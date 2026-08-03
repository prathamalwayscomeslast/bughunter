import uuid
from datetime import datetime, UTC

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base
from db.enums import (
    JobStatus,
    PullRequestStatus,
    RepositoryVisibility,
)


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_repo_status_updated_at", "repository_id", "status", "updated_at"),
        Index("ix_jobs_installation_issue", "installation_id", "issue_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String(50), default="github", nullable=False)

    repository_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("repositories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    installation_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    repo_full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    issue_number: Mapped[int] = mapped_column(Integer, nullable=False)
    issue_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    issue_body: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[JobStatus] = mapped_column(
        SqlEnum(JobStatus, name="job_status"),
        default=JobStatus.RECEIVED,
        nullable=False,
    )

    repair_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    diagnosis: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_files: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    pr_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    repository: Mapped["Repository | None"] = relationship(back_populates="jobs")
    pull_requests: Mapped[list["PullRequest"]] = relationship(
        back_populates="source_job",
        cascade="save-update",
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    firebase_uid: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), index=True, nullable=True)
    email_verified: Mapped[bool] = mapped_column(default=False, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    sign_in_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    repository_accesses: Mapped[list["UserRepositoryAccess"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("github_repo_id", name="uq_repositories_github_repo_id"),
        UniqueConstraint("full_name", name="uq_repositories_full_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    github_repo_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    installation_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    visibility: Mapped[RepositoryVisibility] = mapped_column(
        SqlEnum(RepositoryVisibility, name="repository_visibility"),
        nullable=False,
    )
    html_url: Mapped[str] = mapped_column(Text, nullable=False)

    installed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    user_accesses: Mapped[list["UserRepositoryAccess"]] = relationship(
        back_populates="repository",
        cascade="all, delete-orphan",
    )
    jobs: Mapped[list["Job"]] = relationship(
        back_populates="repository",
        cascade="all, delete-orphan",
    )
    pull_requests: Mapped[list["PullRequest"]] = relationship(
        back_populates="repository",
        cascade="all, delete-orphan",
    )


class UserRepositoryAccess(Base):
    __tablename__ = "user_repository_access"
    __table_args__ = (
        UniqueConstraint("user_id", "repository_id", name="uq_user_repository_access"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repository_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="repository_accesses")
    repository: Mapped["Repository"] = relationship(back_populates="user_accesses")


class PullRequest(Base):
    __tablename__ = "pull_requests"
    __table_args__ = (
        UniqueConstraint("github_pr_id", name="uq_pull_requests_github_pr_id"),
        UniqueConstraint("repository_id", "pr_number", name="uq_pull_requests_repo_pr_number"),
        Index("ix_pull_requests_repo_status_updated_at", "repository_id", "status", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    github_pr_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    repository_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    html_url: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[PullRequestStatus] = mapped_column(
        SqlEnum(PullRequestStatus, name="pull_request_status"),
        default=PullRequestStatus.OPEN,
        nullable=False,
    )

    source_issue_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_job_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    repository: Mapped["Repository"] = relationship(back_populates="pull_requests")
    source_job: Mapped["Job | None"] = relationship(back_populates="pull_requests")