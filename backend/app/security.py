import bcrypt


def hash_password(password: str) -> str:
    """Turn a password into an unreadable hash. bcrypt adds a random 'salt' itself,
    so two users with the same password get different hashes."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())
