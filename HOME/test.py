import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate("C:/Users/lweendo/project/baodinghouse/CUZ/core/\serviceAccountKey.json")
firebase_admin.initialize_app(cred)

db = firestore.client()

ref = db.collection("HOME").document("CUZ").collection("boardinghouse")
results = ref.stream()

for doc in results:
    print(doc.id, doc.to_dict())
