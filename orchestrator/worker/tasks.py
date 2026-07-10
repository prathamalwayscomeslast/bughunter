import logging

from db.session import SessionLocal
from repositories.job_repository import JobRepository
from util.log import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

async def process_bug_job(ctx, job_id: str):
    db = SessionLocal()
    try:
        job_repo = JobRepository(db)
        job = job_repo.get_by_id(job_id)
        if not job:
            logger.error("Job %s not found", job_id)
            return

        job_repo.update_status(job_id, "reproducing")
        logger.info(f"Processing job {job_id} for {job.repo_full_name}#{job.issue_number}")

        # TODO next: clone repo, call LLM, run sandbox

        job_repo.update_status(job_id, "done")
    finally:
        db.close()