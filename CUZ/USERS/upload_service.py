# file: CUZ/USERS/upload_service.py
from fastapi import APIRouter, UploadFile, File, HTTPException
from datetime import datetime
import aiofiles
import os
from core.firebase import db  # Firestore client

router = APIRouter(prefix="/upload", tags=["upload"])

RAILWAY_BUCKET_PATH = "/railway/storage/bucket"  # adjust to your Railway mount path
RAILWAY_PUBLIC_URL = "https://your-railway-app-url/bucket"  # base URL for serving files

@router.post("/event_image")
async def upload_event_image(university: str, student_id: str, event_id: str, file: UploadFile = File(...)):
    """
    Upload an image to Railway bucket, store URL in Firestore.
    """
    try:
        # Validate file type
        if not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="Only image files are allowed")

        # Generate filename
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        filename = f"{student_id}_{event_id}_{timestamp}_{file.filename}"

        # Save to Railway bucket (local mount path)
        file_path = os.path.join(RAILWAY_BUCKET_PATH, filename)
        async with aiofiles.open(file_path, "wb") as out_file:
            content = await file.read()
            await out_file.write(content)

        # Generate public URL
        public_url = f"{RAILWAY_PUBLIC_URL}/{filename}"

        # Save metadata in Firestore
        db.collection("EVENT_IMAGES").document(event_id).collection("uploads").add({
            "student_id": student_id,
            "university": university,
            "filename": filename,
            "url": public_url,
            "uploaded_at": datetime.utcnow().isoformat()
        })

        return {"status": "success", "url": public_url}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
