import uuid
from datetime import datetime, UTC
from sqlalchemy import Column, String, Integer, Text, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    provider = Column(String, default="github")
    installation_id = Column(Integer, nullable=False)
    repo_full_name = Column(String, nullable=False)
    issue_number = Column(Integer, nullable=False)
    issue_title = Column(Text)
    issue_body = Column(Text)
    status = Column(String, default="received")
    created_at = Column(DateTime, default=datetime.now(UTC))
    updated_at = Column(DateTime, default=datetime.now(UTC))