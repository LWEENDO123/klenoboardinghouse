#USERS/security.py
import os
from fastapi import Depends, HTTPException, status, Form
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
from typing import Optional
from .firebase import db  # For user verification in get_current_user

# ==============================
# JWT / Password settings
# ==============================
# ✅ Load from environment variables
SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret")  # safe default for dev
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# OAuth2 scheme for FastAPI
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="users/login")

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="users/login")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ==============================
# Password helpers
# ==============================
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


# ==============================
# JWT helpers
# ==============================
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ==============================
# Current user
# ==============================
async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        role: str = payload.get("role")
        premium: bool = payload.get("premium", False)
        user_id: str = payload.get("user_id")
        university: str = payload.get("university")

        if email is None or role is None:
            raise credentials_exception

        return {
            "email": email,
            "role": role,
            "premium": premium,
            "user_id": user_id,
            "university": university,
        }
    except JWTError:
        raise credentials_exception


# ==============================
# Role checkers
# ==============================
def get_student_or_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Allow students (any tier) or admins. Block landlords."""
    if current_user["role"] not in ("student", "admin"):
        raise HTTPException(status_code=403, detail="Access restricted to students or admins")
    if not current_user.get("user_id") or not current_user.get("university"):
        raise HTTPException(status_code=400, detail="Missing user ID or university")
    return current_user


def get_premium_student_or_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Allow premium students or admins. Block landlords and free students."""
    if current_user["role"] == "student":
        if not current_user.get("premium", False):
            raise HTTPException(status_code=403, detail="Premium student access required")
    elif current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Access restricted to premium students or admins")

    if not current_user.get("user_id") or not current_user.get("university"):
        raise HTTPException(status_code=400, detail="Missing user ID or university")
    return current_user


def get_admin_or_landlord(current_user: dict = Depends(get_current_user)) -> dict:
    """Allow admins or landlords."""
    if current_user["role"] not in ("admin", "landlord"):
        raise HTTPException(status_code=403, detail="Admin or landlord access required")
    return current_user


def get_student_union_or_higher(current_user: dict = Depends(get_current_user)) -> dict:
    """Allow student_union, admin, or landlord."""
    if current_user["role"] not in ("student_union", "admin", "landlord"):
        raise HTTPException(status_code=403, detail="Student union, admin, or landlord access required")
    return current_user


def get_current_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Strict admin-only access."""
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
