from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from dependencies.auth import CurrentUser
from dependencies.db import get_db
from schemas.dashboard import DashboardResponse, DashboardSummaryResponse
from services.dashboard_service import DashboardService
from services.user_service import UserService

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
)


@router.get("", response_model=DashboardResponse)
def get_dashboard(
        current_user: CurrentUser,
        db: Session = Depends(get_db),
) -> DashboardResponse:
    user = UserService(db).get_or_create_authenticated_user(current_user)
    service = DashboardService(db)
    return service.get_dashboard(user_id=user.id)


@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
        current_user: CurrentUser,
        db: Session = Depends(get_db),
) -> DashboardSummaryResponse:
    user = UserService(db).get_or_create_authenticated_user(current_user)
    service = DashboardService(db)
    return service.get_summary(user_id=user.id)