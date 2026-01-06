import uuid
import base64
import httpx

SUBSCRIPTION_KEY = "26643fb684e74fb6a26d774ee240c2cf"
API_USER = "33c62309-71f2-4c22-8813-b42773ad572d"
API_KEY = "8d86592828dd4ecc872b56a3137102e0"
TARGET_ENV = "sandbox"

BASE_URL = "https://sandbox.momodeveloper.mtn.com"

def get_access_token(product="collection"):
    url = f"{BASE_URL}/{product}/token/"
    basic_auth = base64.b64encode(f"{API_USER}:{API_KEY}".encode()).decode()
    headers = {
        "Authorization": f"Basic {basic_auth}",
        "Ocp-Apim-Subscription-Key": SUBSCRIPTION_KEY,
        "Content-Type": "application/json"
    }
    resp = httpx.post(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()["access_token"]

def collect_payment(msisdn: str, amount: str, external_id: str):
    token = get_access_token("collection")
    ref_id = str(uuid.uuid4())
    url = f"{BASE_URL}/collection/v1_0/requesttopay"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Reference-Id": ref_id,
        "X-Target-Environment": TARGET_ENV,
        "Ocp-Apim-Subscription-Key": SUBSCRIPTION_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "amount": amount,
        "currency": "EUR",
        "externalId": external_id,
        "payer": {"partyIdType": "MSISDN", "partyId": msisdn},
        "payerMessage": "Payment",
        "payeeNote": "TutorHub subscription"
    }
    resp = httpx.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return ref_id

def payout_user(msisdn: str, amount: str, external_id: str):
    token = get_access_token("disbursement")
    ref_id = str(uuid.uuid4())
    url = f"{BASE_URL}/disbursement/v1_0/transfer"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Reference-Id": ref_id,
        "X-Target-Environment": TARGET_ENV,
        "Ocp-Apim-Subscription-Key": SUBSCRIPTION_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "amount": amount,
        "currency": "EUR",
        "externalId": external_id,
        "payee": {"partyIdType": "MSISDN", "partyId": msisdn},
        "payerMessage": "Promo payout",
        "payeeNote": "Reward"
    }
    resp = httpx.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return ref_id

def check_status(product: str, ref_id: str):
    token = get_access_token(product)
    url = f"{BASE_URL}/{product}/v1_0/requesttopay/{ref_id}" if product == "collection" \
          else f"{BASE_URL}/{product}/v1_0/transfer/{ref_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Target-Environment": TARGET_ENV,
        "Ocp-Apim-Subscription-Key": SUBSCRIPTION_KEY
    }
    resp = httpx.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()
