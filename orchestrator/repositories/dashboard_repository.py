from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.enums import JobStatus, PullRequestStatus
from db.models import Job, PullRequest, Repository, UserRepositoryAccess


ACTIVE_JOB_STATUSES = (
    JobStatus.RECEIVED,
    JobStatus.REPRODUCING,
    JobStatus.LOCALIZING,
    JobStatus.FIXING,
)


class DashboardRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def count_repositories(self, *, user_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(Repository)
            .join(UserRepositoryAccess, UserRepositoryAccess.repository_id == Repository.id)
            .where(UserRepositoryAccess.user_id == user_id)
        )
        return self.db.scalar(stmt) or 0

    def count_active_jobs(self, *, user_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(Job)
            .join(Repository, Repository.id == Job.repository_id)
            .join(UserRepositoryAccess, UserRepositoryAccess.repository_id == Repository.id)
            .where(UserRepositoryAccess.user_id == user_id)
            .where(Job.status.in_(ACTIVE_JOB_STATUSES))
        )
        return self.db.scalar(stmt) or 0

    def count_active_issues(self, *, user_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(Job)
            .join(Repository, Repository.id == Job.repository_id)
            .join(UserRepositoryAccess, UserRepositoryAccess.repository_id == Repository.id)
            .where(UserRepositoryAccess.user_id == user_id)
            .where(Job.status.in_(ACTIVE_JOB_STATUSES))
        )
        return self.db.scalar(stmt) or 0

    def count_open_pull_requests(self, *, user_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(PullRequest)
            .join(Repository, Repository.id == PullRequest.repository_id)
            .join(UserRepositoryAccess, UserRepositoryAccess.repository_id == Repository.id)
            .where(UserRepositoryAccess.user_id == user_id)
            .where(PullRequest.status == PullRequestStatus.OPEN)
        )
        return self.db.scalar(stmt) or 0

    def list_repository_previews(self, *, user_id: str, limit: int = 5) -> list[Repository]:
        stmt = (
            select(Repository)
            .join(UserRepositoryAccess, UserRepositoryAccess.repository_id == Repository.id)
            .where(UserRepositoryAccess.user_id == user_id)
            .order_by(Repository.last_activity_at.desc().nullslast(), Repository.full_name.asc())
            .limit(limit)
        )
        return self.db.scalars(stmt).all()

    def list_job_previews(self, *, user_id: str, limit: int = 10) -> list[Job]:
        stmt = (
            select(Job)
            .join(Repository, Repository.id == Job.repository_id)
            .join(UserRepositoryAccess, UserRepositoryAccess.repository_id == Repository.id)
            .where(UserRepositoryAccess.user_id == user_id)
            .order_by(Job.updated_at.desc())
            .limit(limit)
        )
        return self.db.scalars(stmt).all()

    def list_issue_previews(self, *, user_id: str, limit: int = 10) -> list[Job]:
        stmt = (
            select(Job)
            .join(Repository, Repository.id == Job.repository_id)
            .join(UserRepositoryAccess, UserRepositoryAccess.repository_id == Repository.id)
            .where(UserRepositoryAccess.user_id == user_id)
            .order_by(Job.updated_at.desc())
            .limit(limit)
        )
        return self.db.scalars(stmt).all()

    def list_pull_request_previews(self, *, user_id: str, limit: int = 10) -> list[PullRequest]:
        stmt = (
            select(PullRequest)
            .join(Repository, Repository.id == PullRequest.repository_id)
            .join(UserRepositoryAccess, UserRepositoryAccess.repository_id == Repository.id)
            .where(UserRepositoryAccess.user_id == user_id)
            .order_by(PullRequest.updated_at.desc())
            .limit(limit)
        )
        return self.db.scalars(stmt).all()