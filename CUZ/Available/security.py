# Available/security.py (updated to include user_id and university in checks if needed)
from fastapi import Depends, HTTPException, status
from USERS.security import get_current_user  # Reuse base get_current_user from USERS (assumes it decodes JWT with user_id and university)


async def get_premium_student(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "student" or not current_user.get("premium", False):
        raise HTTPException(status_code=403, detail="Premium student access required")
    # Ensure user_id exists in current_user (from JWT payload, e.g., added in create_access_token)
    if not current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="User ID missing from authentication")
    # Optionally: Ensure university is in current_user
    if not current_user.get("university"):
        raise HTTPException(status_code=403, detail="University missing from authentication")
    return current_user