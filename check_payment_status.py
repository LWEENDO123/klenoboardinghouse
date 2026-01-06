import base64
import httpx

# --- CONFIG ---
subscription_key = "0a9e3fa6eb66406a8553f29d5fc3758d"
api_user = "8733cbb3-3c21-4676-b0da-d468f7bb1fad"
api_key = "aee1027103964b49a7755d8416d5c077"
target_env = "sandbox"

reference_id = "880d3c2c-9272-485e-b49e-041ed7a0d355"  # from your last request


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


# --- STEP 2: Check Payment Status ---
def check_payment_status(access_token: str, ref_id: str):
    url = f"https://sandbox.momodeveloper.mtn.com/collection/v1_0/requesttopay/{ref_id}"

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
        status = check_payment_status(token, reference_id)
        print("✅ Payment status response:")
        print(status)
        # Example response: {"amount":"100","currency":"EUR","financialTransactionId":"123456789","externalId":"123456","payer":{"partyIdType":"MSISDN","partyId":"2609XXXXXXX"},"status":"SUCCESSFUL"}
    except httpx.HTTPStatusError as e:
        print(f"❌ HTTP error: {e.response.status_code}")
        print("Response text:", e.response.text)
    except Exception as e:
        print(f"❌ Error: {e}")
