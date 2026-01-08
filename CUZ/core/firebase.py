# file: CUZ/core/firebase.py

import os
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

# Path to service account JSON (must be mounted in container)
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

# ------------------------------
# Firebase Admin initialization (force JSON file)
# ------------------------------
try:
    if not GOOGLE_CREDENTIALS_PATH or not os.path.exists(GOOGLE_CREDENTIALS_PATH):
        raise FileNotFoundError(
            f"Service account JSON not found at: {GOOGLE_CREDENTIALS_PATH or '<unset>'}"
        )

    cred = credentials.Certificate(GOOGLE_CREDENTIALS_PATH)

    if not firebase_admin._apps:  # Prevent re-init
        app = firebase_admin.initialize_app(cred, {
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
