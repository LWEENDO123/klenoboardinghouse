from fastapi import APIRouter,HTTPException
from datetime import datetime
from CUZ.USERS.models import (
    StudentSignup,
    LandlordSignup,
    LoginInput 
    
)

from CUZ.USERS.security import hash_password, generate_user_id, generate_landlord_id, verify_password, create_access_token
from CUZ.core.firebase_config import db  # ✅ Use shared db

router = APIRouter()





@router.post("/signup/student", tags=["Auth"])
async def signup_student(student: StudentSignup):
    student_id = generate_user_id(student.first_name, student.last_name)
    student_dict = student.dict()
    student_dict["password"] = hash_password(student.password)
    student_dict["created_at"] = datetime.utcnow().isoformat()
    university = student.university
    db.collection("USERS").document(university).collection("studentinfo").document(student_id).set(student_dict)  
    return {"message": "Student signed up", "id": student_id}

@router.post("/signup/landlord", tags=["Auth"])
async def signup_landlord(landlord: LandlordSignup):
    landlord_id = generate_landlord_id(landlord.first_name, landlord.last_name, landlord.boarding_house)
    landlord_dict = landlord.dict()
    landlord_dict["password"] = hash_password(landlord.password)
    landlord_dict["created_at"] = datetime.utcnow().isoformat()

    db.collection("USERS").document("LANDLORD").collection("landlordinfo").document(landlord_id).set(landlord_dict)
    return {"message": "Landlord signed up", "id": landlord_id}

@router.post("/login", tags=["Auth"])
async def login_user(credentials: LoginInput):
    if credentials.university:
        # Student login flow
        university = credentials.university.upper()
        doc_ref = db.collection("USERS").document(university).collection("studentinfo")
        role = "student"
    else:
        # Landlord login flow
        doc_ref = db.collection("USERS").document("LANDLORD").collection("landlordinfo")
        role = "landlord"

    # Query Firestore for matching email
    query = doc_ref.where("email", "==", credentials.email).stream()
    user_doc = next(query, None)

    if not user_doc:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user_data = user_doc.to_dict()
    user_id = user_doc.id

    if not verify_password(credentials.password, user_data["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Generate JWT token
    token_payload = {
        "user_id": user_id,
        "email": user_data["email"],
        "role": role
    }
    

    if role == "student":
        token_payload["university"] = university

    token = create_access_token(token_payload)

    return {"access_token": token, "token_type": "bearer"}

