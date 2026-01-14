# utils/notify.py
import httpx

API_BASE = "http://localhost:8000"   # adjust to your FastAPI host
AUTH_TOKEN = "YOUR_JWT_TOKEN"        # replace with login token

headers = {
    "Authorization": f"Bearer {AUTH_TOKEN}",
    "Content-Type": "application/json"
}

def send_notification(university: str, category: str, payload: dict):
    """
    Send a notification to the backend.
    category: "party" | "university" | "boardinghouse"
    payload: dict with title/body or template_id/params
    """
    url = f"{API_BASE}/notification/{university}/{category}/send"
    resp = httpx.post(url, headers=headers, json=payload)
    if resp.status_code == 200:
        print("✅ Notification sent:", resp.json())
    else:
        print("❌ Error:", resp.status_code, resp.text)
