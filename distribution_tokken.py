import base64
import httpx

subscription_key = "26643fb684e74fb6a26d774ee240c2cf"
api_user = "33c62309-71f2-4c22-8813-b42773ad572d"
api_key = "8d86592828dd4ecc872b56a3137102e0"

url = "https://sandbox.momodeveloper.mtn.com/disbursement/token/"
basic_auth = base64.b64encode(f"{api_user}:{api_key}".encode()).decode()

headers = {
    "Authorization": f"Basic {basic_auth}",
    "Ocp-Apim-Subscription-Key": subscription_key,
    "Content-Type": "application/json"
}

try:
    resp = httpx.post(url, headers=headers, timeout=30)
    resp.raise_for_status()
    print("✅ Access token response:")
    print(resp.json())  # {"access_token": "...", "token_type": "Bearer", "expires_in": "3600"}
except httpx.HTTPStatusError as e:
    print(f"❌ HTTP error: {e.response.status_code} - {e.response.text}")
