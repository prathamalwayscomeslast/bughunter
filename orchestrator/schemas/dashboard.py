from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from schemas.issue import IssuePreviewItem
from schemas.job import JobPreviewItem
from schemas.pull_request import PullRequestPreviewItem
from schemas.repository import RepositoryPreviewItem


class DashboardSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_repositories: int = Field(ge=0, default=0)
    open_issues: int = Field(ge=0, default=0)
    active_jobs: int = Field(ge=0, default=0)
    open_pull_requests: int = Field(ge=0, default=0)


class DashboardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    summary: DashboardSummaryResponse
    recent_repositories: list[RepositoryPreviewItem]
    recent_issues: list[IssuePreviewItem]
    recent_jobs: list[JobPreviewItem]
    recent_pull_requests: list[PullRequestPreviewItem]