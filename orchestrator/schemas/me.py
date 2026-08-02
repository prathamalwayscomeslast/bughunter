from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class MeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    firebase_uid: str
    email: EmailStr | None = None
    email_verified: bool = False
    display_name: str | None = None
    photo_url: str | None = None
    sign_in_provider: str | None = None
    created_at: datetime
    updated_at: datetime