# file: CUZ/core/security.py
import os
from datetime import datetime, timedelta, timezone
import uuid
import ipaddress
import urllib.parse
import socket
import logging
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from CUZ.core.firebase import db




# ---------------------------
# Logging
# ---------------------------
logger = logging.getLogger("core.security")

# ---------------------------
# Password Hashing (bcrypt 72-byte safe)
# ---------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
BCRYPT_BYTE_LIMIT = 72

def _normalize_and_truncate_password(password: str) -> str:
    """
    Ensure password is a str, remove control characters, then truncate
    safely to BCRYPT_BYTE_LIMIT bytes (not characters).
    """
    if password is None:
        raise ValueError("Password cannot be None")

    if not isinstance(password, str):
        password = str(password)

    # Remove non-printable/control characters (keeps spaces)
    cleaned = "".join(ch for ch in password if ord(ch) >= 32)

    # Encode to bytes and truncate to bcrypt byte limit.
    b = cleaned.encode("utf-8")
    before_len = len(b)
    if before_len > BCRYPT_BYTE_LIMIT:
        b = b[:BCRYPT_BYTE_LIMIT]
        logger.debug(
            "Password bytes exceeded bcrypt limit; truncating "
            f"from {before_len} -> {len(b)} bytes"
        )
    else:
        logger.debug("Password byte length OK: %d bytes", before_len)

    # Decode back to string, ignoring partial UTF-8 byte sequences if present.
    safe_str = b.decode("utf-8", "ignore")
    logger.debug("Final safe password byte-length: %d", len(safe_str.encode("utf-8")))
    return safe_str

