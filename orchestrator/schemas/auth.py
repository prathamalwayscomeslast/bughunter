from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr


class AuthenticatedUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    firebase_uid: str
    email: EmailStr | None = None
    email_verified: bool = False
    display_name: str | None = None
    photo_url: str | None = None
    sign_in_provider: str | None = None
    issuer: str | None = None
    audience: str | None = None