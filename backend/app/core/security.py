import hashlib
import hmac
import secrets

from app.core.config import Settings
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def password_matches(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError):
        return False


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str, settings: Settings) -> str:
    secret = settings.session_hash_secret.get_secret_value() if settings.session_hash_secret else ""
    return hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()


def tokens_match(expected_hash: str, token: str, settings: Settings) -> bool:
    return hmac.compare_digest(expected_hash, token_hash(token, settings))
