# file: CUZ/core/firebase.py

import os
import json
import base64
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

# Expect the base64-encoded JSON string in env var
FIREBASE_SERVICE_ACCOUNT_BASE64 = os.getenv("FIREBASE_SERVICE_ACCOUNT_BASE64")

# ------------------------------
# Firebase Admin initialization
# ------------------------------
if not FIREBASE_SERVICE_ACCOUNT_BASE64:
    logger.error("FIREBASE_SERVICE_ACCOUNT_BASE64 env var not set")
    raise FileNotFoundError("FIREBASE_SERVICE_ACCOUNT_BASE64 env var not set")

try:
    # Decode base64 back into JSON
    decoded_json = base64.b64decode(FIREBASE_SERVICE_ACCOUNT_BASE64).decode("utf-8")
    firebase_cred_dict = json.loads(decoded_json)
    firebase_cred = credentials.Certificate(firebase_cred_dict)

    if not firebase_admin._apps:  # Prevent re-init
        app = firebase_admin.initialize_app(firebase_cred, {
            "projectId": FIREBASE_PROJECT_ID,
            "storageBucket": FIREBASE_BUCKET
        })
        logger.info("🔥 Firebase initialized with project: %s", app.project_id)

    # Firestore client via Firebase Admin
    db = firestore.client()
    logger.info("🔥 Firestore client project: %s", db.project)

    # Storage bucket client via Firebase Admin
    bucket = storage.bucket()
    logger.info("🔥 Firebase Storage bucket initialized: %s", bucket.name)

except Exception as e:
    logger.exception("Failed to initialize Firebase: %s", e)
    raise

# ------------------------------
# Exports
# ------------------------------
__all__ = ["db", "bucket"]
