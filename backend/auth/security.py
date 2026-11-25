import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Dict, Optional
from backend.config import settings

def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with 100,000 iterations and 16-byte random salt."""
    salt = secrets.token_bytes(16)
    iterations = 100_000
    derived_key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    salt_hex = salt.hex()
    hash_hex = derived_key.hex()
    return f"pbkdf2_sha256${iterations}${salt_hex}${hash_hex}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against stored PBKDF2 hash using constant-time comparison."""
    try:
        parts = hashed_password.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        expected_hash = parts[3]
        
        derived_key = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(derived_key.hex(), expected_hash)
    except Exception:
        return False

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")

def _b64url_decode(encoded: str) -> bytes:
    padding = 4 - (len(encoded) % 4)
    if padding and padding != 4:
        encoded += "=" * padding
    return base64.urlsafe_b64decode(encoded.encode("utf-8"))

def create_access_token(data: Dict[str, Any], expires_delta_seconds: Optional[int] = None) -> str:
    """
    Generate an HMAC-SHA256 (HS256) JWT access token compliant with RFC 7519.
    Does not require external jwt libraries, works offline everywhere.
    """
    now = int(time.time())
    if expires_delta_seconds is not None:
        expire = now + expires_delta_seconds
    else:
        expire = now + (settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)
        
    payload = data.copy()
    payload["iat"] = now
    payload["exp"] = expire
    
    header = {"alg": "HS256", "typ": "JWT"}
    header_json = json.dumps(header, separators=(",", ":")).encode("utf-8")
    payload_json = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    
    header_b64 = _b64url_encode(header_json)
    payload_b64 = _b64url_encode(payload_json)
    
    message = f"{header_b64}.{payload_b64}".encode("utf-8")
    signature = hmac.new(settings.SECRET_KEY.encode("utf-8"), message, hashlib.sha256).digest()
    sig_b64 = _b64url_encode(signature)
    
    return f"{header_b64}.{payload_b64}.{sig_b64}"

def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify signature and expiration of an HS256 JWT token."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        message = f"{header_b64}.{payload_b64}".encode("utf-8")
        
        expected_sig = hmac.new(settings.SECRET_KEY.encode("utf-8"), message, hashlib.sha256).digest()
        actual_sig = _b64url_decode(sig_b64)
        
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
            
        payload_bytes = _b64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
        
        # Verify expiration
        exp = payload.get("exp")
        if exp is not None and int(exp) < int(time.time()):
            return None
            
        return payload
    except Exception:
        return None

def generate_guest_token() -> str:
    """Generate a 256-bit unguessable cryptographically secure URL-safe token."""
    return secrets.token_urlsafe(32)
