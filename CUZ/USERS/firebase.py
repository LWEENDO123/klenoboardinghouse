import random
import string
import logging
from fastapi import HTTPException
from CUZ.core.firebase import db  # Shared Firestore client from core (no re-init)
  # Shared Firestore client from core (no re-init)

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
