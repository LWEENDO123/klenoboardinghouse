from fastapi import APIRouter, HTTPException, Request, status, Depends, Form, Cookie
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
import logging
import uuid
import os

from dotenv import load_dotenv

from CUZ.USERS.models import (
    StudentSignup,
    LandlordSignup,
    LoginInput
)
from CUZ.USERS.security import (
    hash_password,
    generate_user_id,
    generate_landlord_id,
    verify_password,
    create_access_token,
    require_role,
    verify_token
)
from CUZ.core.firebase_config import db


# Load environment variables
load_dotenv()

router = APIRouter()
templates = Jinja2Templates(directory="C:/Users/lweendo/project/baodinghouse/CUZ/templates")

# ---------- Helper ----------
def generate_referal_code():
    return str(uuid.uuid4())[:8]

# ---------- HTML Routes ----------
@router.get("/login", response_class=HTMLResponse, tags=["Auth"])
async def get_login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.get("/signup/student", response_class=HTMLResponse, tags=["Auth"])
async def get_student_signup(request: Request):
    return templates.TemplateResponse("student-signup.html", {"request": request})

@router.get("/signup/landlord", response_class=HTMLResponse, tags=["Auth"])
async def get_landlord_signup(request: Request):
    return templates.TemplateResponse("landlord-signup.html", {"request": request})

# ---------- API Routes ----------
# POST: Signup student
@router.post("/login", tags=["Auth"])
async def login_user(credentials: LoginInput):
    try:
        # Determine collection
        if credentials.university:  # Student
            university = credentials.university.upper()
            doc_ref = db.collection("USERS").document(university).collection("studentinfo")
        else:  # Landlord
            doc_ref = db.collection("USERS").document("LANDLORD").collection("landlordinfo")

        # Find user
        query = doc_ref.where("email", "==", credentials.email).stream()
        user_doc = next(query, None)
        if not user_doc:
            raise HTTPException(status_code=401, detail="Email not registered")

        user_data = user_doc.to_dict()
        user_id = user_doc.id

        # Verify password
        if not verify_password(credentials.password, user_data["password"]):
            raise HTTPException(status_code=401, detail="Incorrect password")

        role = user_data.get("role", "student")
        token_payload = {"sub": user_id, "email": user_data["email"], "role": role}
        if role == "student":
            token_payload["university"] = university

        token = create_access_token(token_payload)

        # Set cookie for web, return redirect to dashboard
        redirect_url = "/home" if role == "student" else "/landlord/dashboard"
        response = RedirectResponse(url=redirect_url, status_code=302)
        response.set_cookie(
            key="access_token",
            value=f"Bearer {token}",
            httponly=True,
            max_age=3600,
            samesite="lax"
        )
        return response

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

