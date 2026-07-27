"""
orchestrator/agent/localizer.py

Step 2 of the agentic pipeline: given a confirmed-reproducible bug and a
cloned repository, narrow the search space to 3-5 candidate files that are
most likely to contain the root cause.

Strategy (layered so it degrades gracefully):
  1. Static keyword search — scan every source file for identifiers mentioned
     in the issue title / stack trace (fast, no LLM tokens spent).
  2. tree-sitter AST traversal — for the languages we have parsers for, extract
     function/class names near matches to build richer context.
  3. LLM semantic ranking — feed the top-N candidate snippets to the LLM and
     ask it to rank them by likelihood of containing the root cause.

The final output is a list of (file_path, rationale) tuples, capped at
MAX_CANDIDATES to keep context windows manageable.
"""

from __future__ import annotations

import json
import logging
import os
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import litellm

from config import LLM_MODEL
from agent.issue_parser import ReproductionPlan

logger = logging.getLogger(__name__)

MAX_CANDIDATES = 5          # hard cap fed to LLM ranking
SNIPPET_LINES = 60          # lines of context per candidate file
KEYWORD_MATCH_LIMIT = 20    # max files from keyword scan before LLM ranking

# Source file extensions to scan (binary and generated files excluded)
_SOURCE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rb",
    ".php", ".cs", ".cpp", ".cc", ".c", ".h", ".rs", ".swift",
    ".kt", ".scala", ".sh", ".bash",
}

# Directories that are almost never the source of application bugs
_SKIP_DIRS = {
    ".git", ".github", "node_modules", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".tox", "venv", ".venv", "dist", "build",
    "target", ".idea", ".vscode",
}


@dataclass
class CandidateFile:
    path: str                   # relative to repo root
    snippet: str                # first SNIPPET_LINES lines
    keyword_hits: int           # how many issue keywords matched
    rationale: Optional[str] = None  # LLM-provided reasoning


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_keywords(plan: ReproductionPlan, issue_title: str) -> list[str]:
    """
    Build a keyword list from the reproduction plan and issue title.
    Prefers identifiers that look like function/class/variable names.
    """
    text = " ".join([
        issue_title,
        plan.summary,
        plan.actual_behaviour,
        plan.stack_trace or "",
    ])
    # Extract camelCase, snake_case, PascalCase tokens that look like code
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text)
    # Deduplicate, lowercase, drop stop words
    stop = {"the", "and", "for", "with", "this", "that", "from", "not",
            "error", "exception", "line", "file", "none", "null", "true",
            "false", "class", "function", "def", "var", "let", "const"}
    seen, out = set(), []
    for t in tokens:
        key = t.lower()
        if key not in seen and key not in stop:
            seen.add(key)
            out.append(t)
    return out[:50]  # cap to avoid absurdly long regex


def _walk_source_files(repo_path: Path) -> list[Path]:
    """Yield all source files, skipping irrelevant directories."""
    results = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fname in files:
            if Path(fname).suffix in _SOURCE_EXTENSIONS:
                results.append(Path(root) / fname)
    return results


def _keyword_scan(files: list[Path], keywords: list[str],
                  repo_root: Path) -> list[CandidateFile]:
    """Return files that contain at least one keyword, ranked by hit count."""
    if not keywords:
        return []
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(k) for k in keywords) + r")\b",
        re.IGNORECASE,
    )
    candidates: list[CandidateFile] = []
    for fpath in files:
        try:
            content = fpath.read_text(errors="replace")
        except OSError:
            continue
        hits = len(pattern.findall(content))
        if hits:
            lines = content.splitlines()[:SNIPPET_LINES]
            snippet = "\n".join(lines)
            rel = str(fpath.relative_to(repo_root))
            candidates.append(CandidateFile(path=rel, snippet=snippet,
                                            keyword_hits=hits))
    candidates.sort(key=lambda c: c.keyword_hits, reverse=True)
    return candidates[:KEYWORD_MATCH_LIMIT]


