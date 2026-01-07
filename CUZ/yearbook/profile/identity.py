# file: CUZ/yearbook/profile/identity.py
from fastapi import HTTPException
from CUZ.core.firebase import db   # ✅ fixed import path

async def assert_student_exists(university: str, student_id: str) -> dict:
    ref = db.collection("USERS").document(university).collection("students").document(student_id)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Student not found in USERS")
    return doc.to_dict()

def assert_owns_resource_or_admin(current_user: dict, university: str, student_id: str) -> None:
    if current_user["role"] == "admin":
        return
    if current_user["role"] == "student":
        if current_user.get("user_id") == student_id and current_user.get("university") == university:
            return
    raise HTTPException(status_code=403, detail="You do not have permission for this resource")
