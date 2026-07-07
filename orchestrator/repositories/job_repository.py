from sqlalchemy.orm import Session
from db.models import Job

class JobRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_job(
            self,
            installation_id: int,
            repo_full_name: str,
            issue_number: int,
            issue_title: str,
            issue_body: str,
    ) -> Job:
        job = Job(
            installation_id=installation_id,
            repo_full_name=repo_full_name,
            issue_number=issue_number,
            issue_title=issue_title,
            issue_body=issue_body,
            status="received",
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_by_id(self, job_id: str) -> Job | None:
        return self.db.query(Job).filter(Job.id == job_id).first()

    def update_status(self, job_id: str, status: str) -> None:
        job = self.get_by_id(job_id)
        if job:
            job.status = status
            self.db.commit()