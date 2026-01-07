#PINNED/security.py
from fastapi import Depends, HTTPException, status
from CUZ.USERS.security import get_current_user  # Reuse base JWT decoder from USERS/security.py

async def get_premium_student(current_user: dict = Depends(get_current_user)):
    """
    Dependency to enforce premium student access.
    - Checks role="student" and premium=True.
    - Ensures user_id and university are present for validation in endpoints.
    """
    if current_user.get("role") != "student" or not current_user.get("premium", False):
        raise HTTPException(status_code=403, detail="Premium student access required")
    if not current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="User ID missing from authentication")
    if not current_user.get("university"):
        raise HTTPException(status_code=403, detail="University missing from authentication")
    return current_user