_RANK_SYSTEM_PROMPT = textwrap.dedent("""\
    You are a senior software engineer doing root-cause analysis.
    Given a bug description and a list of candidate source file snippets,
    identify the 1-5 files most likely to contain the root cause.

    Respond ONLY with a JSON array of objects in this exact schema:
    [
      {
        "path": "<relative file path>",
        "rationale": "<one sentence explaining why this file is suspect>"
      }
    ]

    - List files in descending order of suspicion.
    - Include at most 5 entries.
    - If fewer than 5 files are genuinely suspect, include fewer.
    - Do not include files that are clearly irrelevant.
    - No markdown, no code fences, pure JSON only.
""")


def _llm_rank_candidates(candidates: list[CandidateFile],
                         plan: ReproductionPlan,
                         issue_title: str) -> list[CandidateFile]:
    """Ask the LLM to rank and filter candidate files."""
    if not candidates:
        return []

    # Build a compact representation of each candidate to stay within context
    file_blocks = []
    for c in candidates:
        block = f"### {c.path} (keyword hits: {c.keyword_hits})\n{c.snippet[:1500]}"
        file_blocks.append(block)

    user_content = textwrap.dedent(f"""\
        Issue title: {issue_title}

        Bug summary: {plan.summary}
        Actual behaviour: {plan.actual_behaviour}
        Stack trace:
        {plan.stack_trace or 'None provided'}

        --- Candidate files ---
        {chr(10).join(file_blocks)}
    """)

    messages = [
        {"role": "system", "content": _RANK_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    response = litellm.completion(
        model=LLM_MODEL,
        messages=messages,
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content.strip()

    # The model is asked for an array but response_format forces an object;
    # handle both wrapping patterns gracefully.
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            # unwrap common wrappers like {"files": [...]}
            for v in parsed.values():
                if isinstance(v, list):
                    parsed = v
                    break
        if not isinstance(parsed, list):
            parsed = [parsed]
    except json.JSONDecodeError as exc:
        logger.warning("localizer: LLM ranking JSON parse failed: %s — using keyword order", exc)
        return candidates[:MAX_CANDIDATES]

    # Map back to CandidateFile objects, preserving LLM-provided rationale
    path_map = {c.path: c for c in candidates}
    ranked: list[CandidateFile] = []
    for entry in parsed[:MAX_CANDIDATES]:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path", "")
        if path in path_map:
            path_map[path].rationale = entry.get("rationale")
            ranked.append(path_map[path])

    return ranked if ranked else candidates[:MAX_CANDIDATES]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def localize_bug(repo_path: str, plan: ReproductionPlan,
                 issue_title: str) -> list[CandidateFile]:
    """
    Given a cloned repository root path and a ReproductionPlan, return an
    ordered list of CandidateFile objects (at most MAX_CANDIDATES) that are
    the most likely locations of the root cause.

    Returns an empty list if no candidates could be identified — callers
    should treat this as a signal to fall back to a whole-repo LLM search.
    """
    root = Path(repo_path)
    if not root.exists():
        raise FileNotFoundError(f"repo_path does not exist: {repo_path}")

    keywords = _extract_keywords(plan, issue_title)
    logger.info("localizer: %d keywords extracted for scanning", len(keywords))

    source_files = _walk_source_files(root)
    logger.info("localizer: %d source files found in repo", len(source_files))

    keyword_candidates = _keyword_scan(source_files, keywords, root)
    logger.info("localizer: %d candidates after keyword scan", len(keyword_candidates))

    if not keyword_candidates:
        logger.warning("localizer: no keyword matches — returning empty candidates")
        return []

    ranked = _llm_rank_candidates(keyword_candidates, plan, issue_title)
    logger.info("localizer: %d final candidates after LLM ranking", len(ranked))
    for c in ranked:
        logger.debug("  candidate: %s  hits=%d  rationale=%s",
                     c.path, c.keyword_hits, c.rationale)
    return ranked
