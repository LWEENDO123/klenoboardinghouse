# file: CUZ/media/upload.py
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from CUZ.yearbook.profile.compress import compress_to_720, upload_to_firebase
from CUZ.yearbook.profile.video import upload_video_to_firebase

router = APIRouter(prefix="/media", tags=["media"])

@router.post("/upload")
async def upload_media(
    university: str = Form(...),
    type: str = Form(...),  # "image" or "video"
    file: UploadFile = File(...)
):
    try:
        content = await file.read()
        student_id = "admin"  # or pass this from frontend if needed

        if type == "image":
            compressed = compress_to_720(content)
            url = upload_to_firebase(university, student_id, compressed, file.filename)
        elif type == "video":
            url = upload_video_to_firebase(university, student_id, content, file.filename, public=True)
        else:
            raise HTTPException(status_code=400, detail="Invalid type. Must be 'image' or 'video'.")

        return {"url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
