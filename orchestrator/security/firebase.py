from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

import firebase_admin
from firebase_admin import auth, credentials
from firebase_admin.exceptions import FirebaseError


class FirebaseInitializationError(RuntimeError):
    """Raised when Firebase Admin SDK cannot be initialized."""


class FirebaseTokenVerificationError(RuntimeError):
    """Raised when an incoming Firebase ID token is invalid."""


def _load_firebase_credentials() -> credentials.Base:
    """
    Load Firebase service account credentials from one of:
    1. FIREBASE_SERVICE_ACCOUNT_JSON  -> raw JSON string
    2. FIREBASE_SERVICE_ACCOUNT_PATH  -> path to service account JSON file
    """
    raw_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    if raw_json:
        try:
            payload = json.loads(raw_json)
            return credentials.Certificate(payload)
        except json.JSONDecodeError as exc:
            raise FirebaseInitializationError(
                "FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON."
            ) from exc

    file_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")
    if file_path:
        if not os.path.exists(file_path):
            raise FirebaseInitializationError(
                f"Firebase service account file not found: {file_path}"
            )
        return credentials.Certificate(file_path)

    raise FirebaseInitializationError(
        "Missing Firebase credentials. Set either "
        "FIREBASE_SERVICE_ACCOUNT_JSON or FIREBASE_SERVICE_ACCOUNT_PATH."
    )


@lru_cache(maxsize=1)
def get_firebase_app() -> firebase_admin.App:
    """
    Initialize Firebase Admin SDK once and reuse the app instance.
    """
    try:
        existing_app = firebase_admin.get_app()
        return existing_app
    except ValueError:
        pass

    cred = _load_firebase_credentials()

    project_id = os.getenv("FIREBASE_PROJECT_ID")
    options: dict[str, Any] = {}
    if project_id:
        options["projectId"] = project_id

    try:
        return firebase_admin.initialize_app(cred, options=options or None)
    except Exception as exc:
        raise FirebaseInitializationError(
            f"Failed to initialize Firebase Admin SDK: {exc}"
        ) from exc


def verify_firebase_token(id_token: str) -> dict[str, Any]:
    """
    Verify and decode a Firebase ID token.

    Returns decoded claims if valid.
    Raises FirebaseTokenVerificationError if invalid/expired/malformed.
    """
    if not id_token or not id_token.strip():
        raise FirebaseTokenVerificationError("Missing Firebase ID token.")

    get_firebase_app()

    try:
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token
    except (auth.InvalidIdTokenError, auth.ExpiredIdTokenError) as exc:
        raise FirebaseTokenVerificationError("Invalid or expired Firebase ID token.") from exc
    except auth.RevokedIdTokenError as exc:
        raise FirebaseTokenVerificationError("Firebase ID token has been revoked.") from exc
    except auth.CertificateFetchError as exc:
        raise FirebaseTokenVerificationError(
            "Unable to verify Firebase ID token because public certificates could not be fetched."
        ) from exc
    except FirebaseError as exc:
        raise FirebaseTokenVerificationError(
            f"Firebase token verification failed: {exc}"
        ) from exc
    except Exception as exc:
        raise FirebaseTokenVerificationError(
            "Unexpected error during Firebase token verification."
        ) from exc


def extract_identity(decoded_token: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize the subset of Firebase claims we care about.
    """
    firebase_claims = decoded_token.get("firebase", {})
    identities = firebase_claims.get("identities", {})

    return {
        "uid": decoded_token.get("uid"),
        "email": decoded_token.get("email"),
        "email_verified": decoded_token.get("email_verified", False),
        "name": decoded_token.get("name"),
        "picture": decoded_token.get("picture"),
        "issuer": decoded_token.get("iss"),
        "audience": decoded_token.get("aud"),
        "auth_time": decoded_token.get("auth_time"),
        "sign_in_provider": firebase_claims.get("sign_in_provider"),
        "provider_identities": identities,
    }