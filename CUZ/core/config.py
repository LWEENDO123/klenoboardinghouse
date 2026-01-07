# CUZ/ADMIN/core/config.py
import os

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
# ✅ In production, load from environment variables
SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret")  # provide a safe default
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
