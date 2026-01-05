# file: CUZ/core/firebase.py

import os
import firebase_admin
from firebase_admin import credentials, firestore, storage
from google.cloud import firestore as gcp_firestore
from google.oauth2 import service_account

# ------------------------------
# Environment variables
# ------------------------------
FIREBASE_KEY_PATH = os.getenv("FIREBASE_KEY_PATH")  # Path to Firebase Admin SDK JSON
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "boardinghouse-af901")
FIREBASE_BUCKET = os.getenv("FIREBASE_BUCKET", f"{FIREBASE_PROJECT_ID}.appspot.com")

GCP_SERVICE_ACCOUNT_FILE = os.getenv("GCP_SERVICE_ACCOUNT_FILE")  # Path to GCP service account JSON
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", FIREBASE_PROJECT_ID)

# ------------------------------
# Firebase Admin initialization
# ------------------------------
if not FIREBASE_KEY_PATH or not os.path.exists(FIREBASE_KEY_PATH):
    raise FileNotFoundError(f"Firebase service account key not found at: {FIREBASE_KEY_PATH or '<unset>'}")

firebase_cred = credentials.Certificate(FIREBASE_KEY_PATH)
if not firebase_admin._apps:  # Prevent re-init
    app = firebase_admin.initialize_app(firebase_cred, {
        "projectId": FIREBASE_PROJECT_ID,
        "storageBucket": FIREBASE_BUCKET
    })
    print("🔥 Firebase initialized with project:", app.project_id)

# Firestore client via Firebase Admin
db = firestore.client()
print("🔥 Firestore client project:", db.project)

# Storage bucket client via Firebase Admin
bucket = storage.bucket()
print("🔥 Firebase Storage bucket initialized:", bucket.name)

# ------------------------------
# Direct GCP Firestore client
# ------------------------------
if not GCP_SERVICE_ACCOUNT_FILE or not os.path.exists(GCP_SERVICE_ACCOUNT_FILE):
    raise FileNotFoundError(f"GCP service account key not found at: {GCP_SERVICE_ACCOUNT_FILE or '<unset>'}")

gcp_credentials = service_account.Credentials.from_service_account_file(GCP_SERVICE_ACCOUNT_FILE)

# Direct Firestore client with explicit credentials
gcp_db = gcp_firestore.Client(credentials=gcp_credentials, project=GCP_PROJECT_ID)
print("🔥 GCP Firestore client project:", gcp_db.project)

# ------------------------------
# Exports
# ------------------------------
__all__ = ["db", "bucket", "gcp_db"]
