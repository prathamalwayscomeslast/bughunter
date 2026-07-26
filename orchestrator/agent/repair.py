"""
orchestrator/agent/repair.py

Steps 3 + 10 of the agentic pipeline: patch generation and the bounded
repair loop (see BUGHUNTER_CONTEXT.md §2.4, §10.9).

Public API
----------
generate_patch(repo_path, candidates, plan, issue_title,
               previous_attempts=None)  ->  PatchResult

Apply / verify is left intentionally thin here because actual sandbox
execution (Step 7 / Step 3 from the context doc) is a separate concern that
will live in the Go executor service once that is built.  For now, patch
application happens via Python's stdlib `patch` equivalent (unified diff
applied with difflib + pathlib writes) so the loop can function without the
Go service in Phase 2.
"""

from __future__ import annotations

import json
import logging
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import litellm

from config import LLM_MODEL
from agent.issue_parser import ReproductionPlan
from agent.localizer import CandidateFile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class FilePatch:
    """A single file diff in unified diff format."""
    path: str          # relative to repo root
    unified_diff: str  # full unified diff string (--- a/...  +++ b/... hunks)
    explanation: str   # what changed and why


@dataclass
class PatchResult:
    patches: list[FilePatch] = field(default_factory=list)
    # High-level explanation of the root cause found
    root_cause: str = ""
    # How the fix was verified (LLM's self-reported reasoning)
    verification_reasoning: str = ""
    # True when the LLM believes its patch fully resolves the bug
    confident: bool = True
    # Filled when the LLM gives up (e.g., needs more info)
    failure_reason: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps({
            "patches": [{"path": p.path, "explanation": p.explanation} for p in self.patches],
            "root_cause": self.root_cause,
            "verification_reasoning": self.verification_reasoning,
            "confident": self.confident,
            "failure_reason": self.failure_reason,
        }, indent=2)


@dataclass
class PreviousAttempt:
    attempt_number: int
    patches_applied: list[str]      # list of file paths patched
    failure_output: str             # what the sandbox reported after the attempt


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_PATCH_SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert software engineer generating a code fix for a confirmed bug.
    You will be given:
      1. A structured bug report (summary, steps, expected/actual behaviour, stack trace).
      2. Snippets from the 1-5 files most likely to contain the root cause.
      3. (Optionally) a history of previous patch attempts that did NOT fix the bug,
         along with the failure output from each attempt.

    Your task is to produce a minimal, correct code patch.

    Respond ONLY with a valid JSON object matching this exact schema — no markdown,
    no code fences, pure JSON:

    {
      "root_cause": "<one paragraph explanation of what is wrong and why>",
      "patches": [
        {
          "path": "<relative file path>",
          "unified_diff": "<complete unified diff for this file, starting with --- a/path",
          "explanation": "<one sentence: what this change does>"
        }
      ],
      "verification_reasoning": "<how you verified this will fix the bug>",
      "confident": true,
      "failure_reason": null
    }

    Rules:
    - unified_diff MUST be a valid unified diff (--- / +++ / @@ headers required).
    - Only patch the minimum lines necessary.  Avoid unrelated refactoring.
    - If you genuinely cannot determine a fix (e.g., missing context, bug is in a
      dependency you cannot change), set confident to false and explain in
      failure_reason instead of guessing.
    - Patches array may have multiple entries if multiple files need changes.
    - Preserve existing code style — indentation, quote style, etc.
