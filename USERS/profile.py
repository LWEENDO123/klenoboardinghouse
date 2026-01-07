#USERS/profile.py
from fastapi import APIRouter, Depends, HTTPException
from core.security import get_current_user
from USERS.firebase import get_user_by_email



router = APIRouter(prefix="/users/profile", tags=["profile"])

@router.get("/")
async def get_profile(current_user: dict = Depends(get_current_user)):
    user = await get_user_by_email(current_user["email"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # Exclude sensitive fields
    user.pop("password", None)
    return user

@router.get("/inbox")
async def get_payment_inbox(current_user: dict = Depends(get_current_user)):
    # Placeholder: Fetch payment details from Firebase or another collection
    return {"inbox": []}  # Replace with actual payment data logic