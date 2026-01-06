import secrets
import string
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, Cookie
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import firestore
from passlib.context import CryptContext
from jose import jwt
import os

from CUZ.USERS.models import StudentSignup, LandlordSignup, LoginInput

# -----------------------------
# Password hashing
# -----------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password.strip())

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password.strip(), hashed_password)

# -----------------------------
# User ID generation
# -----------------------------
def generate_user_id(first_name: str, last_name: str) -> str:
    initials = first_name[0].upper() + last_name[0].upper()
    user_id = ''.join(secrets.choice(string.digits) for _ in range(15))
    return f"{initials}{user_id}"

def generate_landlord_id(first_name: str, last_name: str, boarding_house: str) -> str:
    initials = first_name[0].upper() + last_name[0].upper()
    random_digits = ''.join(secrets.choice(string.digits) for _ in range(10))
    return f"{initials}{random_digits}{boarding_house}"

# -----------------------------
# JWT setup
# -----------------------------
SECRET_KEY = os.getenv("JWT_SECRET", "fallback-secret")
ALGORITHM = os.getenv("JWT_ALGO", "HS256")

def create_access_token(data: dict, expires_delta: timedelta = timedelta(hours=1)):
    to_encode = data.copy()
    to_encode["exp"] = datetime.utcnow() + expires_delta
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# -----------------------------
# Role-based access control
# -----------------------------
def require_role(required_role: str):
    def role_checker(user=Depends(lambda: verify_token(None))):
        if user.get("role") != required_role:
            raise HTTPException(status_code=403, detail=f"Access denied: {required_role} only")
        return user
    return role_checker

# -----------------------------
# Token verification (header + cookie)
# -----------------------------
security = HTTPBearer(auto_error=False)

def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    access_token: str = Cookie(None)
):
    token_to_check = None

    # 1️⃣ Check Authorization header (mobile)
    if credentials and credentials.credentials:
        token_to_check = credentials.credentials
    # 2️⃣ Check HTTP-only cookie (web)
    elif access_token:
        token_to_check = access_token.replace("Bearer ", "")
    else:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = jwt.decode(token_to_check, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

if SECRET_KEY == "fallback-secret":
    print("⚠️ WARNING: Using fallback JWT secret. Set JWT_SECRET in your environment.") 
