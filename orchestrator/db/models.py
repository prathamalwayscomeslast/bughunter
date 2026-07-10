import uuid
from datetime import datetime, UTC
from sqlalchemy import Column, String, Integer, Text, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class JobStatus:
    """All valid Job.status values, in lifecycle order."""
    RECEIVED = "received"
    REPRODUCING = "reproducing"
    LOCALIZING = "localizing"
    FIXING = "fixing"
    PR_OPENED = "pr_opened"
    FAILED = "failed"
    UNREPRODUCIBLE = "unreproducible"


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    provider = Column(String, default="github")
    installation_id = Column(Integer, nullable=False)
    repo_full_name = Column(String, nullable=False)
    issue_number = Column(Integer, nullable=False)
    issue_title = Column(Text)
    issue_body = Column(Text)
    status = Column(String, default=JobStatus.RECEIVED)
    # Number of fix attempts made so far in the repair loop.
    repair_attempts = Column(Integer, default=0)
    # Free-text diagnosis written by the worker when the repair loop is exhausted.
    diagnosis = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
