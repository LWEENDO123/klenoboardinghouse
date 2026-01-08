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

# ------------------------------
# Firebase Admin initialization (Application Default Credentials)
# ------------------------------
try:
    # Use ADC — GOOGLE_APPLICATION_CREDENTIALS must point to a valid JSON file
    cred = credentials.ApplicationDefault()

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
