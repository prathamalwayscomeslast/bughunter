"""
orchestrator/worker/tasks.py

Main agentic pipeline wired end-to-end.  Each section corresponds to a step
in BUGHUNTER_CONTEXT.md §3 ("End-to-End Flow").

Status transitions:
    received
      → reproducing   (parse + sandbox — sandbox is a placeholder in Phase 2)
          → unreproducible   (bug not confirmed — job ends)
      → localizing
      → fixing
          → pr_opened   (success)
          → failed      (repair loop exhausted)
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile

from db.session import SessionLocal
from db.models import JobStatus
from repositories.job_repository import JobRepository
from util.log import setup_logging
from vcs.auth import get_installation_access_token
from vcs.client import comment_on_issue

from agent.issue_parser import parse_issue
from agent.localizer import localize_bug
from agent.repair import (
    generate_patch, apply_patch,
    PreviousAttempt,
)
from agent.pr_writer import open_fix_pr

setup_logging()
logger = logging.getLogger(__name__)

MAX_REPAIR_ATTEMPTS = int(os.getenv("MAX_REPAIR_ATTEMPTS", "5"))


async def process_bug_job(ctx, job_id: str):
    """
    ARQ task entry point.  ctx is the ARQ context dict (contains the Redis
    connection if needed for future sub-task fanout).
    """
    db = SessionLocal()
    try:
        job_repo = JobRepository(db)
        job = job_repo.get_by_id(job_id)
        if not job:
            logger.error("Worker: job %s not found in DB — skipping", job_id)
            return

        logger.info(
            "Worker: picked up job %s  repo=%s  issue=#%s",
            job_id, job.repo_full_name, job.issue_number,
        )

        # ── Phase 2a: Parse issue into structured reproduction plan ─────────
        job_repo.update_status(job_id, JobStatus.REPRODUCING)
        logger.info("[%s] Status → REPRODUCING", job_id)

        try:
            plan = parse_issue(job.issue_title or "", job.issue_body or "")
        except Exception as exc:
            logger.exception("[%s] Issue parsing failed: %s", job_id, exc)
            _fail_with_diagnosis(
                job_repo, job_id,
                f"BugHunter could not parse the issue description: {exc}",
                job.installation_id, job.repo_full_name, job.issue_number,
            )
            return

        if not plan.reproducible_from_description:
            reason = plan.not_reproducible_reason or "insufficient information in issue body"
            logger.info("[%s] Issue not reproducible: %s", job_id, reason)
            job_repo.update_status(job_id, JobStatus.UNREPRODUCIBLE)
            comment_on_issue(
                job.installation_id,
                job.repo_full_name,
                job.issue_number,
                (
                    f"🔍 **BugHunter** analysed this issue but could not extract "
                    f"enough information to attempt reproduction.\n\n"
                    f"**Reason:** {reason}\n\n"
                    f"Please add more detail (steps to reproduce, expected vs actual "
                    f"behaviour, stack trace) and re-apply the `bug` label."
                ),
            )
            return

        logger.info(
            "[%s] Reproduction plan extracted: %s steps, reproducible=%s",
            job_id, len(plan.steps_to_reproduce), plan.reproducible_from_description,
        )

        # ── Phase 2b: Clone repo ─────────────────────────────────────────────
        # We clone into a temporary directory that is cleaned up at the end.
        # Authentication uses the installation token so private repos work.
        workdir = tempfile.mkdtemp(prefix=f"bughunter_{job_id}_")
        try:
            _clone_repo(
                installation_id=job.installation_id,
                repo_full_name=job.repo_full_name,
                target_dir=workdir,
            )
        except Exception as exc:
            logger.exception("[%s] Repo clone failed: %s", job_id, exc)
            _fail_with_diagnosis(
                job_repo, job_id,
                f"BugHunter could not clone the repository: {exc}",
                job.installation_id, job.repo_full_name, job.issue_number,
            )
            shutil.rmtree(workdir, ignore_errors=True)
            return

        try:
            # ── Phase 2c: Localize ────────────────────────────────────────────
            job_repo.update_status(job_id, JobStatus.LOCALIZING)
            logger.info("[%s] Status → LOCALIZING", job_id)

            candidates = localize_bug(workdir, plan, job.issue_title or "")
            if not candidates:
                logger.warning(
                    "[%s] Localization returned no candidates — aborting", job_id
                )
                _fail_with_diagnosis(
                    job_repo, job_id,
                    (
                        f"BugHunter could not identify candidate files for "
                        f"{job.repo_full_name}#{job.issue_number}. "
                        f"The codebase may not contain identifiers mentioned in the issue."
                    ),
                    job.installation_id, job.repo_full_name, job.issue_number,
                )
                return

            logger.info(
                "[%s] Localised to %d candidate file(s): %s",
                job_id, len(candidates), [c.path for c in candidates],
            )

            # ── Phase 2d: Repair loop ─────────────────────────────────────────
            job_repo.update_status(job_id, JobStatus.FIXING)
            logger.info("[%s] Status → FIXING", job_id)

            previous_attempts: list[PreviousAttempt] = []
            pr_url: str | None = None

            for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
                attempts_so_far = job_repo.increment_repair_attempts(job_id)
                logger.info(
                    "[%s] Repair attempt %d / %d",
                    job_id, attempts_so_far, MAX_REPAIR_ATTEMPTS,
                )

                # 1. Generate patch
                patch_result = generate_patch(
                    repo_path=workdir,
                    candidates=candidates,
                    plan=plan,
                    issue_title=job.issue_title or "",
                    previous_attempts=previous_attempts if previous_attempts else None,
                )

                if not patch_result.confident:
                    logger.warning(
                        "[%s] LLM not confident in patch: %s",
                        job_id, patch_result.failure_reason,
                    )
                    _fail_with_diagnosis(
                        job_repo, job_id,
                        (
                            f"BugHunter could not generate a fix after {attempt} attempt(s).\n"
                            f"Root cause hypothesis: {patch_result.root_cause}\n"
                            f"Reason: {patch_result.failure_reason}"
                        ),
                        job.installation_id, job.repo_full_name, job.issue_number,
                    )
                    return

                # 2. Apply patch to disk
                apply_ok, apply_err = apply_patch(workdir, patch_result)
                if not apply_ok:
                    logger.warning(
                        "[%s] Patch application failed: %s", job_id, apply_err
                    )
                    previous_attempts.append(PreviousAttempt(
                        attempt_number=attempt,
                        patches_applied=[p.path for p in patch_result.patches],
                        failure_output=f"Patch could not be applied: {apply_err}",
                    ))
                    continue

                # 3. Sandbox verification
                # Phase 2 placeholder: trust the LLM's verification_reasoning.
                # Phase 3 will execute the reproduction steps in a Docker sandbox
                # and set bug_fixed based on actual process exit codes.
                bug_fixed = patch_result.confident and bool(patch_result.patches)

                if bug_fixed:
                    logger.info("[%s] Patch accepted on attempt %d", job_id, attempt)
                    try:
                        pr_url = open_fix_pr(
                            installation_id=job.installation_id,
                            repo_full_name=job.repo_full_name,
                            issue_number=job.issue_number,
                            issue_title=job.issue_title or "",
                            repo_path=workdir,
                            plan=plan,
                            result=patch_result,
                            attempt_count=attempt,
                        )
                    except Exception as exc:
                        logger.exception(
                            "[%s] PR creation failed: %s", job_id, exc
                        )
                        _fail_with_diagnosis(
                            job_repo, job_id,
                            f"Fix was generated but PR creation failed: {exc}",
                            job.installation_id, job.repo_full_name, job.issue_number,
                        )
                        return

                    job_repo.update_status(job_id, JobStatus.PR_OPENED)
                    logger.info(
                        "[%s] Status → PR_OPENED  url=%s", job_id, pr_url
                    )
                    comment_on_issue(
                        job.installation_id,
                        job.repo_full_name,
                        job.issue_number,
                        (
                            f"✅ **BugHunter** has opened a pull request with a proposed fix:\n"
                            f"{pr_url}\n\n"
                            f"**Root cause:** {patch_result.root_cause}\n\n"
                            f"Please review the PR and merge if the fix looks correct. "
                            f"BugHunter will never auto-merge."
                        ),
                    )
                    return

                # Bug still reproduced — record failure context for next attempt
                previous_attempts.append(PreviousAttempt(
                    attempt_number=attempt,
                    patches_applied=[p.path for p in patch_result.patches],
                    failure_output="Sandbox verification indicated bug still reproduces "
                                   "(Phase 3 sandbox not yet wired — placeholder)",
                ))

            # Repair loop exhausted
            diagnosis = (
                f"BugHunter exhausted {MAX_REPAIR_ATTEMPTS} repair attempts without "
                f"resolving the bug in {job.repo_full_name}#{job.issue_number}.\n\n"
                f"Last known root cause hypothesis:\n{getattr(patch_result, 'root_cause', 'N/A')}\n\n"
                f"Manual investigation is required."
            )
            _fail_with_diagnosis(
                job_repo, job_id, diagnosis,
                job.installation_id, job.repo_full_name, job.issue_number,
            )

        finally:
            shutil.rmtree(workdir, ignore_errors=True)
            logger.debug("[%s] Cleaned up workdir %s", job_id, workdir)

    finally:
        db.close()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fail_with_diagnosis(
        job_repo: JobRepository,
        job_id: str,
        diagnosis: str,
        installation_id: int,
        repo_full_name: str,
        issue_number: int,
) -> None:
    """Mark the job FAILED, persist the diagnosis, and post it as an issue comment."""
    job_repo.set_diagnosis(job_id, diagnosis)
    job_repo.update_status(job_id, JobStatus.FAILED)
    logger.warning("[%s] Status → FAILED  diagnosis=%s", job_id, diagnosis[:120])
    try:
        comment_on_issue(
            installation_id,
            repo_full_name,
            issue_number,
            (
                f"❌ **BugHunter** was unable to automatically resolve this bug.\n\n"
                f"{diagnosis}\n\n"
                f"You may re-trigger BugHunter by removing and re-applying the `bug` label."
            ),
        )
    except Exception as exc:
        logger.warning("[%s] Failed to post diagnosis comment: %s", job_id, exc)


def _clone_repo(installation_id: int, repo_full_name: str, target_dir: str) -> None:
    """
    Clone the target repository into target_dir using the installation access
    token for authentication.  Works for both public and private repos.
    """
    import subprocess
    token = get_installation_access_token(installation_id)
    clone_url = f"https://x-access-token:{token}@github.com/{repo_full_name}.git"
    result = subprocess.run(
        ["git", "clone", "--depth=1", clone_url, target_dir],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git clone failed (exit {result.returncode}): {result.stderr[:400]}"
        )
    logger.info("_clone_repo: cloned %s into %s", repo_full_name, target_dir)
