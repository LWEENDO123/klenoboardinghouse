# USERS/user_routes.py
from fastapi import (
    APIRouter, HTTPException, status, Depends,
    Request, Form, Header, Response,
)
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
import secrets # for generating secure random codes 
from datetime import datetime, timedelta
import os




from jose import jwt, JWTError
from datetime import timedelta
from pydantic import EmailStr
from fastapi.security import OAuth2PasswordRequestForm
from .firebase import (
    save_reset_code,
    get_reset_code,
    clear_reset_code,
    update_user_password,   # <-- add this
)


# ✅ Project imports
from CUZ.HOME.add_boardinghouse import CLUSTERS
from CUZ.core.firebase import db
from CUZ.core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    SECRET_KEY,
    ALGORITHM,
    get_current_user,
    get_student_or_admin,
    get_premium_student_or_admin,
    get_admin_or_landlord,
    get_student_union_or_higher,
    get_current_admin,
    create_access_token,
    get_password_hash,
    verify_password,
)
from CUZ.core.tokens import (
    create_refresh_token,
    rotate_refresh_token,
    revoke_refresh_token,
    is_refresh_token_valid,
)
from CUZ.core.rate_limit import limit
from CUZ.core.bruteforce import record_failed_attempt, is_account_locked, reset_attempts
from CUZ.core.audit import log_event

from .models import StudentSignup, LandlordSignup
from .firebase import (
    save_student_to_firebase,
    save_landlord_to_firebase,
    get_student_by_id,
    get_landlord_by_id,
    get_student_by_email,
    get_landlord_by_email,
    get_union_member_by_email,
)


import logging
import logging
logger = logging.getLogger("app.users")  # custom logger name for clarity


router = APIRouter(prefix="/users", tags=["users"])


# ---------------------------
# SIGNUPS (with audit logging)
# ---------------------------

@router.post("/student_signup")
@limit("5/minute")
async def student_signup(
    request: Request,
    user: StudentSignup,
    response: Response,
):
    try:
        user_dict = user.dict()
        raw_pw = user_dict["password"]

        # Hash password
        user_dict["password"] = get_password_hash(raw_pw)
        user_dict["role"] = "student"
        user_dict["premium"] = False

        # Expanded duplicate check
        from .firebase import user_exists
        if await user_exists(
            user.university,
            user_dict["email"],
            user_dict.get("phone_number"),
            user_dict.get("first_name", ""),
            user_dict.get("last_name", "")
        ):
            log_event("signup_attempt", {
                "role": "student",
                "email": user_dict["email"],
                "university": user.university,
                "status": "duplicate"
            })
            raise HTTPException(status_code=400, detail="Duplicate user detected (email/phone/name)")

        success = await save_student_to_firebase(user_dict, university=user.university)
        if success:
            access_token = create_access_token(
                data={
                    "sub": user_dict["email"],
                    "role": "student",
                    "premium": False,
                    "user_id": user_dict["user_id"],
                    "university": user_dict["university"],
                }
            )
            log_event("signup_success", {
                "role": "student",
                "email": user_dict["email"],
                "user_id": user_dict["user_id"],
                "university": user.university
            })
            return {
                "access_token": access_token,
                "token_type": "bearer",
                "message": "Student signup successful",
                "user_id": user_dict["user_id"],
                "university": user_dict["university"],
            }
        raise HTTPException(status_code=400, detail="Student already exists")
    except HTTPException:
        raise
    except Exception as e:
        log_event("signup_error", {
            "role": "student",
            "email": user.email,
            "university": user.university,
            "error": str(e)
        })
        raise HTTPException(status_code=500, detail=f"Error signing up student: {str(e)}")


@router.post("/landlord_signup")
@limit("5/minute")
async def landlord_signup(
    request: Request,
    user: LandlordSignup,
    response: Response,
):
    try:
        user_dict = user.dict()
        user_dict["password"] = get_password_hash(user_dict["password"])
        user_dict["role"] = "landlord"

        from .firebase import user_exists
        if await user_exists(
            user_dict.get("university", "ALL"),
            user_dict["email"],
            user_dict.get("phone_number"),
            user_dict.get("first_name", ""),
            user_dict.get("last_name", "")
        ):
            log_event("signup_attempt", {
                "role": "landlord",
                "email": user_dict["email"],
                "status": "duplicate"
            })
            raise HTTPException(status_code=400, detail="Duplicate user detected (email/phone/name)")

        success = await save_landlord_to_firebase(user_dict)
        if success:
            access_token = create_access_token(
                data={
                    "sub": user_dict["email"],
                    "role": "landlord",
                    "premium": False,
                    "user_id": user_dict["user_id"],
                    "university": user_dict.get("university", "ALL"),
                }
            )
            log_event("signup_success", {
                "role": "landlord",
                "email": user_dict["email"],
                "user_id": user_dict["user_id"]
            })
            return {
                "access_token": access_token,
                "token_type": "bearer",
                "message": "Landlord signup successful",
                "user_id": user_dict["user_id"],
                "university": user_dict.get("university", "ALL"),
            }
        raise HTTPException(status_code=400, detail="Landlord already exists")
    except HTTPException:
        raise
    except Exception as e:
        log_event("signup_error", {
            "role": "landlord",
            "email": user.email,
            "error": str(e)
        })
        raise HTTPException(status_code=500, detail=f"Error signing up landlord: {str(e)}")


