from sqlalchemy import func, select, Select
from sqlalchemy.orm import Session
from db.models import Job, JobStatus, Repository, UserRepositoryAccess

ACTIVE_JOB_STATUSES = (
    JobStatus.RECEIVED,
    JobStatus.REPRODUCING,
    JobStatus.LOCALIZING,
    JobStatus.FIXING,
)

class JobRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_job(
            self,
            installation_id: int,
            repo_full_name: str,
            issue_number: int,
            issue_title: str,
            issue_body: str,
    ) -> Job:
        job = Job(
            installation_id=installation_id,
            repo_full_name=repo_full_name,
            issue_number=issue_number,
            issue_title=issue_title,
            issue_body=issue_body,
            status=JobStatus.RECEIVED,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_by_id(self, job_id: str) -> Job | None:
        return self.db.query(Job).filter(Job.id == job_id).first()

    def update_status(self, job_id: str, status: str) -> None:
        job = self.get_by_id(job_id)
        if job:
            job.status = status
            self.db.commit()

    def increment_repair_attempts(self, job_id: str) -> int:
        """Atomically bump repair_attempts and return the new value."""
        job = self.get_by_id(job_id)
        if job:
            job.repair_attempts = (job.repair_attempts or 0) + 1
            self.db.commit()
            return job.repair_attempts
        return 0

    def set_diagnosis(self, job_id: str, diagnosis: str) -> None:
        job = self.get_by_id(job_id)
        if job:
            job.diagnosis = diagnosis
            self.db.commit()

    def set_pr_url(self, job_id: str, pr_url: str) -> None:
        job = self.get_by_id(job_id)
        if job:
            job.pr_url = pr_url
            self.db.commit()

    def list_accessible_jobs(
            self,
            *,
            user_id: str,
            page: int = 1,
            page_size: int = 20,
            repo_id: str | None = None,
            status: JobStatus | None = None,
            active_only: bool = False,
    ) -> tuple[list[Job], int]:
        stmt: Select[tuple[Job]] = (
            select(Job)
            .outerjoin(Repository, Repository.id == Job.repository_id)
            .join(
                UserRepositoryAccess,
                UserRepositoryAccess.repository_id == Repository.id,
                )
            .where(UserRepositoryAccess.user_id == user_id)
        )

        count_stmt = (
            select(func.count())
            .select_from(Job)
            .outerjoin(Repository, Repository.id == Job.repository_id)
            .join(
                UserRepositoryAccess,
                UserRepositoryAccess.repository_id == Repository.id,
                )
            .where(UserRepositoryAccess.user_id == user_id)
        )

        if repo_id:
            stmt = stmt.where(Job.repository_id == repo_id)
            count_stmt = count_stmt.where(Job.repository_id == repo_id)

        if status:
            stmt = stmt.where(Job.status == status)
            count_stmt = count_stmt.where(Job.status == status)

        if active_only:
            stmt = stmt.where(Job.status.in_(ACTIVE_JOB_STATUSES))
            count_stmt = count_stmt.where(Job.status.in_(ACTIVE_JOB_STATUSES))

        stmt = (
            stmt.order_by(Job.updated_at.desc(), Job.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        items = self.db.scalars(stmt).all()
        total = self.db.scalar(count_stmt) or 0
        return items, total

    def get_accessible_job(
            self,
            *,
            job_id: str,
            user_id: str,
    ) -> Job | None:
        """
        Fetch a single job by ID, but only if the requesting user has
        UserRepositoryAccess to the repository it belongs to.
        Returns None if the job doesn't exist OR the user can't see it.
        """
        stmt = (
            select(Job)
            .outerjoin(Repository, Repository.id == Job.repository_id)
            .join(
                UserRepositoryAccess,
                UserRepositoryAccess.repository_id == Repository.id,
                )
            .where(Job.id == job_id)
            .where(UserRepositoryAccess.user_id == user_id)
        )
        return self.db.scalars(stmt).first()

    def count_accessible_active_jobs(self, *, user_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(Job)
            .join(Repository, Repository.id == Job.repository_id)
            .join(UserRepositoryAccess, UserRepositoryAccess.repository_id == Repository.id)
            .where(UserRepositoryAccess.user_id == user_id)
            .where(Job.status.in_(ACTIVE_JOB_STATUSES))
        )
        return self.db.scalar(stmt) or 0

    def count_accessible_active_issues(self, *, user_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(Job)
            .join(Repository, Repository.id == Job.repository_id)
            .join(UserRepositoryAccess, UserRepositoryAccess.repository_id == Repository.id)
            .where(UserRepositoryAccess.user_id == user_id)
            .where(Job.status.in_(ACTIVE_JOB_STATUSES))
        )
        return self.db.scalar(stmt) or 0

    def list_recent_accessible_issue_views(
            self,
            *,
            user_id: str,
            limit: int = 10,
    ) -> list[Job]:
        stmt = (
            select(Job)
            .join(Repository, Repository.id == Job.repository_id)
            .join(UserRepositoryAccess, UserRepositoryAccess.repository_id == Repository.id)
            .where(UserRepositoryAccess.user_id == user_id)
            .order_by(Job.updated_at.desc())
            .limit(limit)
        )
        return self.db.scalars(stmt).all()

