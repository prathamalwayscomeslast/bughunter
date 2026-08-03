from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from dependencies.auth import CurrentUser
from dependencies.db import get_db
from schemas.me import MeResponse
from services.user_service import UserService

router = APIRouter(
    prefix="/me",
    tags=["me"],
)


@router.get("", response_model=MeResponse)
def get_me(
        current_user: CurrentUser,
        db: Session = Depends(get_db),
) -> MeResponse:
    service = UserService(db)
    return service.get_me(current_user)