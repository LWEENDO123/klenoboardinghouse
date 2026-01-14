import os

cred = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

if not cred:
    print("❌ Env var not set")
else:
    print("✅ Env var is set")
    print("First 100 characters:", cred[:100])

    # Check if it's a file path
    import os.path
    if os.path.exists(cred):
        print("Looks like a file path →", cred)
    else:
        print("Not a file path, probably raw JSON string")
