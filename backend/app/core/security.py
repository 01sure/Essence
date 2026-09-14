"""密码散列（PBKDF2，无三方依赖）与 JWT 签发/校验"""
import hashlib
import hmac
import os
import time

import jwt

from app.core.config import get_settings

_ITERATIONS = 120_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"pbkdf2${_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def create_admin_token(admin_id: int, username: str) -> str:
    settings = get_settings()
    payload = {
        "sub": str(admin_id),
        "username": username,
        "exp": int(time.time()) + settings.ADMIN_TOKEN_EXPIRE_HOURS * 3600,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_admin_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, get_settings().SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
