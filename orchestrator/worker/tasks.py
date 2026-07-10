import logging

from db.session import SessionLocal
from db.models import JobStatus
from repositories.job_repository import JobRepository
from util.log import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

MAX_REPAIR_ATTEMPTS = 5


async def process_bug_job(ctx, job_id: str):
    """
    Main agentic pipeline.  Status transitions mirror the lifecycle defined in
    BUGHUNTER_CONTEXT.md §9:

        received → reproducing → localizing → fixing → pr_opened
                                                     ↘ failed          (repair loop exhausted)
                 → unreproducible                                       (bug not confirmed)
    """
    db = SessionLocal()
    try:
        job_repo = JobRepository(db)
        job = job_repo.get_by_id(job_id)
        if not job:
            logger.error("Job %s not found in DB — skipping", job_id)
            return

        logger.info("Worker picked up job %s for %s#%s", job_id, job.repo_full_name, job.issue_number)

        # ── Step 1: REPRODUCING ──────────────────────────────────────────────
        job_repo.update_status(job_id, JobStatus.REPRODUCING)
        logger.info("[%s] Status → %s", job_id, JobStatus.REPRODUCING)

        # TODO (Phase 2): call litellm to parse issue_body into structured
        # reproduction steps (expected/actual behaviour, steps, stack trace).
        # TODO (Phase 3): clone repo into Docker sandbox and execute repro steps.
        # If bug cannot be reproduced, post diagnosis comment and return early:
        #
        #   job_repo.update_status(job_id, JobStatus.UNREPRODUCIBLE)
        #   comment_on_issue(..., message="Could not reproduce this bug…")
        #   return

        reproduced = False   # placeholder — will be set by sandbox executor
        if not reproduced:
            logger.info("[%s] Bug not yet reproducible (sandbox not implemented — placeholder)", job_id)
            # Remove this early-return once real sandbox is wired in.
            job_repo.update_status(job_id, JobStatus.FAILED)
            return

        # ── Step 2: LOCALIZING ───────────────────────────────────────────────
        job_repo.update_status(job_id, JobStatus.LOCALIZING)
        logger.info("[%s] Status → %s", job_id, JobStatus.LOCALIZING)

        # TODO (Phase 2/3): use tree-sitter AST + LLM semantic search to
        # narrow the bug to 3-5 candidate files.  Store result as JSON on job.

        # ── Step 3: REPAIR LOOP ──────────────────────────────────────────────
        job_repo.update_status(job_id, JobStatus.FIXING)
        logger.info("[%s] Status → %s", job_id, JobStatus.FIXING)

        bug_fixed = False
        for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
            attempts_so_far = job_repo.increment_repair_attempts(job_id)
            logger.info("[%s] Repair attempt %d / %d", job_id, attempts_so_far, MAX_REPAIR_ATTEMPTS)

            # TODO (Phase 3): call LLM to generate patch diff.
            # TODO (Phase 3): apply patch inside sandbox.
            # TODO (Phase 3): rerun reproduction check.
            # If bug no longer reproduces, set bug_fixed = True and break.

            break  # placeholder — remove once real loop is implemented

        if not bug_fixed:
            diagnosis = (
                f"BugHunter exhausted {MAX_REPAIR_ATTEMPTS} repair attempts without "
                f"resolving the bug in {job.repo_full_name}#{job.issue_number}. "
                f"Manual investigation required."
            )
            job_repo.set_diagnosis(job_id, diagnosis)
            job_repo.update_status(job_id, JobStatus.FAILED)
            logger.warning("[%s] Repair loop exhausted — status → %s", job_id, JobStatus.FAILED)
            # TODO: post diagnosis as a comment on the GitHub issue.
            return

        # ── Step 4: PR_OPENED ────────────────────────────────────────────────
        job_repo.update_status(job_id, JobStatus.PR_OPENED)
        logger.info("[%s] Status → %s", job_id, JobStatus.PR_OPENED)

        # TODO (Phase 4): create branch, commit fix, open pull request via
        # vcs/client.py using the GitHub App installation token.

    finally:
        db.close()
