# file: CUZ/HOME/add_boardinghouse.py
from fastapi import APIRouter, Depends, HTTPException, Body, Form, File, UploadFile
from CUZ.HOME.models import BoardingHouse              # ✅ models inside CUZ/HOME
from CUZ.core.firebase import db                       # ✅ firebase inside CUZ/core
from CUZ.core.config import CLUSTERS                   # ✅ config inside CUZ/core
from datetime import datetime
from firebase_admin import messaging
from CUZ.USERS.security import get_current_admin, get_admin_or_landlord  # ✅ security inside CUZ/USERS
import random
import string
from CUZ.yearbook.profile.compress import compress_to_720
from CUZ.yearbook.profile.storage import s3_client, RAILWAY_BUCKET
import asyncio
import aiohttp
import tempfile
import subprocess
import os
from pathlib import Path
from typing import List, Dict, Optional

from fastapi import HTTPException
from google.cloud import firestore  # if you use Firestore (you already do)

import uuid
from fastapi import Path

from datetime import datetime
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

router = APIRouter(prefix="/boardinghouse", tags=["boardinghouse"])


# ---------------------------
# Helper: Generate boarding house ID
# ---------------------------
def generate_boardinghouse_id(landlord_name: str) -> str:
    """
    Generate a boarding house ID like ShJohn123456789
    """
    try:
        parts = landlord_name.strip().split()
        if len(parts) >= 2:
            first_letter = parts[0][0].upper()
            second_letter = parts[1][0].upper()
        else:
            first_letter = parts[0][0].upper()
            second_letter = random.choice(string.ascii_uppercase)
        random_digits = ''.join(random.choices(string.digits, k=9))
        return f"{first_letter}{second_letter}{random_digits}"
    except Exception:
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))


# ---------------------------
# ADMIN: Assign boarding house
# ---------------------------



# import boto3  # if you use S3
# from google.cloud import storage  # if you use GCS

# existing imports and router setup assumed
# db = firestore.Client()  # your existing Firestore client

