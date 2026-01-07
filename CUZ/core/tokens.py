# core/tokens.py
# file: CUZ/core/tokens.py
import uuid
from datetime import datetime, timedelta
from jose import jwt

# ✅ Use CUZ prefix for internal modules
from CUZ.core.firebase import db
from CUZ.core.security import (
    get_secret_key,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
)


def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    """
    Create a short-lived access token with role, user_id, university, etc.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, get_secret_key(), algorithm=ALGORITHM)

def create_refresh_token(user_id: str, role: str, university: str, ip: str, user_agent: str) -> str:
    """
    Create a refresh token with unique ID (jti).
    Store role and university in payload and Firestore for rotation.
    """
    jti = str(uuid.uuid4())
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": user_id,
        "jti": jti,
        "role": role,
        "university": university,
        "exp": expire,
    }
    encoded = jwt.encode(payload, get_secret_key(), algorithm=ALGORITHM)

    # Store metadata in Firestore
    db.collection("REFRESH_TOKENS").document(jti).set({
        "uid": user_id,
        "role": role,
        "university": university,
        "ip": ip,
        "user_agent": user_agent,
        "revoked": False,
        "expires_at": expire.isoformat(),
        "created_at": datetime.utcnow().isoformat(),
    })

    return encoded

def revoke_refresh_token(jti: str):
    """
    Mark a refresh token as revoked in Firestore.
    """
    db.collection("REFRESH_TOKENS").document(jti).update({"revoked": True})

def is_refresh_token_valid(jti: str) -> bool:
    """
    Check if a refresh token is still valid (not revoked, not expired).
    """
    doc = db.collection("REFRESH_TOKENS").document(jti).get()
    if not doc.exists:
        return False
    data = doc.to_dict()
    if data.get("revoked"):
        return False
    if datetime.fromisoformat(data["expires_at"]) < datetime.utcnow():
        return False
    return True

def rotate_refresh_token(old_jti: str, user_id: str, role: str, university: str, ip: str, user_agent: str) -> str:
    """
    Invalidate the old refresh token and issue a new one with same role/university.
    """
    revoke_refresh_token(old_jti)
    return create_refresh_token(user_id, role, university, ip, user_agent)
