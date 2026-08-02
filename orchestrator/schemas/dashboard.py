from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from orchestrator.schemas.issue import IssuePreviewItem
from orchestrator.schemas.job import JobPreviewItem
from orchestrator.schemas.pull_request import PullRequestPreviewItem
from orchestrator.schemas.repository import RepositoryPreviewItem


class DashboardSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_repositories: int = Field(ge=0, default=0)
    active_issues: int = Field(ge=0, default=0)
    active_jobs: int = Field(ge=0, default=0)
    open_pull_requests: int = Field(ge=0, default=0)


class DashboardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    summary: DashboardSummaryResponse
    repositories: list[RepositoryPreviewItem]
    issues: list[IssuePreviewItem]
    jobs: list[JobPreviewItem]
    pull_requests: list[PullRequestPreviewItem]