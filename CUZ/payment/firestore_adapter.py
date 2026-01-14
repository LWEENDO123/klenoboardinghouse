from google.cloud import firestore
from google.oauth2 import service_account
import os, json

# ------------------------------
# Firestore client initialization with explicit credentials
# ------------------------------

# Load service account JSON from Railway environment variable
SERVICE_ACCOUNT_JSON = os.getenv("serviceAccountKey")

if not SERVICE_ACCOUNT_JSON:
    raise FileNotFoundError("Environment variable 'serviceAccountKey' is missing or empty")

try:
    # Parse JSON string into dict
    service_account_info = json.loads(SERVICE_ACCOUNT_JSON)
except json.JSONDecodeError as e:
    raise ValueError(f"Invalid JSON in 'serviceAccountKey': {str(e)}")

# Build credentials from dict
credentials = service_account.Credentials.from_service_account_info(service_account_info)

# Initialize Firestore client with fixed project ID
db = firestore.Client(credentials=credentials, project="boardinghouse-af901")
print("🔥 firestore_adapter using project:", db.project)




# ------------------------------
# Helpers
# ------------------------------
def _server_ts():
    # Prefer Firestore server timestamp where auditability matters
    return firestore.SERVER_TIMESTAMP


# ------------------------------
# Student record functions
# ------------------------------
def get_student_record(student_id: str, university: str) -> dict:
    doc = (
        db.collection("USERS")
        .document(university)
        .collection("students")
        .document(student_id)
        .get()
    )
    if doc.exists:
        return doc.to_dict()
    # Provide stable defaults
    return {
        "payments": [],
        "used_referral_codes": [],
        "msisdn": None,
        "phone_number": None,
        "premium": False,
    }

def save_student_record(student_id: str, university: str, record: dict) -> None:
    # Ensure we keep audit-friendly timestamps
    if "updated_at" not in record:
        record["updated_at"] = datetime.utcnow().isoformat()
    (
        db.collection("USERS")
        .document(university)
        .collection("students")
        .document(student_id)
        .set(record)
    )

def append_payment(student_id: str, university: str, payment: dict) -> None:
    # Keep a summary array (optional if you move fully to subcollection)
    (
        db.collection("USERS")
        .document(university)
        .collection("students")
        .document(student_id)
        .update({"payments": firestore.ArrayUnion([payment])})
    )

def append_payment_idempotent(student_id: str, university: str, transaction_id: str, payment: dict) -> None:
    """
    Idempotent payment write:
    - Stores payment under a subcollection keyed by transaction_id.
    - Optionally mirrors to summary array for fast aggregation.
    """
    payments_ref = (
        db.collection("USERS")
        .document(university)
        .collection("students")
        .document(student_id)
        .collection("payments")
        .document(transaction_id)
    )
    snap = payments_ref.get()
    if not snap.exists:
        payment_record = {
            **payment,
            "created_at": datetime.utcnow().isoformat(),
            "created_at_server": _server_ts(),
        }
        payments_ref.set(payment_record)

    # Mirror to summary (safe even if duplicate — ArrayUnion ensures set semantics on exact object match)
    append_payment(student_id, university, payment)


def mark_code_used(student_id: str, university: str, code: str) -> None:
    (
        db.collection("USERS")
        .document(university)
        .collection("students")
        .document(student_id)
        .update({"used_referral_codes": firestore.ArrayUnion([code])})
    )


# ------------------------------
# Referral code functions
# ------------------------------
def ensure_referral_code_doc(code: str) -> None:
    """
    Ensure referral code doc exists with sane defaults to avoid update failures.
    """
    ref = db.collection("referral_codes").document(code)
    snap = ref.get()
    if not snap.exists:
        ref.set({
            "currentUses": 0,
            "usages": [],
            "created_at": datetime.utcnow().isoformat(),
            "created_at_server": _server_ts(),
        })

def increment_referral_use(code: str, used_by: str, payout_id: str, payout_status: str, payout_amount: float = 20) -> None:
    ensure_referral_code_doc(code)
    usage = {
        "usedBy": used_by,
        "usedAt": datetime.utcnow().isoformat(),
        "payoutId": payout_id,
        "payoutAmount": payout_amount,
        "payoutStatus": payout_status,
        "usedAtServer": _server_ts(),
    }
    (
        db.collection("referral_codes")
        .document(code)
        .update({
            "currentUses": firestore.Increment(1),
            "usages": firestore.ArrayUnion([usage]),
        })
    )


