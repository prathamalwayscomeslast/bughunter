import logging

from arq import ArqRedis
from sqlalchemy.orm import Session

from db.models import JobStatus
from util.log import setup_logging
from repositories.job_repository import JobRepository
from vcs.client import comment_on_issue

setup_logging()
logger = logging.getLogger(__name__)


class JobService:
    def __init__(self, db: Session, redis: ArqRedis):
        """
        redis is the shared ArqRedis pool created once at app startup via the
        FastAPI lifespan and stored on app.state.redis.  It must be passed in
        rather than created here to avoid opening a new connection per request.
        """
        self.job_repository = JobRepository(db)
        self.redis = redis

    async def handle_bug_issue(
            self,
            installation_id: int,
            repo_full_name: str,
            issue_number: int,
            issue_title: str,
            issue_body: str,
    ):
        job = self.job_repository.create_job(
            installation_id=installation_id,
            repo_full_name=repo_full_name,
            issue_number=issue_number,
            issue_title=issue_title,
            issue_body=issue_body,
        )
        logger.info(
            "Job %s created for %s#%s (status=%s)",
            job.id, repo_full_name, issue_number, JobStatus.RECEIVED,
        )

        try:
            comment_on_issue(
                installation_id=installation_id,
                repo_full_name=repo_full_name,
                issue_number=issue_number,
                message="🐛 BugHunter picked up this issue and is preparing to reproduce it.",
            )
        except Exception as e:
            logger.exception("GitHub App comment failed: %s", e)

        await self.redis.enqueue_job("process_bug_job", job.id)
        logger.info("Job %s enqueued onto Redis", job.id)
        return job
