#utilis/token_utilis
import jwt
from datetime import datetime, timedelta
from CUZ.core.config import SECRET_KEY

def generate_location_token(data: dict, expires_in_minutes: int = 10):
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=expires_in_minutes)
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def decode_location_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
