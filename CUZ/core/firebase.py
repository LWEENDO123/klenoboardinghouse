# file: CUZ/core/firebase.py

import os
import json
import logging
import firebase_admin
from firebase_admin import credentials, firestore, storage

# ------------------------------
# Logging setup
# ------------------------------
logger = logging.getLogger("core.firebase")
logger.setLevel(logging.INFO)

# ------------------------------
# Environment variables
# ------------------------------
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "boardinghouse-af901")
FIREBASE_BUCKET = os.getenv("FIREBASE_BUCKET", f"{FIREBASE_PROJECT_ID}.appspot.com")
FIREBASE_CREDENTIAL_JSON = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

# ------------------------------
# Firebase Admin initialization (force JSON from env)
# ------------------------------
try:
    if not FIREBASE_CREDENTIAL_JSON:
        raise ValueError("GOOGLE_APPLICATION_CREDENTIALS env var is not set")

    # Parse the raw JSON string directly
    firebase_cred_dict = json.loads(FIREBASE_CREDENTIAL_JSON)
    cred = credentials.Certificate(firebase_cred_dict)

    if not firebase_admin._apps:
        app = firebase_admin.initialize_app(cred, {
            "projectId": FIREBASE_PROJECT_ID,
            "storageBucket": FIREBASE_BUCKET
        })
        logger.info("🔥 Firebase initialized with project: %s", app.project_id)

    db = firestore.client()
    logger.info("🔥 Firestore client project: %s", db.project)

    bucket = storage.bucket()
    logger.info("🔥 Firebase Storage bucket initialized: %s", bucket.name)

except Exception as e:
    logger.exception("Failed to initialize Firebase: %s", e)
    raise

# ------------------------------
# Exports
# ------------------------------
__all__ = ["db", "bucket"]
