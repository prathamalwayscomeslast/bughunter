from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from orchestrator.db.models import User


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, user_id: str) -> User | None:
        return self.db.get(User, user_id)

    def get_by_firebase_uid(self, firebase_uid: str) -> User | None:
        stmt = select(User).where(User.firebase_uid == firebase_uid)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        return self.db.execute(stmt).scalar_one_or_none()

    def create(
            self,
            *,
            firebase_uid: str,
            email: str | None,
            email_verified: bool,
            display_name: str | None,
            photo_url: str | None,
            sign_in_provider: str | None,
    ) -> User:
        user = User(
            firebase_uid=firebase_uid,
            email=email,
            email_verified=email_verified,
            display_name=display_name,
            photo_url=photo_url,
            sign_in_provider=sign_in_provider,
        )
        self.db.add(user)
        self.db.flush()
        self.db.refresh(user)
        return user

    def update_from_auth(
            self,
            user: User,
            *,
            email: str | None,
            email_verified: bool,
            display_name: str | None,
            photo_url: str | None,
            sign_in_provider: str | None,
    ) -> User:
        user.email = email
        user.email_verified = email_verified
        user.display_name = display_name
        user.photo_url = photo_url
        user.sign_in_provider = sign_in_provider
        self.db.flush()
        self.db.refresh(user)
        return user

    def get_or_create_from_auth(
            self,
            *,
            firebase_uid: str,
            email: str | None,
            email_verified: bool,
            display_name: str | None,
            photo_url: str | None,
            sign_in_provider: str | None,
    ) -> User:
        existing = self.get_by_firebase_uid(firebase_uid)
        if existing:
            return self.update_from_auth(
                existing,
                email=email,
                email_verified=email_verified,
                display_name=display_name,
                photo_url=photo_url,
                sign_in_provider=sign_in_provider,
            )

        return self.create(
            firebase_uid=firebase_uid,
            email=email,
            email_verified=email_verified,
            display_name=display_name,
            photo_url=photo_url,
            sign_in_provider=sign_in_provider,
        )