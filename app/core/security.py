"""
Security & Cryptography Utilities.

Handles:
  - Password hashing & verification with bcrypt
  - JWT token creation and decoding
  - Fernet encryption for BYOK LLM API keys
"""

from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

import bcrypt
from cryptography.fernet import Fernet
from jose import JWTError, jwt

from app.core.config import settings

# ---------------------------------------------------------------------------
# Fernet Symmetric Encryption (for third-party BYOK API keys)
# ---------------------------------------------------------------------------
_fernet = Fernet(settings.ENCRYPTION_KEY.encode())


def encrypt_api_key(plain_key: str) -> str:
    """Encrypt a plaintext API key → base64 ciphertext string."""
    return _fernet.encrypt(plain_key.encode()).decode()


def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt a stored ciphertext → plaintext API key."""
    return _fernet.decrypt(encrypted_key.encode()).decode()


def encrypt_headers(headers: dict[str, str] | None) -> str | None:
    """Encrypt a dictionary of headers to a base64 ciphertext string."""
    if not headers:
        return None
    import json
    return _fernet.encrypt(json.dumps(headers).encode()).decode()


def decrypt_headers(encrypted_headers: str | None) -> dict[str, str]:
    """Decrypt a stored ciphertext string back into headers dict."""
    if not encrypted_headers:
        return {}
    import json
    try:
        decrypted_bytes = _fernet.decrypt(encrypted_headers.encode())
        return json.loads(decrypted_bytes.decode())
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Password Hashing & Verification (Bcrypt)
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    """
    Hash a plaintext password using bcrypt with a salt.
    Bcrypt has a maximum password length limit of 72 bytes.
    """
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash."""
    pwd_bytes = plain_password.encode("utf-8")[:72]
    hash_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(pwd_bytes, hash_bytes)


# ---------------------------------------------------------------------------
# JWT (JSON Web Tokens)
# ---------------------------------------------------------------------------
def create_access_token(
    subject: str | uuid.UUID | Any,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Generate a signed JWT access token for a user.
    `subject` is typically the user's UUID string.
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }

    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def decode_access_token(token: str) -> dict[str, Any] | None:
    """
    Decode and validate a JWT access token.
    Returns the payload dictionary or None if invalid/expired.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        return payload
    except JWTError:
        return None
