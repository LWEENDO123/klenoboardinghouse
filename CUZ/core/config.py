# file: CUZ/ADMIN/core/config.py
import os
import logging
from CUZ.core.firebase import db   # adjust import path if needed

# ==============================
# University Clusters
# ==============================
# Define clusters of universities that share the same region.
# This can later be loaded dynamically from Firestore if needed.
CLUSTERS = {
    "UNZA": ["UNZA", "CHRESO", "UNILUS"],
    "CHRESO": ["UNZA", "CHRESO", "UNILUS"],
    "UNILUS": ["UNZA", "CHRESO", "UNILUS"],
    "CUZ": ["CUZ"],  # standalone
}

# ==============================
# Security Settings
# ==============================
logger = logging.getLogger("core.config")

# ✅ In production, load from environment variables
SECRET_KEY = os.getenv("SECRET_KEY")  # no fallback here, force Firestore if missing
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

def get_secret_key() -> str:
    """
    Lazy-load stable JWT secret key from Firestore CONFIG/jwt if not set in env.
    """
    global SECRET_KEY
    if not SECRET_KEY:
        cfg_ref = db.collection("CONFIG").document("jwt")
        snap = cfg_ref.get()
        if not snap.exists:
            raise RuntimeError("Missing CONFIG/jwt document in Firestore")

        data = snap.to_dict() or {}
        key = data.get("SECRET_KEY")
        if not key or len(key) < 32:
            raise RuntimeError("Invalid or missing SECRET_KEY in Firestore CONFIG/jwt")

        SECRET_KEY = key
        logger.info("Loaded SECRET_KEY from Firestore")
    return SECRET_KEY
