from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi import status

from orchestrator.dependencies.auth import CurrentUser
from orchestrator.dependencies.db import get_db
from orchestrator.schemas.common import PaginatedResponse
from orchestrator.schemas.job import JobListItem, JobQueryParams, JobDetailResponse
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

@router.get("/{job_id}", response_model=JobDetailResponse)
def get_job(
        job_id: str,
        current_user: CurrentUser,
        db: Session = Depends(get_db),
) -> JobDetailResponse:
    user = UserService(db).get_or_create_authenticated_user(current_user)
    service = JobService(db)
    job = service.get_job_detail(job_id=job_id, user_id=user.id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )
    return job