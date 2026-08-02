from __future__ import annotations

from enum import Enum


class RepositoryVisibility(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"


class JobStatus(str, Enum):
    FIXING = "fixing"
    REPRODUCING = "reproducing"
    RECEIVED = "received"
    ANALYZING = "analyzing"
    LOCALIZING = "localizing"
    PATCH_GENERATING = "patch_generating"
    PR_OPENED = "pr_opened"
    FAILED = "failed"


class VerificationStatus(str, Enum):
    SKIPPED = "skipped"
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    NOT_ATTEMPTED = "not_attempted"


class PullRequestStatus(str, Enum):
    OPEN = "open"
    MERGED = "merged"
    CLOSED = "closed"