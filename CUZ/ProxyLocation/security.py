#Proxylocation/ssecurity.py
from fastapi import Depends, HTTPException
from USERS.security import get_current_user  # Base JWT decoder from USERS
from USERS.security import (
    get_student_or_admin,
    get_premium_student_or_admin,
)


async def get_student_or_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """
    Dependency for routes where students are the main users,
    but admins have override rights.
    - Allows role="student" (any tier) or role="admin".
    - Blocks landlords.
    """
    role = current_user.get("role")
    if role not in ("student", "admin"):
        raise HTTPException(status_code=403, detail="Access restricted to students or admins")

    if not current_user.get("user_id") or not current_user.get("university"):
        raise HTTPException(status_code=400, detail="Missing user ID or university")

    return current_user


async def get_premium_student_or_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """
    Dependency for premium-only student routes,
    with admin override rights.
    - Allows role="student" with premium=True, or role="admin".
    - Blocks landlords.
    """
    role = current_user.get("role")

    if role == "student":
        if not current_user.get("premium", False):
            raise HTTPException(status_code=403, detail="Premium student access required")
    elif role != "admin":
        raise HTTPException(status_code=403, detail="Access restricted to premium students or admins")

    if not current_user.get("user_id") or not current_user.get("university"):
        raise HTTPException(status_code=400, detail="Missing user ID or university")

    return current_user
