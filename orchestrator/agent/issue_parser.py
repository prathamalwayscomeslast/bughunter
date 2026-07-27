"""
orchestrator/agent/issue_parser.py

Step 1 of the agentic pipeline: parse a freeform GitHub issue body into a
structured ReproductionPlan using the LLM (via litellm so the provider is
swappable — see BUGHUNTER_CONTEXT.md §2.1).

The output of this module is the single source of truth that the sandbox
executor and repair loop consume.  Every downstream stage works off
ReproductionPlan, never off raw issue_body strings.
"""

from __future__ import annotations

import json
import logging
import textwrap
from dataclasses import dataclass, field
from typing import Optional

import litellm

from config import LLM_MODEL

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ReproductionPlan:
    """Structured view of a bug report extracted by the LLM."""
    # One-sentence summary of what is broken.
    summary: str
    # Numbered list of exact steps that trigger the bug (shell commands,
    # HTTP requests, UI interactions, etc.).
    steps_to_reproduce: list[str] = field(default_factory=list)
    # What the reporter expected to happen.
    expected_behaviour: str = ""
    # What actually happened (error message / wrong output).
    actual_behaviour: str = ""
    # Full stack trace, if present in the issue body.
    stack_trace: Optional[str] = None
    # Runtime / OS / dependency versions the reporter mentioned.
    environment: dict[str, str] = field(default_factory=dict)
    # Whether we have enough information to try reproduction at all.
    reproducible_from_description: bool = True
    # Reason why not, if reproducible_from_description is False.
    not_reproducible_reason: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=2, default=str)

    @classmethod
    def from_dict(cls, d: dict) -> "ReproductionPlan":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = textwrap.dedent("""\
    You are a senior software engineer helping an autonomous bug-fixing agent.
    Your job is to parse a GitHub issue body and extract structured information
    needed to reproduce the reported bug inside an isolated sandbox.

    Respond ONLY with a valid JSON object — no markdown, no code fences, no prose.
    The JSON must match this exact schema:

    {
      "summary": "<one-sentence plain-English description of the bug>",
      "steps_to_reproduce": ["step 1", "step 2", ...],
      "expected_behaviour": "<what should happen>",
      "actual_behaviour": "<what does happen / error message>",
      "stack_trace": "<full stack trace or null if absent>",
      "environment": {"key": "value"},
      "reproducible_from_description": true,
      "not_reproducible_reason": null
    }

    Rules:
    - If steps_to_reproduce cannot be extracted, set
      reproducible_from_description to false and explain in
      not_reproducible_reason.
    - Preserve exact commands and error messages verbatim.
    - If a field has no information, use null or [] or {} as appropriate.
    - Never add extra fields to the JSON.
""")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_issue(issue_title: str, issue_body: str) -> ReproductionPlan:
    """
    Call the configured LLM and return a ReproductionPlan.

    Raises ValueError if the LLM returns malformed JSON after two attempts.
    """
    user_content = f"Issue title: {issue_title}\n\n{issue_body or '(no body provided)'}"

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    for attempt in range(1, 3):  # allow one retry on malformed JSON
        logger.debug("parse_issue: LLM call attempt %d model=%s", attempt, LLM_MODEL)
        response = litellm.completion(
            model=LLM_MODEL,
            messages=messages,
            temperature=0.0,          # deterministic extraction
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content.strip()

        try:
            data = json.loads(raw)
            plan = ReproductionPlan.from_dict(data)
            logger.info("parse_issue: plan extracted — reproducible=%s",
                        plan.reproducible_from_description)
            return plan
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("parse_issue: attempt %d — JSON parse failed: %s", attempt, exc)
            if attempt == 2:
                raise ValueError(
                    f"LLM returned non-JSON after two attempts. Raw output:\n{raw}"
                ) from exc
            # Inject the bad response back so the model can self-correct.
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": "Your last response was not valid JSON. "
                           "Please respond with valid JSON only, no other text.",
            })

    # unreachable, but keeps type checker happy :p
    raise ValueError("parse_issue: unexpected exit")
