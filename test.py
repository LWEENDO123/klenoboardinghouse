import httpx

# Replace with your actual values
subscription_key = "0a9e3fa6eb66406a8553f29d5fc3758d"
user_id = "8733cbb3-3c21-4676-b0da-d468f7bb1fad"

url = f"https://sandbox.momodeveloper.mtn.com/v1_0/apiuser/{user_id}/apikey"

headers = {
    "Ocp-Apim-Subscription-Key": subscription_key,
    "Content-Length": "0"  # explicitly indicate empty body
}

try:
    response = httpx.post(url, headers=headers, timeout=30)
    response.raise_for_status()
    print("✅ API Key generated successfully:")
    print(response.json())  # response contains {"apiKey": "..."}
except httpx.HTTPStatusError as e:
    print(f"❌ HTTP error: {e.response.status_code} - {e.response.text}")
except Exception as e:
    print(f"❌ Error: {e}")
