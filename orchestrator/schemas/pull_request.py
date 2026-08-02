from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PullRequestListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    github_pr_id: int
    pr_number: int
    title: str
    repo_id: str
    repo_full_name: str
    html_url: str
    status: Literal["open", "merged", "closed"]
    source_issue_number: int | None = None
    source_job_id: str | None = None
    opened_at: datetime
    updated_at: datetime


class PullRequestPreviewItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    pr_number: int
    title: str
    repo_full_name: str
    status: Literal["open", "merged", "closed"]
    opened_at: datetime


class PullRequestQueryParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    repo_id: str | None = None
    status: Literal["open", "merged", "closed"] | None = None
    sort: Literal["opened_at", "updated_at"] = "updated_at"
    order: Literal["asc", "desc"] = "desc"