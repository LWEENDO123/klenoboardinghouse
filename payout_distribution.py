import uuid
import httpx
import base64

# --- CONFIG ---
subscription_key = "26643fb684e74fb6a26d774ee240c2cf"
api_user = "33c62309-71f2-4c22-8813-b42773ad572d"
api_key = "8d86592828dd4ecc872b56a3137102e0"
target_env = "sandbox"

payee_number = "260912345678"  # MSISDN in E.164 format
amount = "50"
currency = "EUR"  # sandbox requires EUR


# --- STEP 1: Get fresh access token ---
def get_access_token():
    url = "https://sandbox.momodeveloper.mtn.com/disbursement/token/"
    basic_auth = base64.b64encode(f"{api_user}:{api_key}".encode()).decode()

    headers = {
        "Authorization": f"Basic {basic_auth}",
        "Ocp-Apim-Subscription-Key": subscription_key,
        "Content-Type": "application/json"
    }

    resp = httpx.post(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()["access_token"]


# --- STEP 2: Initiate payout with a NEW UUID ---
def initiate_payout(access_token: str):
    url = "https://sandbox.momodeveloper.mtn.com/disbursement/v1_0/transfer"
    reference_id = str(uuid.uuid4())  # fresh UUID every call

    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Reference-Id": reference_id,
        "X-Target-Environment": target_env,
        "Ocp-Apim-Subscription-Key": subscription_key,
        "Content-Type": "application/json"
    }

    payload = {
        "amount": amount,
        "currency": currency,
        "externalId": "promo123",
        "payee": {
            "partyIdType": "MSISDN",
            "partyId": payee_number
        },
        "payerMessage": "Promo code payout",
        "payeeNote": "Reward for referral"
    }

    resp = httpx.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    print("✅ Payout initiated successfully")
    print(f"Reference ID: {reference_id}")
    return reference_id


# --- STEP 3: Check payout status ---
def check_payout_status(access_token: str, ref_id: str):
    url = f"https://sandbox.momodeveloper.mtn.com/disbursement/v1_0/transfer/{ref_id}"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Target-Environment": target_env,
        "Ocp-Apim-Subscription-Key": subscription_key
    }

    resp = httpx.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    try:
        token = get_access_token()
        print("✅ Got fresh access token")
        ref_id = initiate_payout(token)
        status = check_payout_status(token, ref_id)
        print("✅ Payout status response:")
        print(status)
    except httpx.HTTPStatusError as e:
        print(f"❌ HTTP error: {e.response.status_code}")
        print("Response text:", e.response.text)
    except Exception as e:
        print(f"❌ Error: {e}")
