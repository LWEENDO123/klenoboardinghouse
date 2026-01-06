import base64
import httpx

# Replace with your actual values
subscription_key = "0a9e3fa6eb66406a8553f29d5fc3758d"
api_user = "8733cbb3-3c21-4676-b0da-d468f7bb1fad"
api_key = "aee1027103964b49a7755d8416d5c077"

# Encode apiUser:apiKey in Base64
basic_auth = base64.b64encode(f"{api_user}:{api_key}".encode()).decode()

url = "https://sandbox.momodeveloper.mtn.com/collection/token/"

headers = {
    "Ocp-Apim-Subscription-Key": subscription_key,
    "Authorization": f"Basic {basic_auth}",
    "Content-Type": "application/json"
}

try:
    response = httpx.post(url, headers=headers, timeout=30)
    response.raise_for_status()
    print("✅ Access token response:")
    print(response.json())  # {"access_token": "...", "token_type": "Bearer", "expires_in": "3600"}
except httpx.HTTPStatusError as e:
    print(f"❌ HTTP error: {e.response.status_code} - {e.response.text}")
except Exception as e:
    print(f"❌ Error: {e}")