@router.post("/student_union_signup")
@limit("5/minute")
async def student_union_signup(
    request: Request,
    user: StudentSignup,
    response: Response,
):
    try:
        user_dict = user.dict()
        raw_pw = user_dict["password"]

        user_dict["password"] = get_password_hash(raw_pw)
        user_dict["role"] = "student_union"
        user_dict["premium"] = False

        from .firebase import user_exists
        if await user_exists(
            user.university,
            user_dict["email"],
            user_dict.get("phone_number"),
            user_dict.get("first_name", ""),
            user_dict.get("last_name", "")
        ):
            log_event("signup_attempt", {
                "role": "student_union",
                "email": user_dict["email"],
                "university": user.university,
                "status": "duplicate"
            })
            raise HTTPException(status_code=400, detail="Duplicate user detected (email/phone/name)")

        success = await save_student_to_firebase(user_dict, university=user.university)
        if success:
            access_token = create_access_token(
                data={
                    "sub": user_dict["email"],
                    "role": "student_union",
                    "premium": False,
                    "user_id": user_dict["user_id"],
                    "university": user_dict["university"],
                }
            )
            log_event("signup_success", {
                "role": "student_union",
                "email": user_dict["email"],
                "user_id": user_dict["user_id"],
                "university": user.university
            })
            return {
                "access_token": access_token,
                "token_type": "bearer",
                "message": "Student union member signup successful",
                "user_id": user_dict["user_id"],
                "university": user_dict["university"],
            }

        raise HTTPException(status_code=400, detail="Student union member already exists")
    except HTTPException:
        raise
    except Exception as e:
        log_event("signup_error", {
            "role": "student_union",
            "email": user.email,
            "university": user.university,
            "error": str(e)
        })
        raise HTTPException(status_code=500, detail=f"Error signing up student union member: {str(e)}")



# ---------------------------
# LOGIN
# ---------------------------



logger = logging.getLogger("uvicorn.error")





@router.post("/login")
@limit("3/minute")
async def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    university = request.query_params.get("university")
    logger.info("========== NEW LOGIN ATTEMPT ==========")

    try:
        logger.info(f"Username (email): {form_data.username}")
        logger.info(f"University param: {university}")

        # ---------------------------
        # Fetch user depending on context
        # ---------------------------
        user_data = None
        if university:
            user_data = await get_student_by_email(form_data.username, university)
            if not user_data:
                user_data = await get_union_member_by_email(form_data.username, university)
        else:
            user_data = await get_landlord_by_email(form_data.username)

        if not user_data:
            raise HTTPException(status_code=401, detail="User not found")

        # ---------------------------
        # Verify password
        # ---------------------------
        valid = verify_password(form_data.password, user_data["password"])
        if not valid:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # ---------------------------
        # Issue JWT access token (1 day expiry)
        # ---------------------------
        access_token = create_access_token(
            data={
                "sub": user_data["email"],
                "role": user_data["role"],
                "premium": user_data.get("premium", False),
                "user_id": user_data["user_id"],
                "university": user_data.get("university"),
            },
            expires_delta=timedelta(days=1),
        )
        logger.debug(f"Issued access token for user_id={user_data['user_id']} with 1 day expiry")

        # ---------------------------
        # Issue refresh token
        # ---------------------------
        ip = request.client.host
        user_agent = request.headers.get("user-agent", "unknown")
        refresh_token = create_refresh_token(
            user_data["user_id"],
            user_data["role"],
            user_data.get("university") or "",
            ip,
            user_agent,
        )
        logger.debug(f"Issued refresh token for user_id={user_data['user_id']}")

        # ---------------------------
        # Fetch existing device token if present
        # ---------------------------
        device_token = None
        try:
            device_doc = db.collection("DEVICES").document(user_data["user_id"]).get()
            if device_doc.exists:
                device_token = device_doc.to_dict().get("device_token")
        except Exception as e:
            logger.warning(f"Could not fetch device token for user_id={user_data['user_id']}: {e}")

        # ---------------------------
        # Return tokens + device token
        # ---------------------------
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "message": f"Logged in as {user_data['role']}",
            "role": user_data["role"],
            "user_id": user_data["user_id"],
            "university": user_data.get("university"),
            "expires_in": 24 * 60 * 60,
            "device_token": device_token,  # 🔹 include this
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error during login")
        raise HTTPException(status_code=500, detail=f"Error logging in: {str(e)}")


