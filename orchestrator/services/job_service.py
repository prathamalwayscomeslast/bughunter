import logging

from arq import ArqRedis
from sqlalchemy.orm import Session

from db.models import JobStatus
from schemas import PaginatedResponse, IssueListItem, PaginationMeta, JobListItem, JobQueryParams, JobDetailResponse
from util.log import setup_logging
from repositories.job_repository import JobRepository
from vcs.client import comment_on_issue

setup_logging()
logger = logging.getLogger(__name__)


class JobService:
    def __init__(self, db: Session, redis: ArqRedis | None = None):
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

    def list_jobs(
            self,
            *,
            user_id: str,
            params: JobQueryParams,
    ) -> PaginatedResponse[JobListItem]:
        status = JobStatus(params.status) if params.status else None

        jobs, total = self.job_repository.list_accessible_jobs(
            user_id=user_id,
            page=params.page,
            page_size=params.page_size,
            repo_id=params.repo_id,
            status=status,
            active_only=params.active_only,
        )

        items = [JobListItem.model_validate(job) for job in jobs]
        has_next = params.page * params.page_size < total

        return PaginatedResponse[JobListItem](
            items=items,
            meta=PaginationMeta(
                total=total,
                page=params.page,
                page_size=params.page_size,
                has_next=has_next,
            ),
        )

    def list_issues_from_jobs(
            self,
            *,
            user_id: str,
            page: int = 1,
            page_size: int = 20,
    ) -> PaginatedResponse[IssueListItem]:
        jobs, total = self.job_repository.list_accessible_jobs(
            user_id=user_id,
            page=page,
            page_size=page_size,
            active_only=False,
        )

        items = [
            IssueListItem(
                id=job.id,
                github_issue_id=0,  # placeholder until a dedicated issue table or field exists
                issue_number=job.issue_number,
                title=job.issue_title or "",
                repo_id=job.repository_id or "",
                repo_full_name=job.repo_full_name,
                html_url="",
                status="open",
                bughunter_job_status=job.status.value if hasattr(job.status, "value") else str(job.status),
                verification_status=None,
                created_at=job.created_at,
                updated_at=job.updated_at,
            )
            for job in jobs
        ]

        has_next = page * page_size < total
        return PaginatedResponse[IssueListItem](
            items=items,
            meta=PaginationMeta(
                total=total,
                page=page,
                page_size=page_size,
                has_next=has_next,
            ),
        )

    def get_job_detail(
            self,
            *,
            job_id: str,
            user_id: str,
    ) -> JobDetailResponse | None:
        job = self.job_repository.get_accessible_job(
            job_id=job_id,
            user_id=user_id,
        )
        if job is None:
            return None
        return JobDetailResponse.model_validate(job)
