import uuid
import base64
import httpx

# --- CONFIG ---
subscription_key = "0a9e3fa6eb66406a8553f29d5fc3758d"
api_user = "8733cbb3-3c21-4676-b0da-d468f7bb1fad"
api_key = "aee1027103964b49a7755d8416d5c077"
target_env = "sandbox"

# Student info (replace with actual values)
student_id = "stu123"
university = "UNZA"
payer_number = "260912345678"  # must be E.164 format (no + sign in sandbox)


# --- STEP 1: Get Access Token ---
def get_access_token():
    url = "https://sandbox.momodeveloper.mtn.com/collection/token/"
    basic_auth = base64.b64encode(f"{api_user}:{api_key}".encode()).decode()

    headers = {
        "Ocp-Apim-Subscription-Key": subscription_key,
        "Authorization": f"Basic {basic_auth}",
        "Content-Type": "application/json"
    }

    resp = httpx.post(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()["access_token"]


# --- STEP 2: Request To Pay ---
def request_to_pay(access_token: str):
    url = "https://sandbox.momodeveloper.mtn.com/collection/v1_0/requesttopay"
    reference_id = str(uuid.uuid4())  # auto-generate new UUID each call

    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Reference-Id": reference_id,
        "X-Target-Environment": target_env,
        "Ocp-Apim-Subscription-Key": subscription_key,
        "Content-Type": "application/json"
    }

    payload = {
        "amount": "100",
        "currency": "EUR",  # sandbox requires EUR
        "externalId": "123456",  # must be numeric in sandbox
        "payer": {
            "partyIdType": "MSISDN",
            "partyId": payer_number
        },
        "payerMessage": f"Payment for {student_id}",
        "payeeNote": f"Premium upgrade for {university}"
    }

    resp = httpx.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return reference_id


if __name__ == "__main__":
    try:
        token = get_access_token()
        print("✅ Got fresh access token")
        ref_id = request_to_pay(token)
        print("✅ RequestToPay initiated successfully")
        print(f"Reference ID: {ref_id}")
        print("👉 Use this reference ID to check status later.")
    except httpx.HTTPStatusError as e:
        print(f"❌ HTTP error: {e.response.status_code}")
        print("Response text:", e.response.text)
    except Exception as e:
        print(f"❌ Error: {e}")
