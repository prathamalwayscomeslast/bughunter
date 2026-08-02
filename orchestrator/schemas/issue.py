from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class IssueStatus(str):
    OPEN = "open"
    CLOSED = "closed"


class IssueListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    github_issue_id: int
    issue_number: int
    title: str
    repo_id: str
    repo_full_name: str
    html_url: str
    status: Literal["open", "closed"]
    bughunter_job_status: str | None = None
    verification_status: str | None = None
    created_at: datetime
    updated_at: datetime


class IssuePreviewItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    issue_number: int
    title: str
    repo_full_name: str
    bughunter_job_status: str | None = None
    created_at: datetime


class IssueQueryParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    repo_id: str | None = None
    status: Literal["open", "closed"] | None = None
    bughunter_job_status: str | None = None
    sort: Literal["created_at", "updated_at"] = "updated_at"
    order: Literal["asc", "desc"] = "desc"