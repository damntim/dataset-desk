"""Login and token rules: who gets in, and who is refused (401)."""
from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings
from tests.conftest import PASSWORD


def make_token(
    user_id: int, *, secret=settings.jwt_secret, minutes=60, algorithm="HS256", issued_in=0
):
    """issued_in: seconds from now that the token claims it was issued (negative = past)."""
    issued = datetime.now(timezone.utc) + timedelta(seconds=issued_in)
    payload = {"sub": str(user_id), "iat": issued, "exp": issued + timedelta(minutes=minutes)}
    return jwt.encode(payload, secret, algorithm=algorithm)


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_login_returns_token_and_user_without_password_hash(client, users):
    response = client.post(
        "/auth/login", json={"email": "client-a@test.com", "password": PASSWORD}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["user"]["role"] == "client"
    assert "password_hash" not in body["user"]


def test_login_email_is_not_case_sensitive(client, users):
    response = client.post(
        "/auth/login", json={"email": "  Client-A@TEST.com ", "password": PASSWORD}
    )
    assert response.status_code == 200


def test_wrong_password_and_unknown_email_give_the_same_answer(client, users):
    """The message must not reveal whether an email is registered."""
    wrong_password = client.post(
        "/auth/login", json={"email": "client-a@test.com", "password": "wrong"}
    )
    unknown_email = client.post(
        "/auth/login", json={"email": "ghost@test.com", "password": "wrong"}
    )
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_deactivated_user_cannot_log_in(client, make_user):
    make_user("gone@test.com", "client", is_active=False)
    response = client.post("/auth/login", json={"email": "gone@test.com", "password": PASSWORD})
    assert response.status_code == 401


def test_me_without_token_is_401(client):
    assert client.get("/auth/me").status_code == 401


def test_me_with_garbage_token_is_401(client):
    assert client.get("/auth/me", headers=bearer("abc.def.ghi")).status_code == 401


def test_expired_token_is_401(client, users):
    token = make_token(users["client_a"].id, minutes=-5)
    assert client.get("/auth/me", headers=bearer(token)).status_code == 401


def test_small_clock_difference_is_tolerated_but_a_big_one_is_not(client, users):
    """Two machines' clocks never match exactly. Docker on Windows once jumped 22 seconds
    and made valid tokens look 'issued in the future'. We allow 60 seconds of skew."""
    headers = lambda seconds: bearer(make_token(users["admin"].id, issued_in=seconds))  # noqa: E731
    assert client.get("/auth/me", headers=headers(+25)).status_code == 200
    assert client.get("/auth/me", headers=headers(+600)).status_code == 401


def test_token_signed_with_another_secret_is_401(client, users):
    token = make_token(users["admin"].id, secret="another-secret-that-is-long-enough-1234567890")
    assert client.get("/auth/me", headers=bearer(token)).status_code == 401


def test_unsigned_token_is_401(client, users):
    """A classic attack: a token that says 'no signature needed'. We must refuse it."""
    token = make_token(users["admin"].id, secret=None, algorithm="none")
    assert client.get("/auth/me", headers=bearer(token)).status_code == 401


def test_valid_token_returns_the_right_user(client, users, login_as):
    response = client.get("/auth/me", headers=login_as(users["operator"]))
    assert response.status_code == 200
    assert response.json()["email"] == "operator@test.com"


def test_token_of_a_deactivated_user_stops_working_immediately(
    client, users, login_as
):
    headers = login_as(users["admin"])
    other = login_as(users["client_a"])
    assert client.get("/auth/me", headers=other).status_code == 200

    client.patch(
        f"/users/{users['client_a'].id}", json={"is_active": False}, headers=headers
    )
    assert client.get("/auth/me", headers=other).status_code == 401
