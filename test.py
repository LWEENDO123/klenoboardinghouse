import os, base64, json

with open("serviceAccountKey.b64") as f:
    encoded = f.read().strip()

decoded = base64.b64decode(encoded).decode("utf-8")
cred_dict = json.loads(decoded)

print(cred_dict["private_key"][:50])  # should start with "-----BEGIN PRIVATE KEY-----"
