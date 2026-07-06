import hmac
import hashlib
from config import WEBHOOK_SECRET

def verify_github_signature(payload: bytes, signature_header: str | None) -> bool:
    if not signature_header:
        return False
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode("utf-8"), msg=payload, digestmod=hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def is_bug_labeled_event(event_type: str, payload: dict) -> bool:
    if event_type != "issues" or payload.get("action") != "labeled":
        return False
    return payload.get("label", {}).get("name") == "bug"