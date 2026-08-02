from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


JobStatus = Literal[
    "received",
    "analyzing",
    "localizing",
    "patch_generating",
    "pr_opened",
    "failed",
]

VerificationStatus = Literal[
    "skipped",
    "pending",
    "passed",
    "failed",
    "not_attempted",
]


class JobListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    repo_id: str
    repo_full_name: str
    installation_id: int
    issue_number: int
    issue_title: str
    status: JobStatus
    verification_status: VerificationStatus
    attempt_count: int = Field(ge=0, default=0)
    max_attempts: int = Field(ge=1, default=5)
    pr_number: int | None = None
    pr_url: str | None = None
    created_at: datetime
    updated_at: datetime


class JobPreviewItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    repo_full_name: str
    issue_number: int
    issue_title: str
    status: JobStatus
    verification_status: VerificationStatus
    updated_at: datetime


class JobDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    repo_id: str
    repo_full_name: str
    installation_id: int
    issue_number: int
    issue_title: str
    status: JobStatus
    verification_status: VerificationStatus
    attempt_count: int = Field(ge=0, default=0)
    max_attempts: int = Field(ge=1, default=5)
    diagnosis: str | None = None
    pr_number: int | None = None
    pr_url: str | None = None
    created_at: datetime
    updated_at: datetime


class JobQueryParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    repo_id: str | None = None
    status: JobStatus | None = None
    verification_status: VerificationStatus | None = None
    active_only: bool = False
    sort: Literal["created_at", "updated_at"] = "updated_at"
    order: Literal["asc", "desc"] = "desc"