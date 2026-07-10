import json
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from db.session import SessionLocal
from vcs.webhook import verify_github_signature
from schemas.webhook_events import IssueLabeledPayload
from services.job_service import JobService

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    event_type = request.headers.get("X-GitHub-Event")

    if not verify_github_signature(raw_body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload_dict = json.loads(raw_body.decode("utf-8"))

    if event_type == "issues" and payload_dict.get("action") == "labeled":
        label_name = payload_dict.get("label", {}).get("name")

        if label_name == "bug":
            payload = IssueLabeledPayload(**payload_dict)

            job_service = JobService(db)
            await job_service.handle_bug_issue(
                installation_id=payload.installation.id,
                repo_full_name=payload.repository.full_name,
                issue_number=payload.issue.number,
                issue_title=payload.issue.title,
                issue_body=payload.issue.body,
            )

    return {"received": True}