def get_password_hash(password: str) -> str:
    """Hash the provided password using bcrypt, after safely truncating it."""
    safe_pw = _normalize_and_truncate_password(password)
    return pwd_context.hash(safe_pw)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against stored bcrypt hash."""
    try:
        safe_pw = _normalize_and_truncate_password(plain_password)
        return pwd_context.verify(safe_pw, hashed_password)
    except Exception as e:
        logger.exception("Password verification error: %s", e)
        raise

# ---------------------------
# JWT Configuration
# ---------------------------
# ✅ Load from environment for dev, fallback to Firestore in get_secret_key()
SECRET_KEY = os.getenv("SECRET_KEY")  
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))


def get_secret_key() -> str:
    """Lazy-load stable JWT secret key from Firestore CONFIG/jwt."""
    global SECRET_KEY
    if SECRET_KEY is None:
        cfg_ref = db.collection("CONFIG").document("jwt")
        snap = cfg_ref.get()
        if not snap.exists:
            raise RuntimeError("Missing CONFIG/jwt document in Firestore")

        data = snap.to_dict() or {}
        key = data.get("SECRET_KEY")
        if not key or len(key) < 32:
            raise RuntimeError("Invalid or missing SECRET_KEY in Firestore CONFIG/jwt")

        SECRET_KEY = key
        logger.info("Loaded SECRET_KEY from Firestore")
    return SECRET_KEY

security = HTTPBearer()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

ADMIN_CREDENTIALS = {
    "username": "adminL",
    "password": "adminL"
}


# ---------------------------
# Token Creation
# ---------------------------
def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ---------------------------
# Dependency: Current User (JWT only)
# ---------------------------


async def get_current_user(request: Request, credentials=Depends(security)):
    token = credentials.credentials

    try:
        payload = jwt.decode(token, get_secret_key(), algorithms=[ALGORITHM])

        sub = payload.get("sub")
        role = payload.get("role")
        user_id = payload.get("user_id")
        university = payload.get("university")
        premium = payload.get("premium", False)

        logger.debug(
            "JWT decoded → sub=%s role=%s user_id=%s university=%s",
            sub, role, user_id, university
        )

        if not sub or not role or not user_id:
            logger.warning("Invalid JWT payload: %s", payload)
            raise HTTPException(status_code=401, detail="Invalid token payload")

        # -------------------------------------------------
        # 🔓 Device-free endpoints (FIRST LOGIN FLOW)
        # -------------------------------------------------
        DEVICE_FREE_ENDPOINTS = {
            "/device/register",
            "/users/register_fcm",
        }

        path = request.url.path
        enforce_device = path not in DEVICE_FREE_ENDPOINTS

        logger.debug(
            "Auth path=%s | enforce_device=%s",
            path, enforce_device
        )

        # -------------------------------------------------
        # 🔒 Enforce one-device-per-account (if required)
        # -------------------------------------------------
        if enforce_device:
            doc = db.collection("DEVICES").document(user_id).get()

            if not doc.exists:
                logger.warning("No device registered for user_id=%s", user_id)
                raise HTTPException(status_code=401, detail="No active device registered")

            device_info = doc.to_dict()
            current_device_token = request.headers.get("x-device-token")

            logger.debug(
                "Device check → header_token=%s firestore_token=%s active=%s",
                current_device_token,
                device_info.get("device_token"),
                device_info.get("active"),
            )

            if not current_device_token:
                raise HTTPException(status_code=401, detail="Missing device token")

            if (
                device_info.get("device_token") != current_device_token
                or not device_info.get("active", False)
            ):
                raise HTTPException(status_code=401, detail="Logged in on another device")

        # -------------------------------------------------
        # 👑 Admin bypass
        # -------------------------------------------------
        if role == "admin":
            user = {
                "email": sub,
                "role": "admin",
                "user_id": user_id or "ADMIN001",
                "premium": True,
                "university": university or "ALL",
            }
        else:
            # -------------------------------------------------
            # 🔎 Verify user exists
            # -------------------------------------------------
            if role == "student":
                ref = (
                    db.collection("USERS")
                    .document(university)
                    .collection("students")
                    .document(user_id)
                    .get()
                )
            else:
                ref = db.collection("LANDLORDS").document(user_id).get()

            if not ref.exists:
                logger.warning("User not found in Firestore: %s", user_id)
                raise HTTPException(status_code=401, detail="User not found")

            data = ref.to_dict()
            user = {
                "email": sub,
                "role": role,
                "user_id": user_id,
                "premium": data.get("premium", False),
                "university": university,
            }

        request.scope["user"] = user
        logger.debug("Authenticated user context: %s", user)
        return user

    except JWTError as e:
        logger.warning("JWT error: %s", str(e))
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    except HTTPException:
        raise

    except Exception as e:
        logger.exception("❌ Error validating user")
        raise HTTPException(status_code=500, detail="Error validating user")




# ---------------------------
# Role-Based Dependencies
# ---------------------------
async def get_current_admin(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

async def get_current_landlord(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ["landlord", "admin"]:
        raise HTTPException(status_code=403, detail="Landlord or admin access required")
    return current_user

async def get_premium_student(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "student" or not current_user.get("premium", False):
        raise HTTPException(status_code=403, detail="Premium student required")
    return current_user

async def get_student_or_admin(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ["student", "admin"]:
        raise HTTPException(status_code=403, detail="Student or admin access required")
    return current_user

async def get_premium_student_or_admin(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") == "admin":
        return current_user
    if current_user.get("role") == "student" and current_user.get("premium", False):
        return current_user
    raise HTTPException(status_code=403, detail="Premium student or admin required")

async def get_admin_or_landlord(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ["admin", "landlord"]:
        raise HTTPException(status_code=403, detail="Admin or landlord access required")
    return current_user

async def get_student_union_or_higher(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") in ["student_union", "admin"]:
        return current_user
    raise HTTPException(status_code=403, detail="Student union or admin access required")

# ---------------------------
# Admin Login Helper
# ---------------------------
async def get_admin_credentials(username: str, password: str):
    """Verify static admin credentials and issue JWT."""
    if username == ADMIN_CREDENTIALS["username"] and password == ADMIN_CREDENTIALS["password"]:
        admin_data = {
            "sub": username,
            "role": "admin",
            "user_id": "ADMIN001",
            "university": "ALL"
        }
        return {
            "access_token": create_access_token(admin_data),
            "token_type": "bearer"
        }
    raise HTTPException(status_code=401, detail="Incorrect admin credentials")

# ---------------------------
# Location Tokens
# ---------------------------
def create_location_token(start_lat: float, start_lon: float, end_lat: float, end_lon: float, expires_minutes: int = 10):
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    payload = {
        "start_lat": start_lat,
        "start_lon": start_lon,
        "end_lat": end_lat,
        "end_lon": end_lon,
        "exp": expire
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_location_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return {
            "start_lat": payload.get("start_lat"),
            "start_lon": payload.get("start_lon"),
            "end_lat": payload.get("end_lat"),
            "end_lon": payload.get("end_lon")
        }
    except JWTError:
        return None

# ---------------------------
# Safe URL Validation
# ---------------------------
TRUSTED_DOMAINS = ["maps.googleapis.com", "yango.com"]

def is_safe_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname
    if not host:
        return False
    if any(host.endswith(d) for d in TRUSTED_DOMAINS):
        return True
    try:
        ip = socket.gethostbyname(host)
        ip_obj = ipaddress.ip_address(ip)
        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved:
            return False
    except Exception:
        return False
    return True
