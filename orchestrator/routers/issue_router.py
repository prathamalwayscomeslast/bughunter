from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from dependencies.auth import CurrentUser
from dependencies.db import get_db
from schemas.common import PaginatedResponse
from schemas.issue import IssueListItem
from services.job_service import JobService
from services.user_service import UserService

router = APIRouter(
    prefix="/issues",
    tags=["issues"],
)


@router.get("", response_model=PaginatedResponse[IssueListItem])
def list_issues(
        current_user: CurrentUser,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        db: Session = Depends(get_db),
) -> PaginatedResponse[IssueListItem]:
    user = UserService(db).get_or_create_authenticated_user(current_user)
    service = JobService(db)
    return service.list_issues_from_jobs(
        user_id=user.id,
        page=page,
        page_size=page_size,
    )