# ------------------------------
# Union member functions
# ------------------------------
def get_union_member_by_code(university: str, code: str):
    """
    Look up a union member by referral code in USERS/{university}/studentunion.
    Returns (union_id, union_doc) if found, otherwise (None, None).
    """
    docs = (
        db.collection("USERS")
        .document(university)
        .collection("studentunion")
        .where("referral_code", "==", code)
        .stream()
    )
    for doc in docs:
        return doc.id, doc.to_dict()
    return None, None

def log_union_payout(university: str, union_id: str, payout: dict) -> None:
    """
    Append a payout record to the union member document.
    """
    payout_record = {
        **payout,
        "logged_at": datetime.utcnow().isoformat(),
        "logged_at_server": _server_ts(),
    }
    (
        db.collection("USERS")
        .document(university)
        .collection("studentunion")
        .document(union_id)
        .update({"payouts": firestore.ArrayUnion([payout_record])})
    )


# ------------------------------
# Gateway error logs
# ------------------------------
def log_gateway_error(entry: dict) -> None:
    payload = {
        **entry,
        "ts": datetime.utcnow().isoformat(),
        "ts_server": _server_ts(),
    }
    db.collection("gateway_logs").add(payload)


# ------------------------------
# Duplicate payout guard
# ------------------------------
def has_payout_for_transaction(transaction_id: str) -> bool:
    """
    Check across all universities and union members if a transactionId
    has already been logged in payouts.
    """
    universities = db.collection("USERS").stream()
    for uni_doc in universities:
        unions = (
            db.collection("USERS")
            .document(uni_doc.id)
            .collection("studentunion")
            .stream()
        )
        for union_doc in unions:
            payouts = union_doc.to_dict().get("payouts", [])
            if any(p.get("transactionId") == transaction_id or p.get("payoutId") == transaction_id for p in payouts):
                return True
    return False


# ------------------------------
# Union notifications (simplified for dashboard)
# ------------------------------
def log_union_simple_notification(university: str, union_id: str, transaction_id: str, status: str) -> None:
    """
    Store a simplified notification for a union member.
    Only transactionId + message + timestamp are visible to the union dashboard.
    Full payout details remain logged via log_union_payout.
    """
    notif = {
        "transactionId": transaction_id,
        "message": f"Referral payout update - Status: {status}",
        "timestamp": datetime.utcnow().isoformat(),
        "timestamp_server": _server_ts(),
        "read": False,
    }
    (
        db.collection("USERS")
        .document(university)
        .collection("studentunion")
        .document(union_id)
        .collection("notifications")
        .add(notif)
    )



def log_payout_atomic(university: str, union_id: str, referral_code: str,
                      student_id: str, payout_id: str, payout_status: str,
                      payout_data: dict) -> None:
    """
    Atomically log a payout, increment referral usage, and add a notification.
    Uses the credentialed Firestore client initialized at the top of the file.
    """
    def txn_fn(transaction):
        union_ref = db.collection("USERS").document(university).collection("studentunion").document(union_id)
        referral_ref = db.collection("referral_codes").document(referral_code)
        notif_ref = union_ref.collection("notifications").document()

        # Union payout
        transaction.update(union_ref, {
            "payouts": firestore.ArrayUnion([{
                **payout_data,
                "loggedAt": datetime.utcnow().isoformat(),
                "loggedAtServer": _server_ts(),
            }])
        })

        # Referral usage
        usage = {
            "usedBy": student_id,
            "usedAt": datetime.utcnow().isoformat(),
            "payoutId": payout_id,
            "payoutStatus": payout_status,
            "usedAtServer": _server_ts(),
        }
        transaction.update(referral_ref, {
            "currentUses": firestore.Increment(1),
            "usages": firestore.ArrayUnion([usage]),
        })

        # Notification
        notif = {
            "transactionId": payout_id,
            "message": f"Referral payout update - Status: {payout_status}",
            "timestamp": datetime.utcnow().isoformat(),
            "timestampServer": _server_ts(),
            "read": False,
        }
        transaction.set(notif_ref, notif)

    db.transaction()(txn_fn)


def log_collection_atomic(student_id: str, university: str, transaction_id: str,
                          amount: float, status: str, operator: str, reference: str) -> None:
    """
    Atomically log a mobile money collection into student record.
    Uses the credentialed Firestore client initialized at the top of the file.
    """
    def txn_fn(transaction):
        student_ref = db.collection("USERS").document(university).collection("students").document(student_id)
        payment = {
            "transactionId": transaction_id,
            "amount": amount,
            "status": status,
            "operator": operator,
            "reference": reference,
            "loggedAt": datetime.utcnow().isoformat(),
            "loggedAtServer": _server_ts(),
        }
        transaction.update(student_ref, {
            "payments": firestore.ArrayUnion([payment]),
        })

    db.transaction()(txn_fn)
