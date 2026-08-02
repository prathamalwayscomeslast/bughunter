from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from orchestrator.dependencies.auth import CurrentUser
from orchestrator.dependencies.db import get_db
from orchestrator.schemas.common import PaginatedResponse
from orchestrator.schemas.job import JobListItem, JobQueryParams
from orchestrator.services.job_service import JobService
from orchestrator.services.user_service import UserService

router = APIRouter(
    prefix="/jobs",
    tags=["jobs"],
)


@router.get("", response_model=PaginatedResponse[JobListItem])
def list_jobs(
        current_user: CurrentUser,
        params: Annotated[JobQueryParams, Depends()],
        db: Session = Depends(get_db),
) -> PaginatedResponse[JobListItem]:
    user = UserService(db).get_or_create_authenticated_user(current_user)
    service = JobService(db)
    return service.list_jobs(user_id=user.id, params=params)