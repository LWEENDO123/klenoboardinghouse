import random
import string
import logging
from fastapi import HTTPException
from CUZ.core.firebase import db  # Shared Firestore client from core (no re-init)
  # Shared Firestore client from core (no re-init)




from datetime import datetime, timedelta

logger = logging.getLogger("app.firebase")
logger.setLevel(logging.INFO)

def generate_user_id(first_name: str, last_name: str) -> str:
    prefix = (first_name[0] + last_name[0]).upper() if first_name and last_name else "XX"
    random_digits = ''.join(random.choices(string.digits, k=10))
    return prefix + random_digits

# ---------------------------
# STUDENTS (and routing for union members)
# ---------------------------
async def save_student_to_firebase(student_data: dict, university: str):
    """
    Save a student or union member to Firestore.
    If student_data contains role == 'student_union' or 'union_member', route to union collection.
    Returns True on success, False if email already exists (duplicate).
    Raises HTTPException on unexpected errors.
    """
    try:
        role = student_data.get("role", "student")
        email = student_data.get("email")
        first_name = student_data.get("first_name", "")
        last_name = student_data.get("last_name", "")

        logger.info("save_student_to_firebase called role=%s email=%s university=%s", role, email, university)

        # Route union members to the union helper to keep logic centralized
        if role in ("student_union", "union_member", "union"):
            # normalize role name for union helper
            student_data["role"] = "union_member"
            return await save_union_member_to_firebase(student_data, university)

        # Normal student flow
        students_ref = db.collection("USERS").document(university).collection("students")

        # Check if email exists already in students collection
        query = students_ref.where("email", "==", email).limit(1).stream()
        existing = list(query)
        if existing:
            logger.info("save_student_to_firebase: email already exists in students: %s", email)
            return False

        # Also ensure no union member exists with same email (avoid cross-role collision)
        union_ref = db.collection("USERS").document(university).collection("studentunion")
        union_query = union_ref.where("email", "==", email).limit(1).stream()
        if list(union_query):
            logger.warning("save_student_to_firebase: email exists in union collection, refusing to create student: %s", email)
            return False

        # Generate user id and set fields
        student_id = generate_user_id(first_name, last_name)
        student_data["user_id"] = student_id
        student_data["role"] = "student"

        # Write document
        students_ref.document(student_id).set(student_data)
        logger.info("save_student_to_firebase: wrote student %s to USERS/%s/students/%s", email, university, student_id)
        return True

    except Exception as e:
        logger.exception("save_student_to_firebase failed for email=%s: %s", student_data.get("email"), e)
        raise HTTPException(status_code=500, detail=f"Firebase error: {str(e)}")


async def get_student_by_email(email: str, university: str):
    try:
        students_ref = db.collection("USERS").document(university).collection("students")
        query = students_ref.where("email", "==", email).limit(1).stream()
        for doc in query:
            return doc.to_dict()
        return None
    except Exception as e:
        logger.exception("get_student_by_email failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Firebase error: {str(e)}")


async def get_student_by_id(student_id: str, university: str):
    try:
        student_ref = db.collection("USERS").document(university).collection("students").document(student_id)
        doc = student_ref.get()
        if doc.exists:
            return doc.to_dict()
        return None
    except Exception as e:
        logger.exception("get_student_by_id failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Firebase error: {str(e)}")
    

  # ---------------------------
# User existence helper
# ---------------------------
async def user_exists(university: str, email: str, phone: str, first_name: str, last_name: str) -> bool:
    """
    Check if a user already exists in any collection (students, landlords, union members)
    by email, phone number, or name combination.
    """
    # Normalize names
    fname = first_name.strip().lower()
    lname = last_name.strip().lower()

    # Students
    students_ref = db.collection("USERS").document(university).collection("students")
    student_query = students_ref.where("email", "==", email).stream()
    if list(student_query): return True
    student_query = students_ref.where("phone_number", "==", phone).stream()
    if list(student_query): return True
    student_query = students_ref.where("first_name", "==", fname).where("last_name", "==", lname).stream()
    if list(student_query): return True

    # Union members
    union_ref = db.collection("USERS").document(university).collection("studentunion")
    union_query = union_ref.where("email", "==", email).stream()
    if list(union_query): return True
    union_query = union_ref.where("phone_number", "==", phone).stream()
    if list(union_query): return True
    union_query = union_ref.where("first_name", "==", fname).where("last_name", "==", lname).stream()
    if list(union_query): return True

    # Landlords (global collection)
    landlords_ref = db.collection("LANDLORDS")
    landlord_query = landlords_ref.where("email", "==", email).stream()
    if list(landlord_query): return True
    landlord_query = landlords_ref.where("phone_number", "==", phone).stream()
    if list(landlord_query): return True
    landlord_query = landlords_ref.where("first_name", "==", fname).where("last_name", "==", lname).stream()
    if list(landlord_query): return True

    return False






logger = logging.getLogger("app.firebase")

