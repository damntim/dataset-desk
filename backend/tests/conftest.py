"""Shared test setup ("fixtures"). pytest runs this file before any test.

Tests use a SEPARATE database called desk_test, so they can never touch real data.
"""
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

# 1) Point the app at the TEST database. This must happen BEFORE the app is imported,
#    because the app reads DATABASE_URL once, when it starts.
_dev_url = make_url(
    os.environ.get("DATABASE_URL", "postgresql+psycopg://desk:desk@localhost:5432/desk")
)
TEST_DB_NAME = "desk_test"
os.environ["DATABASE_URL"] = _dev_url.set(database=TEST_DB_NAME).render_as_string(
    hide_password=False
)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, User  # noqa: E402
from app.security import hash_password  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]
PASSWORD = "password123"
# bcrypt is slow on purpose, so we hash once and reuse it for every test user.
PASSWORD_HASH = hash_password(PASSWORD)


@pytest.fixture(scope="session", autouse=True)
def _database():
    """Once per test run: create desk_test if needed, then build the tables
    from scratch using our real migrations (so the migrations get tested too)."""
    admin_engine = create_engine(_dev_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DB_NAME}
        )
        if not exists:
            conn.execute(text(f"CREATE DATABASE {TEST_DB_NAME}"))
    admin_engine.dispose()

    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")

    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _empty_tables():
    """Before EVERY test: empty all tables, so tests never affect each other."""
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def client():
    """A fake browser that calls our API directly."""
    return TestClient(app)


@pytest.fixture
def make_user():
    """Create a user straight in the database. Returns the User."""

    def _make(email: str, role: str, is_active: bool = True, organisation: str | None = None):
        with SessionLocal() as db:
            user = User(
                email=email,
                password_hash=PASSWORD_HASH,
                name=email.split("@")[0],
                organisation=organisation,
                role=role,
                is_active=is_active,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            return user

    return _make


@pytest.fixture
def users(make_user):
    """One person of each kind, plus a second client (to test 'not your data')."""
    return {
        "admin": make_user("admin@test.com", "admin"),
        "operator": make_user("operator@test.com", "operator"),
        "client_a": make_user("client-a@test.com", "client", organisation="Acme"),
        "client_b": make_user("client-b@test.com", "client", organisation="Beta"),
    }


@pytest.fixture
def login_as(client):
    """login_as(user) -> the headers that prove who you are (the 'wristband')."""

    def _login(user: User):
        response = client.post("/auth/login", json={"email": user.email, "password": PASSWORD})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _login
