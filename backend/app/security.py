from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings

ALGORITHM = "HS256"
# Clocks of different machines never agree perfectly (and Docker on Windows can jump by
# ~20 seconds). We accept tokens whose times are off by up to this many seconds.
CLOCK_SKEW_SECONDS = 60


def hash_password(password: str) -> str:
    """Turn a password into an unreadable hash. bcrypt adds a random 'salt' itself,
    so two users with the same password get different hashes."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=settings.bcrypt_rounds)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:  # bcrypt refuses passwords longer than 72 bytes
        return False


def create_access_token(user_id: int) -> str:
    """The 'wristband': who the user is (sub), when it was made (iat), when it expires (exp)."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """Return the user id if the wristband is genuine and not expired, else None."""
    try:
        # We always say which algorithm is allowed. Never trust the token to choose.
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[ALGORITHM], leeway=CLOCK_SKEW_SECONDS
        )
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
