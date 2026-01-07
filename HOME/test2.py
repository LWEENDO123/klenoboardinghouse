from firebase_admin import credentials, firestore, initialize_app
from datetime import datetime

# 🔐 Initialize Firebase
cred = credentials.Certificate("C:/Users/lweendo/project/baodinghouse/CUZ/core/serviceAccountKey.json")
initialize_app(cred)
db = firestore.client()

# 🏫 Set university
university = "CUZ"
ref = db.collection("HOME").document(university).collection("boardinghouse")
results = ref.stream()

print(f"\n📍 Available boarding houses in {university}:\n")

found = False
for doc in results:
    data = doc.to_dict()

    if any([
        data.get("singleroom") == "available",
        data.get("sharedroom_2") == "available",
        data.get("sharedroom_3") == "available",
        data.get("sharedroom_4") == "available"
    ]):
        found = True
        gender = (
            "Male" if data.get("gender_male") else
            "Female" if data.get("gender_female") else
            "Male/Female" if data.get("gender_both") else "Unspecified"
        )

        print(f"🏠 {data.get('name')}")
        print(f"📍 Location: {data.get('location')}")
        print(f"🧍 Gender: {gender}")
        print(f"🖼️ Images: {data.get('images', [])}")
        print(f"🆔 ID: {doc.id}")
        print("-" * 40)

if not found:
    print("❌ No available boarding houses found.")