""")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_user_message(
        plan: ReproductionPlan,
        issue_title: str,
        candidates: list[CandidateFile],
        previous_attempts: Optional[list[PreviousAttempt]],
) -> str:
    parts = [
        f"Issue title: {issue_title}",
        f"\nSummary: {plan.summary}",
        f"Expected: {plan.expected_behaviour}",
        f"Actual: {plan.actual_behaviour}",
    ]
    if plan.stack_trace:
        parts.append(f"Stack trace:\n{plan.stack_trace}")
    if plan.steps_to_reproduce:
        parts.append("Steps to reproduce:\n" +
                     "\n".join(f"  {i+1}. {s}"
                               for i, s in enumerate(plan.steps_to_reproduce)))

    parts.append("\n--- Suspect file contents ---")
    for c in candidates:
        parts.append(f"\n### {c.path}\n{c.snippet[:2000]}")
        if c.rationale:
            parts.append(f"(Suspicion rationale: {c.rationale})")

    if previous_attempts:
        parts.append("\n--- Previous fix attempts that FAILED ---")
        for pa in previous_attempts:
            parts.append(
                f"\nAttempt {pa.attempt_number} patched: {', '.join(pa.patches_applied)}\n"
                f"Failure output:\n{pa.failure_output[:1000]}"
            )
        parts.append(
            "\nNote: The above patches did NOT fix the bug. "
            "Reason through what went wrong and produce a different approach."
        )

    return "\n".join(parts)


def _apply_unified_diff(repo_root: Path, diff_str: str) -> tuple[bool, str]:
    """
    Apply a unified diff string to the repository on disk.

    Returns (success: bool, error_message: str).

    This is a pure-Python diff applier for Phase 2.  When the Go sandbox
    executor is live, diff application will move there and this function will
    be replaced by an HTTP call to POST /execute.
    """
    import re as _re

    # Split diff into per-file blocks
    file_blocks = _re.split(r'^(?=--- )', diff_str, flags=_re.MULTILINE)
    applied = 0
    errors = []

    for block in file_blocks:
        block = block.strip()
        if not block or not block.startswith("---"):
            continue

        # Extract target path from +++ line
        lines = block.splitlines()
        plus_line = next((l for l in lines if l.startswith("+++ ")), None)
        if not plus_line:
            errors.append(f"No +++ line found in block: {block[:80]}")
            continue

        # Strip b/ prefix if present
        raw_path = plus_line[4:].strip()
        if raw_path.startswith("b/"):
            raw_path = raw_path[2:]

        target = repo_root / raw_path
        if not target.exists():
            errors.append(f"Target file does not exist: {raw_path}")
            continue

        try:
            original_lines = target.read_text(errors="replace").splitlines(keepends=True)
        except OSError as e:
            errors.append(f"Cannot read {raw_path}: {e}")
            continue

        # Walk through hunks and apply changes
        patched = list(original_lines)
        hunk_pattern = _re.compile(r'^@@ -([0-9]+)(?:,([0-9]+))? \+([0-9]+)(?:,([0-9]+))? @@')
        i = 0
        offset = 0   # cumulative line offset from previous hunks

        while i < len(lines):
            m = hunk_pattern.match(lines[i])
            if not m:
                i += 1
                continue

            orig_start = int(m.group(1)) - 1  # 0-indexed
            hunk_lines = []
            i += 1
            while i < len(lines) and not hunk_pattern.match(lines[i]):
                if lines[i].startswith(("---", "+++")):
                    i += 1
                    continue
                hunk_lines.append(lines[i])
                i += 1

            # Build the replacement
            pos = orig_start + offset
            remove_count = sum(1 for l in hunk_lines if l.startswith("-") or l.startswith(" "))
            new_content = []
            for hl in hunk_lines:
                if hl.startswith("+"):
                    new_content.append(hl[1:] + ("" if hl[1:].endswith("\n") else "\n"))
                elif hl.startswith(" "):
                    new_content.append(hl[1:] + ("" if hl[1:].endswith("\n") else "\n"))
                # lines starting with "-" are removed

            patched[pos:pos + remove_count] = new_content
            offset += len(new_content) - remove_count

        target.write_text("".join(patched), encoding="utf-8")
        applied += 1
        logger.debug("repair: applied diff to %s", raw_path)

    if errors:
        return False, "; ".join(errors)
    if applied == 0:
        return False, "No hunks applied — diff may be malformed"
    return True, ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_patch(
        repo_path: str,
        candidates: list[CandidateFile],
        plan: ReproductionPlan,
        issue_title: str,
        previous_attempts: Optional[list[PreviousAttempt]] = None,
) -> PatchResult:
    """
    Call the LLM to generate a code patch for the given bug.

    Does NOT apply the patch — call apply_patch() separately so that the
    sandbox executor can validate before writing to disk.
    """
    user_msg = _build_user_message(plan, issue_title, candidates, previous_attempts)
    messages = [
        {"role": "system", "content": _PATCH_SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    response = litellm.completion(
        model=LLM_MODEL,
        messages=messages,
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("repair: LLM returned non-JSON: %s", exc)
        return PatchResult(
            confident=False,
            failure_reason=f"LLM returned non-JSON response: {exc}",
        )

    patches = []
    for p in data.get("patches", []):
        patches.append(FilePatch(
            path=p.get("path", ""),
            unified_diff=p.get("unified_diff", ""),
            explanation=p.get("explanation", ""),
        ))

    return PatchResult(
        patches=patches,
        root_cause=data.get("root_cause", ""),
        verification_reasoning=data.get("verification_reasoning", ""),
        confident=data.get("confident", True),
        failure_reason=data.get("failure_reason"),
    )


def apply_patch(repo_path: str, result: PatchResult) -> tuple[bool, str]:
    """
    Write the patches from a PatchResult to disk.

    Returns (success, error_message).  When the Go sandbox executor is
    available, this function will be replaced by a call to its /execute
    endpoint and the result parsed from the response.
    """
    root = Path(repo_path)
    all_errors = []
    for fp in result.patches:
        ok, err = _apply_unified_diff(root, fp.unified_diff)
        if not ok:
            all_errors.append(f"{fp.path}: {err}")
            logger.warning("repair.apply_patch: failed to apply diff to %s: %s", fp.path, err)

    if all_errors:
        return False, "; ".join(all_errors)
    return True, ""
