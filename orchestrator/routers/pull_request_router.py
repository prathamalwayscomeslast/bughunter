from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from dependencies.auth import CurrentUser
from dependencies.db import get_db
from schemas.common import PaginatedResponse
from schemas.pull_request import PullRequestListItem, PullRequestQueryParams
from services.pull_request_service import PullRequestService
from services.user_service import UserService

router = APIRouter(
    prefix="/pull-requests",
    tags=["pull-requests"],
)


@router.get("", response_model=PaginatedResponse[PullRequestListItem])
def list_pull_requests(
        current_user: CurrentUser,
        params: Annotated[PullRequestQueryParams, Depends()],
        db: Session = Depends(get_db),
) -> PaginatedResponse[PullRequestListItem]:
    user = UserService(db).get_or_create_authenticated_user(current_user)
    service = PullRequestService(db)
    return service.list_pull_requests(user_id=user.id, params=params)