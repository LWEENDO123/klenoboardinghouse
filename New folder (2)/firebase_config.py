import os
import firebase_admin
from firebase_admin import credentials, firestore

# Dynamically build the path to your key
key_path = os.path.join(os.path.dirname(__file__), "..", "..", "C://Users//lweendo//project//baodinghouse//CUZ//core\serviceAccountKey.json ")

# Initialize Firebase app
cred = credentials.Certificate(key_path)
firebase_admin.initialize_app(cred)

# Shared Firestore DB instance
db = firestore.client()