async def _download_to_tempfile(url: str, timeout: int = 30) -> Optional[str]:
    """Download a remote file to a temporary file and return the local path, or None on failure."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=timeout) as resp:
                if resp.status != 200:
                    return None
                suffix = Path(url).suffix or ".bin"
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    content = await resp.read()
                    tmp.write(content)
                    return tmp.name
    except Exception as e:
        # log if you have a logger
        print(f"_download_to_tempfile error for {url}: {e}")
        return None

def _generate_thumbnail_ffmpeg(video_path: str, out_path: str, time_sec: int = 2, width: int = 640) -> bool:
    """
    Use ffmpeg to generate a single-frame JPEG thumbnail.
    Returns True on success, False on failure.
    """
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-ss", str(time_sec),
            "-i", video_path,
            "-vframes", "1",
            "-vf", f"scale={width}:-1",
            "-q:v", "3",
            out_path,
        ]
        # run synchronously; ffmpeg must be installed on the server
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return os.path.exists(out_path)
    except Exception as e:
        print(f"_generate_thumbnail_ffmpeg error for {video_path}: {e}")
        return False

async def _generate_and_upload_thumbnail(video_url: str, dest_key_prefix: str = "thumbnails/") -> Optional[str]:
    """
    Download video_url, generate thumbnail, upload it, and return the public thumbnail URL.
    Returns None on failure.
    """
    local_video = None
    local_thumb = None
    try:
        local_video = await _download_to_tempfile(video_url)
        if not local_video:
            print(f"Failed to download video: {video_url}")
            return None

        # create temp file for thumbnail
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_thumb:
            local_thumb = tmp_thumb.name

        ok = _generate_thumbnail_ffmpeg(local_video, local_thumb, time_sec=2, width=640)
        if not ok:
            print(f"ffmpeg failed to create thumbnail for {video_url}")
            return None

        # Build destination path/key for storage (customize naming as needed)
        filename = Path(video_url).stem
        dest_key = f"{dest_key_prefix}{filename}_thumb.jpg"

        # Upload the thumbnail and return the public URL
        # You must implement upload_file_to_storage(local_path, dest_key) to match your storage provider.
        # Example: return await upload_file_to_storage(local_thumb, dest_key)
        thumb_url = await upload_file_to_storage(local_thumb, dest_key)
        return thumb_url
    except Exception as e:
        print(f"_generate_and_upload_thumbnail error for {video_url}: {e}")
        return None
    finally:
        # cleanup temp files
        try:
            if local_video and os.path.exists(local_video):
                os.remove(local_video)
            if local_thumb and os.path.exists(local_thumb):
                os.remove(local_thumb)
        except Exception:
            pass

# Placeholder: implement this for your storage provider.
# Example implementations:
# - For Google Cloud Storage: use google.cloud.storage.Client().bucket(...).blob(dest_key).upload_from_filename(...)
# - For AWS S3: use boto3.client('s3').upload_file(local_path, bucket, dest_key, ExtraArgs={'ACL':'public-read', 'ContentType':'image/jpeg'})
# storage.py already defines: s3_client, RAILWAY_BUCKET, BASE_URL

async def upload_file_to_storage(local_path: str, dest_key: str) -> Optional[str]:
    """
    Upload local_path to Railway Object Storage and return a permanent proxy URL.
    """
    try:
        # Read file bytes
        with open(local_path, "rb") as f:
            file_bytes = f.read()

        # Upload to bucket
        s3_client.put_object(
            Bucket=RAILWAY_BUCKET,
            Key=dest_key,
            Body=file_bytes,
            ContentType="image/jpeg",
        )

        # Return proxy URL (served via your FastAPI /media route)
        return f"{BASE_URL}/media/{dest_key}"
    except Exception as e:
        logger.error(f"❌ Failed to upload {local_path} to storage: {e}", exc_info=True)
        return None


# ---------------- Updated endpoint ----------------
@router.post("/admin/assign_boardinghouse")
async def assign_boardinghouse(
    boardinghouse: BoardingHouse,
    current_user: dict = Depends(get_current_admin)
):
    try:
        landlord_name = boardinghouse.name
        universities = getattr(boardinghouse, "universities", [current_user.get("university")])
        bh_id = generate_boardinghouse_id(landlord_name)

        # Build gallery: images first (type=image), then videos (type=video + thumbnail_url)
        gallery: List[Dict] = []

        # Add images (if any)
        for img in (boardinghouse.images or []):
            gallery.append({"type": "image", "url": img, "thumbnail_url": None})

        # For videos: attempt to generate/upload thumbnail (async)
        video_urls = boardinghouse.videos or []
        # Kick off thumbnail generation tasks in parallel
        thumb_tasks = [asyncio.create_task(_generate_and_upload_thumbnail(v)) for v in video_urls]
        # Wait for all to finish
        thumb_results = await asyncio.gather(*thumb_tasks, return_exceptions=True)

        for idx, v in enumerate(video_urls):
            thumb_url = None
            res = thumb_results[idx]
            if isinstance(res, Exception):
                print(f"thumbnail task exception for {v}: {res}")
                thumb_url = None
            else:
                thumb_url = res  # may be None if generation/upload failed

            gallery.append({"type": "video", "url": v, "thumbnail_url": thumb_url})

        # Prepare data for storage
        boardinghouse_data = boardinghouse.dict(exclude_unset=True)
        boardinghouse_data.update({
            "id": bh_id,
            "created_at": SERVER_TIMESTAMP,
            "videos": video_urls,
            "voice_notes": boardinghouse.voice_notes or [],
            "images": boardinghouse.images or [],
            "gallery": gallery,  # new structured gallery field
            "space_description": boardinghouse.space_description or "Kleno will update you when number of space is available.",
            "conditions": boardinghouse.conditions or None,
            "public_T": boardinghouse.public_T or None,
            "rating": boardinghouse.rating,
            "gender_male": boardinghouse.gender_male,
            "gender_female": boardinghouse.gender_female,
            "gender_both": boardinghouse.gender_both,
            "GPS_coordinates": boardinghouse.GPS_coordinates or None,
            "yango_coordinates": boardinghouse.yango_coordinates or None,
            "cover_image": boardinghouse.cover_image or None,
            "phone_number": boardinghouse.phone_number or None,
        })

        # Save under each university's HOME collection
        for univ in universities:
            univ_ref = db.collection("HOME").document(univ)
            if not univ_ref.get().exists:
                univ_ref.set({
                    "created_at": SERVER_TIMESTAMP,
                    "status": "active",
                    "description": f"Auto-created HOME/{univ}"
                })
            univ_ref.collection("BOARDHOUSE").document(bh_id).set(boardinghouse_data)

        # Save globally
        db.collection("BOARDINGHOUSES").document(bh_id).set({
            **boardinghouse_data,
            "universities": universities
        })

        return {
            "message": "✅ Boarding house assigned successfully",
            "boardinghouse_id": bh_id,
            "stored_in": [f"HOME/{u}/BOARDHOUSE" for u in universities] + ["BOARDINGHOUSES (global)"],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error assigning boarding house: {str(e)}")



# ---------------------------
# LANDLORD: Create boarding house
# ---------------------------
@router.post("/landlord/create", response_model=dict)
async def create_boardinghouse(
    boardinghouse: BoardingHouse,
    current_user: dict = Depends(get_admin_or_landlord)
):
    """
    Landlord creates a boarding house listing.
    - Stores globally and under each university HOME collection.
    - Accepts multiple images (slider/gallery).
    - Broadcasts to landlords_{university} channel.
    """
    try:
        landlord_id = current_user.get("user_id")
        if current_user.get("role") not in ["landlord", "admin"]:
            raise HTTPException(status_code=403, detail="Only landlords or admins can create boarding houses")

        universities = getattr(boardinghouse, "universities", [current_user.get("university")])
        boardinghouse_data = boardinghouse.dict(exclude_unset=True)

        bh_id = generate_boardinghouse_id(boardinghouse.name)
        boardinghouse_data.update({
            "id": bh_id,
            "landlord_id": landlord_id,
            "created_at": datetime.utcnow()
        })

        # Save under each university HOME collection
        for univ in universities:
            univ_ref = db.collection("HOME").document(univ)
            if not univ_ref.get().exists:
                univ_ref.set({
                    "created_at": datetime.utcnow(),
                    "status": "active",
                    "description": f"Auto-created HOME/{univ}"
                })
            univ_ref.collection("BOARDHOUSE").document(bh_id).set(boardinghouse_data)

        # Save globally
        db.collection("BOARDINGHOUSES").document(bh_id).set({
            **boardinghouse_data,
            "universities": universities
        })

        # Broadcast to landlords channel
        for univ in universities:
            topic = f"landlords_{univ}"
            message = messaging.Message(
                notification=messaging.Notification(
                    title="New Boarding House Added",
                    body=f"{boardinghouse.name} has been listed with {len(boardinghouse.images)} photos."
                ),
                topic=topic,
                data={"boardinghouse_id": bh_id}
            )
            messaging.send(message)

        return {
            "message": "✅ Boarding house created successfully",
            "boardinghouse_id": bh_id,
            "stored_in": [f"HOME/{u}/BOARDHOUSE" for u in universities] + ["BOARDINGHOUSES (global)"],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating boarding house: {str(e)}")


# ---------------------------
# LANDLORD: Update availability
# ---------------------------
@router.patch("/landlord/update_availability/{id}")
async def update_availability(
    id: str,
    university: str,
    updates: dict = Body(...),
    current_user: dict = Depends(get_admin_or_landlord)
):
    """
    Landlord updates availability of a boarding house and notifies students.
    - Updates global BOARDINGHOUSES document and all university references.
    - Sends notifications across all universities the boarding house serves.
    """
    # ✅ Identity check
    if university != current_user.get("university") and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="University mismatch")

    try:
        # ✅ Fetch global boarding house doc
        boardinghouse_ref = db.collection("BOARDINGHOUSES").document(id)
        boardinghouse_doc = boardinghouse_ref.get()
        if not boardinghouse_doc.exists:
            raise HTTPException(status_code=404, detail="Boarding house not found")

        data = boardinghouse_doc.to_dict()
        landlord_id = current_user.get("user_id")

        # ✅ Ownership check
        if data.get("landlord_id") != landlord_id and current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="You do not have permission to update this boarding house")

        # ✅ Allowed fields
        allowed_fields = {
            "sharedroom_4", "price_4",
            "sharedroom_3", "price_3",
            "sharedroom_2", "price_2",
            "singleroom", "price_1"
        }
        update_data = {key: value for key, value in updates.items() if key in allowed_fields}
        if not update_data:
            raise HTTPException(status_code=400, detail="No valid fields to update")

        # ✅ Update global + university references
        boardinghouse_ref.update(update_data)
        universities = data.get("universities", [])
        for univ in universities:
            db.collection("HOME").document(univ).collection("BOARDHOUSE").document(id).update(update_data)

        # ✅ Build notification
        bh_name = data.get("name", "A boarding house")
        detail_url = f"/home/boardinghouse/{id}"
        title = "New Availability"
        body = f"{bh_name} has updated room availability."

        premium_topic = f"boardinghouse_{university}_premium"
        generic_topic = f"boardinghouse_{university}_generic"

        # ✅ Send premium notification
        premium_msg = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            topic=premium_topic,
            data={"boardinghouse_id": id, "detail_url": detail_url}
        )
        messaging.send(premium_msg)

        # ✅ Send generic notification
        generic_msg = messaging.Message(
            notification=messaging.Notification(
                title="New Availability",
                body="A boarding house near you has an opening."
            ),
            topic=generic_topic,
            data={"boardinghouse_id": id}
        )
        messaging.send(generic_msg)

        # ✅ Store notification in Firestore
        notif_data = {
            "title": title,
            "body": body,
            "category": "boardinghouse",
            "boardinghouse_id": id,
            "detail_url": detail_url,
            "timestamp": datetime.utcnow(),
            "read_by": []
        }
        for univ in universities:
            db.collection("USERS").document(univ).collection("notifications").add(notif_data)

        return {"message": f"Availability updated for boarding house {id}"}

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating availability: {str(e)}")







@router.delete("/admin/delete/{id}", response_model=dict)
async def delete_boardinghouse(
    id: str = Path(..., description="Boarding house ID to delete"),
    university: str = Body(..., embed=True, description="University to delete from"),
    current_user: dict = Depends(get_current_admin)
):
    """
    Permanently delete a boarding house from both global and university collections.
    Admin-only access.
    """
    try:
        # Check if the boarding house exists globally
        global_ref = db.collection("BOARDINGHOUSES").document(id)
        global_doc = global_ref.get()
        if not global_doc.exists:
            raise HTTPException(status_code=404, detail="Boarding house not found")

        # Delete from global
        global_ref.delete()

        # Delete from university-scoped collection
        scoped_ref = db.collection("HOME").document(university).collection("BOARDHOUSE").document(id)
        if scoped_ref.get().exists:
            scoped_ref.delete()

        return {
            "message": f"🗑️ Boarding house {id} deleted successfully",
            "deleted_from": [f"BOARDINGHOUSES", f"HOME/{university}/BOARDHOUSE"]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting boarding house: {str(e)}")


@router.post("/upload")
async def upload_media(
    university: str = Form(...),
    student_id: str = Form(None),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_admin),
):
    try:
        # ✅ LAZY IMPORT (BREAKS CIRCULAR IMPORT)
        from CUZ.yearbook.profile.storage import upload_file_bytes

        contents = await file.read()

        if not contents:
            raise HTTPException(status_code=400, detail="Empty file upload")

        content_type = file.content_type or "application/octet-stream"

        # Compress if it's an image
        if content_type.startswith("image/"):
            contents = compress_to_720(contents)

        sid = student_id or current_user.get("user_id") or "admin"

        # Generate a clean, unique key
        unique_id = uuid.uuid4()
        clean_filename = file.filename.replace(" ", "_")
        key = f"{university}/{sid}/{unique_id}_{clean_filename}"

        # The storage function now returns a permanent public URL
        url = upload_file_bytes(
            key=key,
            file_bytes=contents,
            content_type=content_type,
        )

        return {
            "url": url,
            "filename": file.filename,
            "content_type": content_type,
            "uploaded_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")