# ---------------------------
# LOOKUPS
# ---------------------------
@router.get("/student/{university}/{student_id}")
async def get_student(university: str, student_id: str):
    student = await get_student_by_id(student_id, university)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return student


@router.get("/landlord/{landlord_id}")
async def get_landlord(landlord_id: str):
    landlord = await get_landlord_by_id(landlord_id)
    if not landlord:
        raise HTTPException(status_code=404, detail="Landlord not found")
    return landlord


@router.get("/union/{university}/{union_id}")
async def get_union_member(university: str, union_id: str):
    """
    Lookup a student union member by ID within a university.
    """
    from .firebase import get_union_member_by_id  # ✅ import here or at top

    union_member = await get_union_member_by_id(union_id, university)
    if not union_member:
        raise HTTPException(status_code=404, detail="Union member not found")
    return union_member




# ---------------------------
# ADMIN LOGIN (Hardcoded adminL)
# ---------------------------
@router.post("/admin_login")
async def admin_login(
    username: str = Form(...),
    password: str = Form(...)
):
    """
    Authenticate admin with hardcoded credentials.
    Returns JWT + full payload for mobile dashboard routing.
    """
    try:
        # 🔐 Hardcoded admin credentials
        ADMIN_USERNAME = "adminL"
        ADMIN_PASSWORD = "adminL"

        if username != ADMIN_USERNAME or password != ADMIN_PASSWORD:
            raise HTTPException(status_code=401, detail="Invalid admin credentials")

        # Generate access token
        access_token_expires = timedelta(minutes=60)
        access_token = create_access_token(
            data={
                "sub": ADMIN_USERNAME,
                "role": "admin",
                "user_id": "adminL-id",
                "university": "ALL"
            },
            expires_delta=access_token_expires
        )

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "message": "Logged in as Admin",
            "role": "admin",
            "user_id": "adminL-id",
            "university": "ALL"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during admin login: {str(e)}")



# ---------------------------
# REFRESH TOKEN ENDPOINT
# ---------------------------
# USERS/user_routes.py
from CUZ.core.tokens import create_access_token, rotate_refresh_token, is_refresh_token_valid

from jose import jwt, JWTError


logger = logging.getLogger("uvicorn.error")

from datetime import timedelta

@router.post("/auth/refresh")
@limit("10/minute")
async def refresh_tokens(
    request: Request,
    response: Response,
    refresh_token: str = Form(...)
):
    try:
        logger.debug("========== REFRESH TOKEN REQUEST ==========")
        logger.debug(f"Received refresh request from IP={request.client.host}, UA={request.headers.get('user-agent')}")
        logger.debug(f"Raw refresh_token (first 40 chars)={refresh_token[:40]}...")

        # Decode JWT payload
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        logger.debug(f"Decoded payload={payload}")

        jti = payload.get("jti")
        user_id = payload.get("sub")
        role = payload.get("role")
        university = payload.get("university")

        logger.debug(f"Extracted jti={jti}, user_id={user_id}, role={role}, university={university}")

        if not all([jti, user_id, role, university]):
            logger.error("Missing fields in refresh token payload")
            raise HTTPException(status_code=400, detail="Invalid refresh token payload")

        if not is_refresh_token_valid(jti):
            logger.warning(f"Refresh token jti={jti} invalid or expired")
            raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

        ip = request.client.host
        user_agent = request.headers.get("user-agent", "unknown")

        logger.debug(f"Rotating refresh token for user_id={user_id}")
        new_refresh = rotate_refresh_token(jti, user_id, role, university, ip, user_agent)

        logger.debug("Creating new access token (1 day expiry)")
        new_access = create_access_token(
            {
                "sub": payload.get("sub_email") or payload.get("sub"),
                "role": role,
                "premium": False,
                "user_id": user_id,
                "university": university,
            },
            expires_delta=timedelta(days=1)   # 🔹 now 1 day expiry
        )

        logger.info(f"✅ Successfully refreshed tokens for user_id={user_id}")
        logger.debug(f"New access_token (first 40 chars)={new_access[:40]}...")
        logger.debug(f"New refresh_token (first 40 chars)={new_refresh[:40]}...")

        return {
            "access_token": new_access,
            "refresh_token": new_refresh,
            "token_type": "bearer",
            "expires_in": 24 * 60 * 60   # 🔹 1 day in seconds
        }

    except JWTError:
        logger.exception("JWT decode error")
        raise HTTPException(status_code=400, detail="Invalid refresh token")
    except Exception as e:
        logger.exception("Unexpected error during token refresh")
        raise HTTPException(status_code=500, detail=f"Error refreshing token: {str(e)}")



