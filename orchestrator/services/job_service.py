import logging

from sqlalchemy.orm import Session
from arq import create_pool
from arq.connections import RedisSettings

from config import REDIS_URL
from util.log import setup_logging
from repositories.job_repository import JobRepository
from vcs.client import comment_on_issue

setup_logging()
logger = logging.getLogger(__name__)

class JobService:
    def __init__(self, db: Session):
        self.job_repository = JobRepository(db)

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

        try:
            comment_on_issue(
                installation_id=installation_id,
                repo_full_name=repo_full_name,
                issue_number=issue_number,
                message="BugHunter picked up this issue and is preparing to reproduce it."
            )
        except Exception as e:
            logger.exception("GitHub App comment failed: %s", e)

        redis = await create_pool(RedisSettings.from_dsn(REDIS_URL))
        await redis.enqueue_job("process_bug_job", job.id)
        return job