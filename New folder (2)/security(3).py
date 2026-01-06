from fastapi import Depends, HTTPException, status
from USERS.security import get_current_user  # Base JWT decoder

async def get_premium_student(current_user: dict = Depends(get_current_user)):
    """
    Dependency to enforce premium student access.
    - Checks role="student" and premium=True.
    - Ensures user_id and university are present for validation.
    """
    if current_user.get("role") != "student" or not current_user.get("premium", False):
        raise HTTPException(status_code=403, detail="Premium student access required")
    if not current_user.get("user_id") or not current_user.get("university"):
        raise HTTPException(status_code=403, detail="Missing user ID or university")
    return current_user