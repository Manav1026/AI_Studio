"""Session tokens (JWT) and symmetric encryption for the credential store."""
import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.core.errors import Unauthorized

ALGO = "HS256"
ISSUER = "sfai"


def create_session_token(user_id: str, tenant_id: str, role: str, ttl_minutes: int | None = None,
                         scope: str = "app") -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        "iss": ISSUER, "sub": user_id, "tid": tenant_id, "role": role, "scope": scope,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl_minutes or s.session_ttl_minutes)).timestamp()),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, s.app_secret_key, algorithm=ALGO)


def decode_session_token(token: str) -> dict:
    try:
        return jwt.decode(token, get_settings().app_secret_key, algorithms=[ALGO], issuer=ISSUER)
    except jwt.PyJWTError as exc:
        raise Unauthorized("Invalid or expired session") from exc


def _fernet() -> Fernet:
    s = get_settings()
    key = s.encryption_key
    if not key:
        if s.app_env in ("staging", "production"):
            raise RuntimeError("ENCRYPTION_KEY must be configured outside local/test")
        # Derive a stable local key from the app secret so local dev works out of the box.
        key = base64.urlsafe_b64encode(hashlib.sha256(s.app_secret_key.encode()).digest()).decode()
    return Fernet(key.encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError("Unable to decrypt credential (key rotated or corrupted)") from exc


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge
