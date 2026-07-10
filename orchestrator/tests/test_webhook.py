"""Unit tests for webhook signature verification and event routing."""
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

# Minimal env is set by CI via environment variables before import.
from main import app

client = TestClient(app)

WEBHOOK_SECRET = "test-secret"


def _sign(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def test_healthz():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_webhook_rejects_bad_signature():
    body = b'{"action": "labeled"}'
    response = client.post(
        "/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": "sha256=badsignature",
            "X-GitHub-Event": "issues",
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 401


def test_webhook_accepts_non_bug_label():
    """A labeled event with a non-bug label should return 200 and do nothing."""
    payload = {
        "action": "labeled",
        "label": {"name": "enhancement"},
        "issue": {"number": 1, "title": "test", "body": "test"},
        "repository": {"full_name": "owner/repo"},
        "installation": {"id": 123},
    }
    body = json.dumps(payload).encode()
    response = client.post(
        "/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": _sign(body),
            "X-GitHub-Event": "issues",
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"received": True}
