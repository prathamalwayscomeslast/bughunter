from __future__ import annotations

from sqlalchemy.orm import Session

from orchestrator.db.enums import RepositoryVisibility
from orchestrator.repositories.repository_repository import RepositoryRepository
from orchestrator.schemas.common import PaginatedResponse, PaginationMeta
from orchestrator.schemas.repository import (
    RepositoryListItem,
    RepositoryQueryParams,
)


class RepositoryService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository_repository = RepositoryRepository(db)

    def list_repositories(
            self,
            *,
            user_id: str,
            params: RepositoryQueryParams,
    ) -> PaginatedResponse[RepositoryListItem]:
        visibility = (
            RepositoryVisibility(params.visibility)
            if params.visibility
            else None
        )

        repos, total = self.repository_repository.list_accessible_repositories(
            user_id=user_id,
            page=params.page,
            page_size=params.page_size,
            search=params.search,
            visibility=visibility,
        )

        items = [RepositoryListItem.model_validate(repo) for repo in repos]
        has_next = params.page * params.page_size < total

        return PaginatedResponse[RepositoryListItem](
            items=items,
            meta=PaginationMeta(
                total=total,
                page=params.page,
                page_size=params.page_size,
                has_next=has_next,
            ),
        )