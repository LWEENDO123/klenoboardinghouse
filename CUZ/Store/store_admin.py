# Store/store_admin.py
from fastapi import APIRouter, Depends, HTTPException
from CUZ.core.firebase import db
from .models import Store
from CUZ.core.security import get_current_admin

router = APIRouter(prefix="/admin/store", tags=["admin-store"])

@router.post("/{university}")
async def add_store(
    university: str,
    store: Store,
    current_user: dict = Depends(get_current_admin)
):
    """
    Admin-only endpoint to add a store to Store/{university}/stores/{store_id}.
    """
    try:
        # Firestore path: Store/{university}/stores/{auto_id}
        store_ref = db.collection("Store").document(university).collection("stores").document()

        store_data = store.dict(exclude={"id"})
        store_data["university"] = university
        store_data["created_by"] = current_user.get("user_id")

        store_ref.set(store_data)

        return {
            "message": "✅ Store added successfully",
            "store_id": store_ref.id,
            "data": {**store_data, "id": store_ref.id}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding store: {str(e)}")
