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
applied via patch-ng) so the loop can function without the
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
import patch_ng as _patch_ng
from litellm import JSONSchemaValidationError

from agent.issue_parser import ReproductionPlan
from agent.localizer import CandidateFile
from config import LLM_MODEL

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

_PATCH_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "root_cause": {"type": "string"},
        "patches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "unified_diff": {"type": "string"},
                    "explanation": {"type": "string"},
                },
                "required": ["path", "unified_diff", "explanation"],
                "additionalProperties": False,
            },
        },
        "verification_reasoning": {"type": "string"},
        "confident": {"type": "boolean"},
        "failure_reason": {"type": ["string", "null"]},
    },
    "required": [
        "root_cause",
        "patches",
        "verification_reasoning",
        "confident",
        "failure_reason",
    ],
    "additionalProperties": False,
}

_PATCH_SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert software engineer generating a code fix for a confirmed bug.
    You will be given:
      1. A structured bug report (summary, steps, expected/actual behaviour, stack trace).
      2. Snippets from the 1-5 files most likely to contain the root cause.
      3. (Optionally) a history of previous patch attempts that did NOT fix the bug,
         along with the failure output from each attempt.

    Your task is to produce a correct code patch.

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
    Apply a unified diff string to the repository on disk using patch-ng.

    Returns (success: bool, error_message: str).

    Phase 2 bridge: when the Go sandbox executor is live, this function
    is replaced by an HTTP call to POST /execute on the Go service.
    """

    # patch-ng expects bytes or a file-like object
    patch_set = _patch_ng.fromstring(diff_str.encode("utf-8"))
    if not patch_set:
        return False, "patch-ng could not parse the diff — check unified diff format"

    # apply() takes the root directory as a string; returns True on full success
    success = patch_set.apply(root=str(repo_root))
    if not success:
        # patch-ng logs errors internally; surface a generic message
        return False, (
            "patch-ng failed to apply one or more hunks. "
            "The diff may not match the current file state."
        )

    logger.debug(
        "repair: patch-ng applied %d file(s) under %s",
        len(patch_set.items),
        repo_root,
    )
    return True, ""

def _completion_json_with_fallback(messages: list[dict[str, str]]) -> dict:
    """
    Try schema-based structured output first. If the current provider/model
    rejects the params, fall back to prompt-only JSON and parse manually.
    """
    raw = ""

    try:
        response = litellm.completion(
            model=LLM_MODEL,
            messages=messages,
            temperature=0.1,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "patch_result",
                    "strict": True,
                    "schema": _PATCH_RESULT_SCHEMA,
                },
            },
        )
        raw = (response.choices[0].message.content or "").strip()
        return json.loads(raw)

    except (
            litellm.UnsupportedParamsError,
            litellm.BadRequestError,
    ) as exc:
        logger.warning(
            "repair: structured output unsupported for model=%s, falling back to prompt-only JSON: %s",
            LLM_MODEL,
            exc,
        )

    except JSONSchemaValidationError as exc:
        logger.warning(
            "repair: schema validation failed for model=%s: %s",
            LLM_MODEL,
            exc,
        )
        raw = getattr(exc, "raw_response", "") or ""
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass

    response = litellm.completion(
        model=LLM_MODEL,
        messages=messages + [
            {
                "role": "user",
                "content": (
                    "Return ONLY a valid JSON object matching the required schema. "
                    "Do not wrap it in markdown or add explanation."
                ),
            }
        ],
        temperature=0.1,
    )
    raw = (response.choices[0].message.content or "").strip()
    return json.loads(raw)

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

    try:
        data = _completion_json_with_fallback(messages)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.error("repair: LLM returned invalid JSON: %s", exc)
        return PatchResult(
            confident=False,
            failure_reason=f"LLM returned invalid JSON response: {exc}",
        )
    except Exception as exc:
        logger.exception("repair: LLM completion failed: %s", exc)
        return PatchResult(
            confident=False,
            failure_reason=f"LLM completion failed: {exc}",
        )

    if not isinstance(data, dict):
        return PatchResult(
            confident=False,
            failure_reason="LLM response was not a JSON object",
        )

    raw_patches = data.get("patches", [])
    if not isinstance(raw_patches, list):
        return PatchResult(
            confident=False,
            failure_reason="LLM response contained a non-list 'patches' field",
        )

    patches = []
    for p in raw_patches:
        if not isinstance(p, dict):
            continue
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
