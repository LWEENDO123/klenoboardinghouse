from fastapi import FastAPI, Request, UploadFile, File, Form, Depends, HTTPException, Response, Cookie
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.exceptions import RequestValidationError

import firebase_admin
from firebase_admin import credentials, storage, firestore

from typing import List
import logging
import time

# 🔐 Security + User routes
from CUZ.USERS import user_routes
from CUZ.USERS.security import require_role, verify_token, create_access_token
from CUZ.HOME import home_routes  # API endpoints

# Firestore client
from CUZ.core.firebase_config import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------
# FastAPI Setup
# -----------------------
app = FastAPI(title="BoardingHouse Backend")

# Templates (for PC dashboards)
templates = Jinja2Templates(directory="C:/Users/lweendo/project/baodinghouse/CUZ/templates")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for Flutter + Web
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Firebase init
if not firebase_admin._apps:
    cred = credentials.Certificate("C:/Users/lweendo/project/baodinghouse/CUZ/core/serviceAccountKey.json")
    firebase_admin.initialize_app(cred, {'storageBucket': 'boardinghouse-af901.appspot.com'})

# Include routes
app.include_router(user_routes.router, prefix="", tags=["Auth"])
app.include_router(home_routes.router, prefix="/api", tags=["Home API"])  # API-first

# -----------------------
# Error handler
# -----------------------
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Validation error: {exc}")
    return JSONResponse(
        status_code=422,
        content={"detail": "Invalid form data. Please check your inputs."},
    )

# -----------------------
# Web Dashboard Routes
# -----------------------

# Student Dashboard (Web)
@app.get("/home", response_class=HTMLResponse)
async def student_home(request: Request, token: str = Cookie(None)):
    """
    Student dashboard – web version.
    Reads JWT from cookie.
    """
    if not token:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Please login first"})
    try:
        user = verify_token(token)
        if user.get("role") != "student":
            raise HTTPException(status_code=403, detail="Access denied")
    except Exception:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid or expired session"})
    return templates.TemplateResponse("home.html", {"request": request, "user": user})


# Landlord Dashboard (Web)
@app.get("/landlord/dashboard", response_class=HTMLResponse)
async def landlord_dashboard(request: Request, token: str = Cookie(None)):
    """
    Landlord dashboard – web version.
    Reads JWT from cookie.
    """
    if not token:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Please login first"})
    try:
        user = verify_token(token)
        if user.get("role") != "landlord":
            raise HTTPException(status_code=403, detail="Access denied")
    except Exception:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid or expired session"})

    landlord_id = user["sub"]

    # fetch landlord’s boardinghouses (for display)
    bh_docs = db.collection("boardinghouses").where("landlordId", "==", landlord_id).stream()
    boardinghouse = next(bh_docs, None)

    if not boardinghouse:
        return templates.TemplateResponse("landlord_dashboard.html", {
            "request": request,
            "user": user,
            "boardinghouse": None
        })

    bh_data = boardinghouse.to_dict()

    editable_data = {
        "rooms": bh_data.get("rooms", {}),
        "prices": bh_data.get("prices", {}),
        "amenities": bh_data.get("amenities", []),
        "rating": bh_data.get("rating", 0),
        "images": bh_data.get("images", [])
    }

    return templates.TemplateResponse("landlord_dashboard.html", {
        "request": request,
        "user": user,
        "boardinghouse": editable_data
    })


# Web form: Add boarding house
@app.get("/add-boardinghouse", response_class=HTMLResponse)
async def get_add_boardinghouse(request: Request, token: str = Cookie(None)):
    if not token:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Please login first"})
    try:
        user = verify_token(token)
        if user.get("role") != "landlord":
            raise HTTPException(status_code=403, detail="Access denied")
    except Exception:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid or expired session"})
    return templates.TemplateResponse("add_boardinghouse.html", {"request": request})


