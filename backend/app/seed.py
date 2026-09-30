"""Create the demo users from seed/users.json. Safe to run many times.

    python -m app.seed
"""
import json
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import User
from app.security import hash_password


def seed_users() -> None:
    users = json.loads((Path(settings.seed_dir) / "users.json").read_text(encoding="utf-8"))
    created = skipped = 0
    with SessionLocal() as db:
        for u in users:
            if db.scalar(select(User).where(User.email == u["email"])):
                skipped += 1  # already there: leave it alone
                continue
            db.add(
                User(
                    email=u["email"],
                    password_hash=hash_password(u["password"]),
                    name=u["name"],
                    organisation=u.get("organisation"),
                    role=u["role"],
                )
            )
            created += 1
        db.commit()
    print(f"seed users: {created} created, {skipped} already existed")


if __name__ == "__main__":
    seed_users()
