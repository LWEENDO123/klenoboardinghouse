# file: CUZ/core/firebase.py

import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

# ------------------------------
# Environment variable
# ------------------------------
# Expect the full JSON string in FIREBASE_SERVICE_ACCOUNT
firebase_service_account = os.getenv("FIREBASE_SERVICE_ACCOUNT")

if not firebase_service_account:
    raise FileNotFoundError("FIREBASE_SERVICE_ACCOUNT env var not set")

# Parse JSON string into dict
cred_dict = json.loads(firebase_service_account)

# Initialize Firebase app
cred = credentials.Certificate(cred_dict)
if not firebase_admin._apps:  # Prevent re-init
    firebase_admin.initialize_app(cred)

# Shared Firestore DB instance
db = firestore.client()