@app.post("/add-boardinghouse")
async def add_boardinghouse_form(
    houseName: str = Form(...),
    houseLocation: str = Form(...),
    university: str = Form(...),
    landlordId: str = Form(...),
    price1: str = Form(...),
    price2: str = Form(...),
    price3: str = Form(...),
    price4: str = Form(...),
    GPSCoordinates: str = Form(...),
    yangoCoordinates: str = Form(...),
    genderMale: str = Form(...),
    genderFemale: str = Form(...),
    genderBoth: str = Form(...),
    sharedroom4: str = Form(...),
    sharedroom3: str = Form(...),
    sharedroom2: str = Form(...),
    singleroom: str = Form(...),
    amenities: str = Form(...),
    rating: float = Form(...),
    images: List[UploadFile] = File(...),
    token: str = Cookie(None)
):
    """
    Handles landlord form submission (web only).
    Uses Firebase Storage for image uploads.
    """
    if not token:
        raise HTTPException(status_code=401, detail="Login required")
    try:
        user = verify_token(token)
        if user.get("role") != "landlord":
            raise HTTPException(status_code=403, detail="Access denied")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid session")

    try:
        bucket = storage.bucket()
        image_urls = []

        for image in images:
            filename = f"boardinghouses/{int(time.time())}_{image.filename}"
            blob = bucket.blob(filename)
            blob.upload_from_file(image.file, content_type=image.content_type)
            blob.make_public()
            image_urls.append(blob.public_url)

        doc_id = f"{houseName}_{houseLocation}"
        boardinghouse_data = {
            "houseName": houseName,
            "houseLocation": houseLocation,
            "university": university,
            "landlordId": landlordId,
            "prices": {"price1": price1, "price2": price2, "price3": price3, "price4": price4},
            "coordinates": {"GPS": GPSCoordinates, "yango": yangoCoordinates},
            "gender": {
                "male": genderMale.lower() == "true",
                "female": genderFemale.lower() == "true",
                "both": genderBoth.lower() == "true"
            },
            "rooms": {
                "sharedroom4": sharedroom4,
                "sharedroom3": sharedroom3,
                "sharedroom2": sharedroom2,
                "singleroom": singleroom
            },
            "amenities": [a.strip() for a in amenities.split(",")],
            "rating": rating,
            "images": image_urls,
            "createdAt": firestore.SERVER_TIMESTAMP
        }

        db.collection("boardinghouses").document(doc_id).set(boardinghouse_data)

        return {"message": "Boarding house added successfully", "id": doc_id, "image_urls": image_urls}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# -----------------------
# Web login route (sets cookie)
# -----------------------
@app.post("/login")
async def login_web(credentials: dict, response: Response):
    """
    Login endpoint for web + mobile.
    Sets JWT cookie for web sessions.
    """
    from CUZ.USERS.security import verify_password, create_access_token
    from CUZ.USERS.models import LoginInput

    login_data = LoginInput(**credentials)
    user_doc = None

    if login_data.university:  # student login
        university = login_data.university.upper()
        doc_ref = db.collection("USERS").document(university).collection("studentinfo")
    else:  # landlord login
        doc_ref = db.collection("USERS").document("LANDLORD").collection("landlordinfo")

    query = doc_ref.where("email", "==", login_data.email).stream()
    user_doc = next(query, None)
    if not user_doc:
        raise HTTPException(status_code=401, detail="Email not registered")

    user_data = user_doc.to_dict()
    if not verify_password(login_data.password, user_data["password"]):
        raise HTTPException(status_code=401, detail="Incorrect password")

    role = user_data.get("role", "student")
    payload = {"sub": user_doc.id, "email": user_data["email"], "role": role}
    if role == "student":
        payload["university"] = login_data.university.upper()

    token = create_access_token(payload)

    # Set HttpOnly cookie for web
    response.set_cookie(key="token", value=token, httponly=True, max_age=3600)
    return {"access_token": token, "token_type": "bearer"}
    

# -----------------------
# Entry point
# -----------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
