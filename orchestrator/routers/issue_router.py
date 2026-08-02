from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from orchestrator.dependencies.auth import CurrentUser
from orchestrator.dependencies.db import get_db
from orchestrator.schemas.common import PaginatedResponse
from orchestrator.schemas.issue import IssueListItem
from orchestrator.services.job_service import JobService
from orchestrator.services.user_service import UserService

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