async def update_user_password(email: str, hashed_pw: str, university: str | None = None) -> bool:
    """
    Update a user's password stored at USERS/{university}/students/{id}.
    - If `university` is provided, search only that university's students collection first.
    - Otherwise iterate all universities under USERS and update the first matching student.
    Returns True on success, raises HTTPException(404) if not found.
    """
    try:
        def _update_iterable(iterable):
            updated = False
            for doc in iterable:
                # doc.reference is the DocumentReference for the matched document
                doc.reference.update({
                    "password": hashed_pw,
                    "updated_at": datetime.utcnow().isoformat()
                })
                logger.info("update_user_password: updated password for email=%s at %s", email, doc.reference.path)
                updated = True
            return updated

        users_root = db.collection("USERS")

        # 1) If university provided, check that university's students collection first
        if university:
            students_ref = users_root.document(university).collection("students")
            q = students_ref.where("email", "==", email).limit(1).stream()
            if _update_iterable(q):
                return True

        # 2) Iterate all universities under USERS and search students subcollection
        for uni_doc in users_root.stream():
            uni_id = uni_doc.id
            students_ref = users_root.document(uni_id).collection("students")
            q = students_ref.where("email", "==", email).limit(1).stream()
            if _update_iterable(q):
                return True

        # Not found
        logger.warning("update_user_password: user not found for email=%s", email)
        raise HTTPException(status_code=404, detail="User not found")

    except HTTPException:
        # re-raise HTTPExceptions so caller can handle them
        raise
    except Exception as e:
        logger.exception("update_user_password: unexpected error for email=%s: %s", email, e)
        raise HTTPException(status_code=500, detail=f"Error updating password: {str(e)}")







RESET_COLLECTION = "password_resets"

async def save_reset_code(email: str, code: str, expires: datetime):
    """
    Save reset code with expiry in Firestore.
    """
    doc_ref = db.collection(RESET_COLLECTION).document(email)
    doc_ref.set({
        "code": code,
        "expires": expires.isoformat()
    }, merge=True)

async def get_reset_code(email: str):
    """
    Retrieve reset code if not expired.
    """
    doc = db.collection(RESET_COLLECTION).document(email).get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    expires = datetime.fromisoformat(data["expires"])
    if datetime.utcnow() > expires:
        # Expired
        await clear_reset_code(email)
        return None
    return data["code"]

async def clear_reset_code(email: str):
    """
    Remove reset code after use or expiry.
    """
    db.collection(RESET_COLLECTION).document(email).delete()



  


# ---------------------------
# LANDLORDS
# ---------------------------
async def save_landlord_to_firebase(landlord_data: dict):
    try:
        landlords_ref = db.collection("LANDLORDS")

        # Check if email exists already
        query = landlords_ref.where("email", "==", landlord_data["email"]).limit(1).stream()
        if any(list(query)):
            logger.info("save_landlord_to_firebase: email exists: %s", landlord_data["email"])
            return False

        landlord_id = generate_user_id(landlord_data["first_name"], landlord_data["last_name"])
        landlord_data["user_id"] = landlord_id
        landlord_data["role"] = "landlord"

        landlords_ref.document(landlord_id).set(landlord_data)
        logger.info("save_landlord_to_firebase: wrote landlord %s to LANDLORDS/%s", landlord_data["email"], landlord_id)
        return True
    except Exception as e:
        logger.exception("save_landlord_to_firebase failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Firebase error: {str(e)}")


async def get_landlord_by_email(email: str):
    try:
        landlords_ref = db.collection("LANDLORDS")
        query = landlords_ref.where("email", "==", email).limit(1).stream()
        for doc in query:
            return doc.to_dict()
        return None
    except Exception as e:
        logger.exception("get_landlord_by_email failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Firebase error: {str(e)}")


async def get_landlord_by_id(landlord_id: str):
    try:
        landlord_ref = db.collection("LANDLORDS").document(landlord_id)
        doc = landlord_ref.get()
        if doc.exists:
            return doc.to_dict()
        return None
    except Exception as e:
        logger.exception("get_landlord_by_id failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Firebase error: {str(e)}")


# ---------------------------
# STUDENT UNION MEMBERS
# ---------------------------
async def save_union_member_to_firebase(union_data: dict, university: str):
    """
    Save union member. Prevent creating a union member if a student with same email exists.
    Returns True on success, False if duplicate exists.
    """
    try:
        union_ref = db.collection("USERS").document(university).collection("studentunion")
        students_ref = db.collection("USERS").document(university).collection("students")

        email = union_data.get("email")
        first_name = union_data.get("first_name", "")
        last_name = union_data.get("last_name", "")

        logger.info("save_union_member_to_firebase called email=%s university=%s", email, university)

        # Check if email exists already in union collection
        union_query = union_ref.where("email", "==", email).limit(1).stream()
        if list(union_query):
            logger.info("save_union_member_to_firebase: email already exists in union collection: %s", email)
            return False

        # Prevent creating union member if a student exists with same email
        student_query = students_ref.where("email", "==", email).limit(1).stream()
        if list(student_query):
            logger.warning("save_union_member_to_firebase: email exists in students collection, refusing to create union member: %s", email)
            return False

        # Generate id and set role
        union_id = generate_user_id(first_name, last_name)
        union_data["user_id"] = union_id
        union_data["role"] = "union_member"

        union_ref.document(union_id).set(union_data)
        logger.info("save_union_member_to_firebase: wrote union member %s to USERS/%s/studentunion/%s", email, university, union_id)
        return True
    except Exception as e:
        logger.exception("save_union_member_to_firebase failed for email=%s: %s", union_data.get("email"), e)
        raise HTTPException(status_code=500, detail=f"Firebase error: {str(e)}")


async def get_union_member_by_email(email: str, university: str):
    try:
        union_ref = db.collection("USERS").document(university).collection("studentunion")
        query = union_ref.where("email", "==", email).limit(1).stream()
        for doc in query:
            return doc.to_dict()
        return None
    except Exception as e:
        logger.exception("get_union_member_by_email failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Firebase error: {str(e)}")


async def get_union_member_by_id(union_id: str, university: str):
    try:
        union_ref = db.collection("USERS").document(university).collection("studentunion").document(union_id)
        doc = union_ref.get()
        if doc.exists:
            return doc.to_dict()
        return None
    except Exception as e:
        logger.exception("get_union_member_by_id failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Firebase error: {str(e)}")
