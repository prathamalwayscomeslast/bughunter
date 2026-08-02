from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RepositoryVisibility(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"


class RepositoryListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    github_repo_id: int
    installation_id: int
    full_name: str
    owner: str
    name: str
    visibility: Literal["public", "private"]
    html_url: str
    active_issue_count: int = Field(ge=0, default=0)
    active_job_count: int = Field(ge=0, default=0)
    open_pr_count: int = Field(ge=0, default=0)
    last_activity_at: datetime | None = None
    installed_at: datetime


class RepositoryPreviewItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    full_name: str
    active_job_count: int = Field(ge=0, default=0)
    open_pr_count: int = Field(ge=0, default=0)
    last_activity_at: datetime | None = None


class RepositoryQueryParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    search: str | None = None
    visibility: Literal["public", "private"] | None = None
    sort: Literal["installed_at", "last_activity_at", "full_name"] = "last_activity_at"
    order: Literal["asc", "desc"] = "desc"