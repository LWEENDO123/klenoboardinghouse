# CUZ/core/firebase_config.py
'''
import os
import firebase_admin
from firebase_admin import credentials, firestore as fb_firestore, storage
from google.cloud import firestore as gcp_firestore
from google.oauth2 import service_account

# ------------------------------
# Env variables (with safe defaults)
# ------------------------------
FIREBASE_KEY_PATH = os.getenv("FIREBASE_KEY_PATH")  # Path to Firebase Admin SDK JSON
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "boardinghouse-af901")
FIREBASE_BUCKET = os.getenv("FIREBASE_BUCKET", f"{FIREBASE_PROJECT_ID}.appspot.com")

GCP_SERVICE_ACCOUNT_FILE = os.getenv("GCP_SERVICE_ACCOUNT_FILE")  # Path to GCP service account JSON
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", FIREBASE_PROJECT_ID)

# ------------------------------
# Validation
# ------------------------------
if not FIREBASE_KEY_PATH or not os.path.exists(FIREBASE_KEY_PATH):
    raise FileNotFoundError(f"Firebase service account key not found at: {FIREBASE_KEY_PATH or '<unset>'}")

if not GCP_SERVICE_ACCOUNT_FILE or not os.path.exists(GCP_SERVICE_ACCOUNT_FILE):
    raise FileNotFoundError(f"GCP service account key not found at: {GCP_SERVICE_ACCOUNT_FILE or '<unset>'}")

# ------------------------------
# Firebase Admin (for Firebase SDK features)
# ------------------------------
firebase_cred = credentials.Certificate(FIREBASE_KEY_PATH)
if not firebase_admin._apps:  # Prevent re-init if already done
    app = firebase_admin.initialize_app(firebase_cred, {
        "projectId": FIREBASE_PROJECT_ID,
        "storageBucket": FIREBASE_BUCKET,
    })
    print("🔥 firebase_config initialized with project:", app.project_id)

# Shared Firestore DB instance via Firebase Admin
firebase_db = fb_firestore.client()
print("🔥 firebase_config Firebase Admin client project:", firebase_db.project)

# Optional: Firebase Storage bucket
bucket = storage.bucket()
print("🔥 firebase_config Firebase Storage bucket:", bucket.name)

# ------------------------------
# Google Cloud Firestore (direct client)
# ------------------------------
gcp_credentials = service_account.Credentials.from_service_account_file(GCP_SERVICE_ACCOUNT_FILE)

# Direct Firestore client with explicit credentials
gcp_db = gcp_firestore.Client(credentials=gcp_credentials, project=GCP_PROJECT_ID)
print("🔥 firebase_config GCP Firestore client project:", gcp_db.project)

# ------------------------------
# Exports
# ------------------------------
__all__ = ["firebase_db", "bucket", "gcp_db"]


'''
