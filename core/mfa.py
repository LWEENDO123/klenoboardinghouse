# CUZ/ADMIN/core/mfa.py
import pyotp
import base64
import os
from datetime import datetime

def generate_mfa_secret() -> str:
    """
    Generate a new base32 secret for an admin.
    This secret should be stored securely in Firestore (encrypted).
    """
    return pyotp.random_base32()

def get_totp(secret: str) -> pyotp.TOTP:
    """
    Return a TOTP object for the given secret.
    """
    return pyotp.TOTP(secret)

def verify_otp(secret: str, otp: str) -> bool:
    """
    Verify a one-time password (OTP) against the secret.
    Returns True if valid, False otherwise.
    """
    totp = get_totp(secret)
    return totp.verify(otp, valid_window=1)  # allow small clock drift

def generate_qr_uri(secret: str, admin_email: str, issuer: str = "KLENO Tutor Hub") -> str:
    """
    Generate a provisioning URI for QR code scanning in Google Authenticator.
    """
    totp = get_totp(secret)
    return totp.provisioning_uri(name=admin_email, issuer_name=issuer)
