from __future__ import annotations

from sqlalchemy.orm import Session

from db.enums import PullRequestStatus
from repositories.pull_request_repository import PullRequestRepository
from schemas.common import PaginatedResponse, PaginationMeta
from schemas.pull_request import (
    PullRequestListItem,
    PullRequestQueryParams,
)


class PullRequestService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.pull_request_repository = PullRequestRepository(db)

    def list_pull_requests(
            self,
            *,
            user_id: str,
            params: PullRequestQueryParams,
    ) -> PaginatedResponse[PullRequestListItem]:
        status = PullRequestStatus(params.status) if params.status else None

        prs, total = self.pull_request_repository.list_accessible_pull_requests(
            user_id=user_id,
            page=params.page,
            page_size=params.page_size,
            repo_id=params.repo_id,
            status=status,
        )

        items = [PullRequestListItem.model_validate(pr) for pr in prs]
        has_next = params.page * params.page_size < total

        return PaginatedResponse[PullRequestListItem](
            items=items,
            meta=PaginationMeta(
                total=total,
                page=params.page,
                page_size=params.page_size,
                has_next=has_next,
            ),
        )