from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from db.enums import RepositoryVisibility
from db.models import Repository, UserRepositoryAccess


class RepositoryRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, repository_id: str) -> Repository | None:
        return self.db.get(Repository, repository_id)

    def get_by_full_name(self, full_name: str) -> Repository | None:
        stmt = select(Repository).where(Repository.full_name == full_name)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_accessible_repositories(
            self,
            *,
            user_id: str,
            page: int = 1,
            page_size: int = 20,
            search: str | None = None,
            visibility: RepositoryVisibility | None = None,
    ) -> tuple[list[Repository], int]:
        stmt: Select[tuple[Repository]] = (
            select(Repository)
            .join(UserRepositoryAccess, UserRepositoryAccess.repository_id == Repository.id)
            .where(UserRepositoryAccess.user_id == user_id)
        )

        count_stmt = (
            select(func.count())
            .select_from(Repository)
            .join(UserRepositoryAccess, UserRepositoryAccess.repository_id == Repository.id)
            .where(UserRepositoryAccess.user_id == user_id)
        )

        if search:
            like = f"%{search.lower()}%"
            stmt = stmt.where(func.lower(Repository.full_name).like(like))
            count_stmt = count_stmt.where(func.lower(Repository.full_name).like(like))

        if visibility:
            stmt = stmt.where(Repository.visibility == visibility)
            count_stmt = count_stmt.where(Repository.visibility == visibility)

        stmt = (
            stmt.order_by(
                Repository.last_activity_at.desc().nullslast(),
                Repository.full_name.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        items = self.db.scalars(stmt).all()
        total = self.db.scalar(count_stmt) or 0
        return items, total

    def list_accessible_repository_ids(self, *, user_id: str) -> list[str]:
        stmt = (
            select(Repository.id)
            .join(UserRepositoryAccess, UserRepositoryAccess.repository_id == Repository.id)
            .where(UserRepositoryAccess.user_id == user_id)
        )
        return list(self.db.scalars(stmt).all())

    def create_or_update_from_github(
            self,
            *,
            github_repo_id: int,
            installation_id: int,
            full_name: str,
            owner: str,
            name: str,
            visibility: RepositoryVisibility,
            html_url: str,
    ) -> Repository:
        existing = self.get_by_full_name(full_name)
        if existing:
            existing.github_repo_id = github_repo_id
            existing.installation_id = installation_id
            existing.owner = owner
            existing.name = name
            existing.visibility = visibility
            existing.html_url = html_url
            self.db.flush()
            self.db.refresh(existing)
            return existing

        repo = Repository(
            github_repo_id=github_repo_id,
            installation_id=installation_id,
            full_name=full_name,
            owner=owner,
            name=name,
            visibility=visibility,
            html_url=html_url,
        )
        self.db.add(repo)
        self.db.flush()
        self.db.refresh(repo)
        return repo

    def grant_user_access(self, *, user_id: str, repository_id: str) -> None:
        exists_stmt = select(UserRepositoryAccess).where(
            UserRepositoryAccess.user_id == user_id,
            UserRepositoryAccess.repository_id == repository_id,
            )
        existing = self.db.execute(exists_stmt).scalar_one_or_none()
        if existing:
            return

        access = UserRepositoryAccess(user_id=user_id, repository_id=repository_id)
        self.db.add(access)
        self.db.flush()