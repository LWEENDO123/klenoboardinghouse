# file: CUZ/core/firebase.py

import os
import json
import logging
import firebase_admin
from firebase_admin import credentials, firestore

import boto3
from botocore.client import Config

logger = logging.getLogger("core.firebase")
logger.setLevel(logging.INFO)

# ------------------------------
# Firestore (Firebase for text data)
# ------------------------------
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "boardinghouse-af901")
CREDENTIAL_SOURCE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

try:
    if not CREDENTIAL_SOURCE:
        raise ValueError("GOOGLE_APPLICATION_CREDENTIALS env var is not set")

    # Case 1: it's a file path
    if os.path.exists(CREDENTIAL_SOURCE):
        logger.info("Loading Firebase credentials from file: %s", CREDENTIAL_SOURCE)
        cred = credentials.Certificate(CREDENTIAL_SOURCE)
    else:
        # Case 2: it's a raw JSON string
        logger.info("Loading Firebase credentials from raw JSON string")
        cred_dict = json.loads(CREDENTIAL_SOURCE)
        cred = credentials.Certificate(cred_dict)

    if not firebase_admin._apps:
        app = firebase_admin.initialize_app(cred, {
            "projectId": FIREBASE_PROJECT_ID,
        })
        logger.info("🔥 Firebase initialized with project: %s", app.project_id)

    db = firestore.client()
    logger.info("🔥 Firestore client project: %s", db.project)

except Exception as e:
    logger.exception("Failed to initialize Firebase Firestore: %s", e)
    raise

# ------------------------------
# Railway S3 Storage (for images/videos)
# ------------------------------
RAILWAY_BUCKET = os.getenv("RAILWAY_BUCKET", "boardinghouse-bucket")
RAILWAY_ENDPOINT = os.getenv("RAILWAY_ENDPOINT")  # e.g. https://your-railway-s3-endpoint
RAILWAY_ACCESS_KEY = os.getenv("RAILWAY_ACCESS_KEY")
RAILWAY_SECRET_KEY = os.getenv("RAILWAY_SECRET_KEY")

try:
    s3_client = boto3.client(
        "s3",
        endpoint_url=RAILWAY_ENDPOINT,
        aws_access_key_id=RAILWAY_ACCESS_KEY,
        aws_secret_access_key=RAILWAY_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1"
    )
    logger.info("🔥 Railway S3 client initialized for bucket: %s", RAILWAY_BUCKET)
except Exception as e:
    logger.exception("Failed to initialize Railway S3 client: %s", e)
    raise

# ------------------------------
# Exports
# ------------------------------
__all__ = ["db", "s3_client", "RAILWAY_BUCKET"]
