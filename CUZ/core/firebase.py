# file: CUZ/core/firebase.py

import os
import json
import firebase_admin
from firebase_admin import credentials, firestore, storage

# ------------------------------
# Environment variables
# ------------------------------
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "boardinghouse-af901")
FIREBASE_BUCKET = os.getenv("FIREBASE_BUCKET", f"{FIREBASE_PROJECT_ID}.appspot.com")

# Expect the full JSON string in env var
FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT")

# ------------------------------
# Firebase Admin initialization
# ------------------------------
if not FIREBASE_SERVICE_ACCOUNT_JSON:
    raise FileNotFoundError("FIREBASE_SERVICE_ACCOUNT env var not set")

firebase_cred_dict = json.loads(FIREBASE_SERVICE_ACCOUNT_JSON)
firebase_cred = credentials.Certificate(firebase_cred_dict)

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
# Exports
# ------------------------------
__all__ = ["db", "bucket"]
