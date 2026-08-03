from __future__ import annotations

from sqlalchemy.orm import Session

from repositories.user_repository import UserRepository
from schemas.auth import AuthenticatedUser
from schemas.me import MeResponse


class UserService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.user_repository = UserRepository(db)

    def get_or_create_authenticated_user(self, auth_user: AuthenticatedUser):
        try:
            user = self.user_repository.get_or_create_from_auth(
                firebase_uid=auth_user.firebase_uid,
                email=auth_user.email,
                email_verified=auth_user.email_verified,
                display_name=auth_user.display_name,
                photo_url=auth_user.photo_url,
                sign_in_provider=auth_user.sign_in_provider,
            )
            self.db.commit()
            self.db.refresh(user)
            return user
        except Exception:
            self.db.rollback()
            raise

    def get_me(self, auth_user: AuthenticatedUser) -> MeResponse:
        user = self.get_or_create_authenticated_user(auth_user)
        return MeResponse.model_validate(user)