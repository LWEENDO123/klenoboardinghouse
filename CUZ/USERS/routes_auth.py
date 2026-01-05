# USERS/routes_auth.py
from fastapi import APIRouter, Depends, HTTPException, Request
from jose import jwt, JWTError
from datetime import timedelta

from core.tokens import (
    create_access_token,
    create_refresh_token,
    rotate_refresh_token,
    is_refresh_token_valid,
    revoke_refresh_token,
    SECRET_KEY,
    ALGORITHM
)
from core.mfa import verify_otp
from core.audit import log_auth_failure, log_failed_mfa, log_token_reuse
from USERS.firebase import db

router = APIRouter()

# -------------------------
# LOGIN ENDPOINT
# -------------------------
@router.post("/login")
async def login(request: Request, email: str, password: str, otp: str = None):
    ip = request.client.host
    ua = request.headers.get("user-agent")

    # 1. Validate credentials (simplified example)
    user_doc = db.collection("USERS").document(email).get()
    if not user_doc.exists or user_doc.to_dict().get("password") != password:
        await log_auth_failure(actor=email, ip=ip, user_agent=ua, reason="invalid_credentials")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user = user_doc.to_dict()
    role = user.get("role", "student")

    # 2. If admin, enforce MFA
    if role == "admin":
        secret = user.get("mfa_secret")
        if not secret or not otp or not verify_otp(secret, otp):
            await log_failed_mfa(actor=email, ip=ip, user_agent=ua)
            raise HTTPException(status_code=401, detail="MFA verification failed")

    # 3. Issue tokens
    access_token = create_access_token({"sub": email, "role": role})
    refresh_token = create_refresh_token(email, ip, ua)

    return {"access_token": access_token, "refresh_token": refresh_token}


# -------------------------
# REFRESH ENDPOINT
# -------------------------
@router.post("/refresh")
async def refresh(request: Request, token: str):
    ip = request.client.host
    ua = request.headers.get("user-agent")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        jti = payload.get("jti")
        uid = payload.get("sub")

        # 1. Check if token is valid
        if not is_refresh_token_valid(jti):
            await log_token_reuse(actor=uid, jti=jti, ip=ip, user_agent=ua)
            raise HTTPException(status_code=401, detail="Invalid or revoked refresh token")

        # 2. Rotate token
        new_refresh = rotate_refresh_token(jti, uid, ip, ua)
        new_access = create_access_token({"sub": uid})

        return {"access_token": new_access, "refresh_token": new_refresh}

    except JWTError:
        await log_auth_failure(actor="unknown", ip=ip, user_agent=ua, reason="invalid_refresh_token")
        raise HTTPException(status_code=401, detail="Invalid refresh token")