# ---------------------------
# AUDIT LOGS
# ---------------------------
@router.get("/admin/audit_logs")
async def get_audit_logs(limit: int = 50):
    """
    Fetch recent audit logs for admin review.
    - Default limit: 50
    - Ordered by most recent first
    """
    try:
        logs = (
            db.collection("audit_logs")
            .order_by("timestamp", direction="DESCENDING")
            .limit(limit)
            .stream()
        )
        return [doc.to_dict() for doc in logs]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching audit logs: {str(e)}")


# ---------------------------
# FCM TOKEN REGISTRATION
# ---------------------------
@router.post("/register_fcm")
async def register_fcm_token(student_id: str, university: str, fcm_token: str):
    """
    Register or update a student's FCM token for push notifications.
    """
    db.collection("USERS").document(university).collection("students").document(student_id).set(
        {"fcm_token": fcm_token}, merge=True
    )
    return {"message": "FCM token registered"}



@router.post("/logout")
async def logout(refresh_token: str = Form(...)):
    """
    Logout: revoke the given refresh token.
    """
    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        jti = payload.get("jti")
        if not jti:
            raise HTTPException(status_code=400, detail="Invalid refresh token payload")

        revoke_refresh_token(jti)
        return {"message": "Logout successful"}
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid refresh token")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during logout: {str(e)}")

   
@router.get("/ping")
async def ping():
    """
    Simple health check endpoint.
    Frontend calls this every ~25 minutes to keep connection alive.
    """
    return {"message": "pong", "status": "ok"}




# Load Brevo API key and sender details from Railway env vars
BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
BREVO_SENDER_NAME = os.environ.get("BREVO_SENDER_NAME", "KLENO")
BREVO_SENDER_EMAIL = os.environ.get("BREVO_SENDER_EMAIL", "support@yourdomain.com")

configuration = sib_api_v3_sdk.Configuration()
configuration.api_key['api-key'] = BREVO_API_KEY


@router.post("/forgot_password")
async def forgot_password(email: EmailStr):
    reset_code = secrets.token_hex(3)  # 6‑digit hex code
    await save_reset_code(email, reset_code, expires=datetime.utcnow() + timedelta(minutes=10))

    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))
    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        to=[{"email": email}],
        sender={"name": BREVO_SENDER_NAME, "email": BREVO_SENDER_EMAIL},
        subject="Password Reset Code",
        html_content=f"<p>Your password reset code is <b>{reset_code}</b></p>"
    )

    try:
        api_instance.send_transac_email(send_smtp_email)
        return {"detail": "Reset code sent"}
    except ApiException as e:
        raise HTTPException(status_code=500, detail=f"Email send failed: {e}")


@router.post("/reset_password")
async def reset_password(email: EmailStr, code: str, new_password: str):
    """
    Reset password flow:
    - validate reset code
    - hash new password
    - update user password in Firestore (students / landlords / union members)
    - clear reset code
    """
    logger.info("reset_password: request for email=%s", email)
    stored_code = await get_reset_code(email)
    if not stored_code or stored_code != code:
        logger.warning("reset_password: invalid or expired code for email=%s", email)
        raise HTTPException(status_code=400, detail="Invalid or expired reset code")

    try:
        hashed_pw = get_password_hash(new_password)
    except Exception as e:
        logger.exception("reset_password: error hashing password for email=%s: %s", email, e)
        raise HTTPException(status_code=500, detail="Error processing password")

    try:
        # update_user_password is implemented in firebase.py and imported above
        updated = await update_user_password(email, hashed_pw)
        if not updated:
            logger.warning("reset_password: update_user_password returned falsy for email=%s", email)
            raise HTTPException(status_code=404, detail="User not found")
    except HTTPException:
        # re-raise HTTPExceptions so FastAPI returns the intended status
        raise
    except Exception as e:
        # Log full exception server-side for debugging
        logger.exception("reset_password: failed to update password for %s: %s", email, e)
        raise HTTPException(status_code=500, detail="Error updating password")

    try:
        await clear_reset_code(email)
    except Exception as e:
        # Non-fatal: log but still return success to user
        logger.exception("reset_password: failed to clear reset code for %s: %s", email, e)

    logger.info("reset_password: password updated successfully for email=%s", email)
    return {"detail": "Password updated successfully"}

