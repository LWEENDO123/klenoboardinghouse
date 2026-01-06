import uuid
import httpx

# --- CONFIG ---
subscription_key = "26643fb684e74fb6a26d774ee240c2cf"  # your Disbursement subscription key
provider_callback_host = "https://example.com"  # replace with your callback host (sandbox accepts any valid URL)

# --- STEP 1: Generate a new UUID for the API user ---
api_user = str(uuid.uuid4())
print(f"Generated API User UUID: {api_user}")

# --- STEP 2: Create the API user ---
create_url = "https://sandbox.momodeveloper.mtn.com/v1_0/apiuser"
create_headers = {
    "Ocp-Apim-Subscription-Key": subscription_key,
    "X-Reference-Id": api_user,
    "Content-Type": "application/json"
}
create_body = {
    "providerCallbackHost": provider_callback_host
}

try:
    resp = httpx.post(create_url, headers=create_headers, json=create_body, timeout=30)
    resp.raise_for_status()
    print("✅ API User created successfully")
except httpx.HTTPStatusError as e:
    print(f"❌ Error creating API user: {e.response.status_code} - {e.response.text}")
    exit(1)

# --- STEP 3: Generate the API key for this user ---
apikey_url = f"https://sandbox.momodeveloper.mtn.com/v1_0/apiuser/{api_user}/apikey"
apikey_headers = {
    "Ocp-Apim-Subscription-Key": subscription_key,
    "Content-Length": "0"
}

try:
    resp = httpx.post(apikey_url, headers=apikey_headers, timeout=30)
    resp.raise_for_status()
    print("✅ API Key generated successfully:")
    print(resp.json())  # {"apiKey": "..."}
except httpx.HTTPStatusError as e:
    print(f"❌ Error generating API key: {e.response.status_code} - {e.response.text}")
