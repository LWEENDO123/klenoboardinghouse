#Event/security.py
from fastapi import Depends, HTTPException
from USERS.security import get_current_user

async def get_current_student(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "student":
        raise HTTPException(status_code=403, detail="Student access required")
    if not current_user.get("user_id") or not current_user.get("university"):
        raise HTTPException(status_code=403, detail="Missing user ID or university")
    return current_user

async def get_premium_student(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "student" or not current_user.get("premium", False):
        raise HTTPException(status_code=403, detail="Premium student access required")
    return current_user

async def get_student_union_or_admin(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ["student_union", "admin"]:
        raise HTTPException(status_code=403, detail="Student union or admin access required")
    return current_user
