"""
orchestrator/agent/pr_writer.py

Step 11 of the agentic pipeline: once the repair loop confirms the bug no
longer reproduces, this module:
  1. Creates a feature branch  bughunter/fix/<issue_number>-<slug>
  2. Commits all changed files
  3. Opens a pull request with a structured description

All GitHub API calls use the installation access token obtained via
vcs/auth.py — never a personal access token (see BUGHUNTER_CONTEXT.md §6).
"""

from __future__ import annotations

import logging
import re
import textwrap
from pathlib import Path
from typing import Optional

from github import Github

from agent.issue_parser import ReproductionPlan
from agent.repair import PatchResult
from vcs.auth import get_installation_access_token

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(text: str, max_len: int = 40) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text[:max_len]


def _branch_name(issue_number: int, issue_title: str) -> str:
    return f"bughunter/fix/{issue_number}-{_slugify(issue_title)}"


def _build_pr_body(
        plan: ReproductionPlan,
        result: PatchResult,
        issue_number: int,
        attempt_count: int,
) -> str:
    files_changed = ", ".join(f"`{p.path}`" for p in result.patches) or "(none)"
    steps_md = "\n".join(
        f"  {i+1}. {s}" for i, s in enumerate(plan.steps_to_reproduce)
    ) or "  (not extractable from issue)"

    return textwrap.dedent(f"""\
        ## 🐛 BugHunter Automated Fix

        Closes #{issue_number}

        ---

        ### Root Cause
        {result.root_cause or '(see diff)'}

        ### What Changed
        Files modified: {files_changed}

        {chr(10).join(f'- **`{p.path}`** — {p.explanation}' for p in result.patches)}

        ### How the Bug Was Verified
        {result.verification_reasoning or '(reproduction check passed)'}

        ### Steps That Reproduced the Bug
        {steps_md}

        ---

        > 🤖 This PR was opened automatically by **BugHunter** after {attempt_count}
        > repair attempt(s).  A human must review and merge — BugHunter never
        > auto-merges (see [design principles](https://github.com/prathamalwayscomeslast/bughunter/blob/main/BUGHUNTER_CONTEXT.md#23-human-approval-gate)).
    """).strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def open_fix_pr(
        installation_id: int,
        repo_full_name: str,
        issue_number: int,
        issue_title: str,
        repo_path: str,
        plan: ReproductionPlan,
        result: PatchResult,
        attempt_count: int,
        base_branch: str | None = None,
) -> str:
    """
    Create a branch, commit the patched files, and open a pull request.

    Returns the URL of the newly created PR.

    ``repo_path`` is the filesystem path to the cloned repository (the same
    directory that repair.apply_patch() wrote changes into).
    """
    access_token = get_installation_access_token(installation_id)
    gh = Github(access_token)
    gh_repo = gh.get_repo(repo_full_name)
    if base_branch is None:
        base_branch = gh_repo.default_branch

    branch = _branch_name(issue_number, issue_title)
    logger.info("pr_writer: creating branch '%s' on %s", branch, repo_full_name)

    # ── 1. Verify/create remote branch ────────────────────────────────────
    default_sha = gh_repo.get_branch(base_branch).commit.sha
    try:
        gh_repo.create_git_ref(ref=f"refs/heads/{branch}", sha=default_sha)
        logger.debug("pr_writer: branch created")
    except Exception as exc:
        if "already exists" in str(exc).lower():
            logger.debug("pr_writer: branch already exists, reusing")
        else:
            raise

    # ── 2. Commit each patched file via the Contents API ──────────────────
    root = Path(repo_path)
    for fp in result.patches:
        fpath = root / fp.path
        if not fpath.exists():
            logger.warning("pr_writer: patched file %s missing on disk — skipping", fp.path)
            continue

        new_content = fpath.read_bytes()

        # Fetch the current file's SHA so the API accepts the update
        try:
            existing = gh_repo.get_contents(fp.path, ref=branch)
            file_sha: Optional[str] = existing.sha  # type: ignore[union-attr]
        except Exception:
            file_sha = None  # new file

        commit_message = f"fix({fp.path}): {fp.explanation[:72]}"

        if file_sha:
            gh_repo.update_file(
                path=fp.path,
                message=commit_message,
                content=new_content,
                sha=file_sha,
                branch=branch,
            )
        else:
            gh_repo.create_file(
                path=fp.path,
                message=commit_message,
                content=new_content,
                branch=branch,
            )
        logger.debug("pr_writer: committed %s", fp.path)

    # ── 3. Open the PR ────────────────────────────────────────────────────
    pr_title = f"fix: {issue_title[:72]} (BugHunter #{issue_number})"
    pr_body = _build_pr_body(plan, result, issue_number, attempt_count)

    pr = gh_repo.create_pull(
        title=pr_title,
        body=pr_body,
        head=branch,
        base=base_branch,
    )
    logger.info("pr_writer: PR opened at %s", pr.html_url)
    return pr.html_url
