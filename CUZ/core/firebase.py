# file: CUZ/core/firebase.py

import os
import json
import base64
import logging
import firebase_admin
from firebase_admin import credentials, firestore, storage

logger = logging.getLogger("core.firebase")
logger.setLevel(logging.INFO)

FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "boardinghouse-af901")
FIREBASE_BUCKET = os.getenv("FIREBASE_BUCKET", f"{FIREBASE_PROJECT_ID}.appspot.com")
FIREBASE_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

try:
    if not FIREBASE_CREDENTIALS:
        raise ValueError("GOOGLE_APPLICATION_CREDENTIALS env var is not set")

    cred = None

    # Try raw JSON
    try:
        firebase_cred_dict = json.loads(FIREBASE_CREDENTIALS)
        cred = credentials.Certificate(firebase_cred_dict)
        logger.info("Using raw JSON credentials from env")
    except json.JSONDecodeError:
        # Try base64‑encoded JSON
        try:
            decoded = base64.b64decode(FIREBASE_CREDENTIALS).decode("utf-8")
            firebase_cred_dict = json.loads(decoded)
            cred = credentials.Certificate(firebase_cred_dict)
            logger.info("Using base64‑encoded JSON credentials from env")
        except Exception:
            # Fallback: treat as file path
            if not os.path.isfile(FIREBASE_CREDENTIALS):
                raise FileNotFoundError(f"Credential file not found: {FIREBASE_CREDENTIALS}")
            cred = credentials.Certificate(FIREBASE_CREDENTIALS)
            logger.info("Using credential file path: %s", FIREBASE_CREDENTIALS)

    if not firebase_admin._apps:
        app = firebase_admin.initialize_app(cred, {
            "projectId": FIREBASE_PROJECT_ID,
            "storageBucket": FIREBASE_BUCKET
        })
        logger.info("🔥 Firebase initialized with project: %s", app.project_id)

    db = firestore.client()
    bucket = storage.bucket()

except Exception as e:
    logger.exception("Failed to initialize Firebase: %s", e)
    raise

__all__ = ["db", "bucket"]
