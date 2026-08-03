from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from dependencies.auth import CurrentUser
from dependencies.db import get_db
from schemas.common import PaginatedResponse
from schemas.repository import RepositoryListItem, RepositoryQueryParams
from services.repository_service import RepositoryService
from services.user_service import UserService

router = APIRouter(
    prefix="/repositories",
    tags=["repositories"],
)


@router.get("", response_model=PaginatedResponse[RepositoryListItem])
def list_repositories(
        current_user: CurrentUser,
        params: Annotated[RepositoryQueryParams, Depends()],
        db: Session = Depends(get_db),
) -> PaginatedResponse[RepositoryListItem]:
    user = UserService(db).get_or_create_authenticated_user(current_user)
    service = RepositoryService(db)
    return service.list_repositories(user_id=user.id, params=params)