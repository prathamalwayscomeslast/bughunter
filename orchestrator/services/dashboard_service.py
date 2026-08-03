from __future__ import annotations

from sqlalchemy.orm import Session

from repositories.dashboard_repository import DashboardRepository
from schemas.dashboard import (
    DashboardResponse,
    DashboardSummaryResponse,
)
from schemas.issue import IssuePreviewItem
from schemas.job import JobPreviewItem
from schemas.pull_request import PullRequestPreviewItem
from schemas.repository import RepositoryPreviewItem


class DashboardService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.dashboard_repository = DashboardRepository(db)

    def get_summary(self, *, user_id: str) -> DashboardSummaryResponse:
        return DashboardSummaryResponse(
            total_repositories=self.dashboard_repository.count_repositories(user_id=user_id),
            active_issues=self.dashboard_repository.count_active_issues(user_id=user_id),
            active_jobs=self.dashboard_repository.count_active_jobs(user_id=user_id),
            open_pull_requests=self.dashboard_repository.count_open_pull_requests(user_id=user_id),
        )

    def get_dashboard(self, *, user_id: str) -> DashboardResponse:
        summary = self.get_summary(user_id=user_id)

        repositories = [
            RepositoryPreviewItem.model_validate(repo)
            for repo in self.dashboard_repository.list_repository_previews(user_id=user_id, limit=5)
        ]

        jobs = [
            JobPreviewItem.model_validate(job)
            for job in self.dashboard_repository.list_job_previews(user_id=user_id, limit=10)
        ]

        issues = [
            IssuePreviewItem(
                id=job.id,
                issue_number=job.issue_number,
                title=job.issue_title or "",
                repo_full_name=job.repo_full_name,
                bughunter_job_status=job.status.value if hasattr(job.status, "value") else str(job.status),
                created_at=job.created_at,
            )
            for job in self.dashboard_repository.list_issue_previews(user_id=user_id, limit=10)
        ]

        pull_requests = [
            PullRequestPreviewItem.model_validate(pr)
            for pr in self.dashboard_repository.list_pull_request_previews(user_id=user_id, limit=10)
        ]

        return DashboardResponse(
            summary=summary,
            repositories=repositories,
            issues=issues,
            jobs=jobs,
            pull_requests=pull_requests,
        )