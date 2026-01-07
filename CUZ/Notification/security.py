# Notification/security.py
from fastapi import Depends, HTTPException, status
from CUZ.USERS.security import get_current_user  # Base JWT from USERS

async def get_current_student(current_user: dict = Depends(get_current_user)):
    """Public access for any student (no premium check)."""
    if current_user.get("role") != "student":
        raise HTTPException(status_code=403, detail="Student access required")
    return current_user

async def get_admin_or_landlord(current_user: dict = Depends(get_current_user)):
    """For sending notifications (admin or landlord only)."""
    if current_user.get("role") not in ["admin", "landlord"]:
        raise HTTPException(status_code=403, detail="Admin or landlord access required")
    return current_user
