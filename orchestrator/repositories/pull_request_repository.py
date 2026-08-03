from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from db.enums import PullRequestStatus
from db.models import PullRequest, Repository, UserRepositoryAccess


class PullRequestRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, pull_request_id: str) -> PullRequest | None:
        return self.db.get(PullRequest, pull_request_id)

    def list_accessible_pull_requests(
            self,
            *,
            user_id: str,
            page: int = 1,
            page_size: int = 20,
            repo_id: str | None = None,
            status: PullRequestStatus | None = None,
    ) -> tuple[list[PullRequest], int]:
        stmt: Select[tuple[PullRequest]] = (
            select(PullRequest)
            .join(Repository, Repository.id == PullRequest.repository_id)
            .join(UserRepositoryAccess, UserRepositoryAccess.repository_id == Repository.id)
            .where(UserRepositoryAccess.user_id == user_id)
        )

        count_stmt = (
            select(func.count())
            .select_from(PullRequest)
            .join(Repository, Repository.id == PullRequest.repository_id)
            .join(UserRepositoryAccess, UserRepositoryAccess.repository_id == Repository.id)
            .where(UserRepositoryAccess.user_id == user_id)
        )

        if repo_id:
            stmt = stmt.where(PullRequest.repository_id == repo_id)
            count_stmt = count_stmt.where(PullRequest.repository_id == repo_id)

        if status:
            stmt = stmt.where(PullRequest.status == status)
            count_stmt = count_stmt.where(PullRequest.status == status)

        stmt = (
            stmt.order_by(PullRequest.updated_at.desc(), PullRequest.opened_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        items = self.db.scalars(stmt).all()
        total = self.db.scalar(count_stmt) or 0
        return items, total

    def count_accessible_open_pull_requests(self, *, user_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(PullRequest)
            .join(Repository, Repository.id == PullRequest.repository_id)
            .join(UserRepositoryAccess, UserRepositoryAccess.repository_id == Repository.id)
            .where(UserRepositoryAccess.user_id == user_id)
            .where(PullRequest.status == PullRequestStatus.OPEN)
        )
        return self.db.scalar(stmt) or 0