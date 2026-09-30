"""Create the demo users from seed/users.json. Safe to run many times.

python -m app.seed
"""

import json
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.importer import decode_file, import_episodes
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


def seed_episodes() -> None:
    """Load seed/episodes.csv with the same importer operators use (so it is idempotent too)."""
    path = Path(settings.seed_dir) / "episodes.csv"
    if not path.exists():
        return
    with SessionLocal() as db:
        report = import_episodes(db, decode_file(path.read_bytes()))
    print(
        f"seed episodes: {report['imported']} imported, "
        f"{report['already_existed']} already existed, {report['skipped']} skipped"
    )


if __name__ == "__main__":
    seed_users()
    seed_episodes()
