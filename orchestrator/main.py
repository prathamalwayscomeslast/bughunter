import json
import logging

from fastapi import FastAPI, Request, HTTPException
from util.logging import setup_logging
from vcs.webhook import verify_github_signature, is_bug_labeled_event
from vcs.client import comment_on_issue

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI()

@app.get("/healthz")
def health():
    return {"status": "ok"}

@app.post("/webhook")
async def webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    event_type = request.headers.get("X-GitHub-Event")

    if not verify_github_signature(raw_body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = json.loads(raw_body.decode("utf-8"))

    if is_bug_labeled_event(event_type, payload):
        try:
            installation_id = payload["installation"]["id"]
            issue = payload["issue"]
            repo_full_name = payload["repository"]["full_name"]

            comment_on_issue(
                installation_id=installation_id,
                repo_full_name=repo_full_name,
                issue_number=issue["number"],
                message="BugHunter picked up this issue and is preparing to reproduce it!"
            )
        except Exception as e:
            logger.exception("GitHub App comment failed: %s", e)

    return {"received": True}

@app.get("/hetal")
async def hetal():
    return {"hetal": "hiii"}