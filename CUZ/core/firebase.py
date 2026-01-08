import os
import json
import base64
import logging
import firebase_admin
from firebase_admin import credentials, firestore, storage
from datetime import datetime

# ============================================================
# 🔧 Logging setup
# ============================================================

logger = logging.getLogger("core.firebase")
logger.setLevel(logging.DEBUG)

handler = logging.StreamHandler()
formatter = logging.Formatter(
    "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s"
)
handler.setFormatter(formatter)
logger.addHandler(handler)

# ============================================================
# 🌍 Environment variables
# ============================================================

FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID")
FIREBASE_BUCKET = os.getenv("FIREBASE_BUCKET")
FIREBASE_SERVICE_ACCOUNT_BASE64 = os.getenv("FIREBASE_SERVICE_ACCOUNT_BASE64")

logger.info("Boot time (UTC): %s", datetime.utcnow().isoformat())

if not FIREBASE_PROJECT_ID:
    raise RuntimeError("❌ FIREBASE_PROJECT_ID is not set")

if not FIREBASE_SERVICE_ACCOUNT_BASE64:
    raise RuntimeError("❌ FIREBASE_SERVICE_ACCOUNT_BASE64 is not set")

if not FIREBASE_BUCKET:
    FIREBASE_BUCKET = f"{FIREBASE_PROJECT_ID}.appspot.com"

# ============================================================
# 🔐 Decode service account
# ============================================================

try:
    decoded_bytes = base64.b64decode(FIREBASE_SERVICE_ACCOUNT_BASE64)
    decoded_json = decoded_bytes.decode("utf-8")
    firebase_cred_dict = json.loads(decoded_json)

except Exception:
    logger.exception("❌ Failed to decode FIREBASE_SERVICE_ACCOUNT_BASE64")
    raise

# ============================================================
# 🔎 Deep credential diagnostics
# ============================================================

REQUIRED_KEYS = {
    "type",
    "project_id",
    "private_key_id",
    "private_key",
    "client_email",
    "client_id",
    "token_uri",
}

missing = REQUIRED_KEYS - firebase_cred_dict.keys()
if missing:
    raise RuntimeError(f"❌ Missing keys in service account JSON: {missing}")

logger.info("Service account email: %s", firebase_cred_dict["client_email"])
logger.info("Service account project_id: %s", firebase_cred_dict["project_id"])
logger.info("Expected project_id: %s", FIREBASE_PROJECT_ID)

# ⚠️ Project mismatch warning
if firebase_cred_dict["project_id"] != FIREBASE_PROJECT_ID:
    logger.warning(
        "⚠️ PROJECT MISMATCH! JSON=%s ENV=%s",
        firebase_cred_dict["project_id"],
        FIREBASE_PROJECT_ID,
    )

private_key = firebase_cred_dict["private_key"]

# ============================================================
# 🚨 PRIVATE KEY VALIDATION (CRITICAL)
# ============================================================

if "-----BEGIN PRIVATE KEY-----" not in private_key:
    raise RuntimeError("❌ Private key missing BEGIN marker")

if "-----END PRIVATE KEY-----" not in private_key:
    raise RuntimeError("❌ Private key missing END marker")

if "\\n" in private_key:
    logger.warning(
        "⚠️ Private key contains escaped newlines (\\\\n). Fixing automatically."
    )
    firebase_cred_dict["private_key"] = private_key.replace("\\n", "\n")

logger.debug(
    "Private key fingerprint (first 40 chars): %s",
    firebase_cred_dict["private_key"][:40],
)

# ============================================================
# 🚀 Firebase Admin initialization
# ============================================================

try:
    cred = credentials.Certificate(firebase_cred_dict)

    if not firebase_admin._apps:
        app = firebase_admin.initialize_app(
            cred,
            {
                "projectId": FIREBASE_PROJECT_ID,
                "storageBucket": FIREBASE_BUCKET,
            },
        )
        logger.info("🔥 Firebase app initialized")

    db = firestore.client()
    logger.info("🔥 Firestore connected (project=%s)", db.project)

    bucket = storage.bucket()
    logger.info("🔥 Storage bucket ready (%s)", bucket.name)

except Exception:
    logger.exception("❌ Firebase initialization failed")
    raise

# ============================================================
# 📦 Exports
# ============================================================

__all__ = ["db", "bucket"]
