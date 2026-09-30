"""Authorization: only admins manage users (403 for everyone else)."""
import pytest

from tests.conftest import PASSWORD

NEW_USER = {
    "email": "New.Person@Test.com",
    "password": "longenough1",
    "name": "New Person",
    "role": "client",
    "organisation": "NewCo",
}

# (method, path) of every admin-only endpoint. {id} is replaced by a real user id.
ADMIN_ONLY = [
    ("get", "/users"),
    ("post", "/users"),
    ("patch", "/users/{id}"),
]


def call(client, method, path, headers=None, user_id=1):
    body = {"name": "x"} if method == "patch" else NEW_USER if method == "post" else None
    return client.request(method, path.format(id=user_id), json=body, headers=headers)


@pytest.mark.parametrize("method,path", ADMIN_ONLY)
@pytest.mark.parametrize("who", ["client_a", "operator"])
def test_non_admins_get_403(client, users, login_as, who, method, path):
    response = call(client, method, path, login_as(users[who]), users["client_b"].id)
    assert response.status_code == 403


@pytest.mark.parametrize("method,path", ADMIN_ONLY)
def test_anonymous_gets_401(client, users, method, path):
    assert call(client, method, path, None, users["client_b"].id).status_code == 401


def test_admin_can_list_users_and_no_password_hash_leaks(client, users, login_as):
    response = client.get("/users", headers=login_as(users["admin"]))
    assert response.status_code == 200
    assert len(response.json()) == 4
    assert all("password_hash" not in u for u in response.json())


def test_admin_creates_user_who_can_then_log_in(client, users, login_as):
    created = client.post("/users", json=NEW_USER, headers=login_as(users["admin"]))
    assert created.status_code == 201
    assert created.json()["email"] == "new.person@test.com"  # stored in lower case

    login = client.post(
        "/auth/login", json={"email": "new.person@test.com", "password": NEW_USER["password"]}
    )
    assert login.status_code == 200


def test_duplicate_email_is_409_even_with_different_capitals(client, users, login_as):
    headers = login_as(users["admin"])
    assert client.post("/users", json=NEW_USER, headers=headers).status_code == 201
    again = {**NEW_USER, "email": "new.person@TEST.COM"}
    assert client.post("/users", json=again, headers=headers).status_code == 409


@pytest.mark.parametrize(
    "change",
    [
        {"password": "short"},
        {"role": "superuser"},
        {"email": "not-an-email"},
    ],
)
def test_invalid_user_data_is_422(client, users, login_as, change):
    response = client.post(
        "/users", json={**NEW_USER, **change}, headers=login_as(users["admin"])
    )
    assert response.status_code == 422


def test_admin_can_change_role_and_deactivate_another_user(client, users, login_as):
    headers = login_as(users["admin"])
    target = users["client_a"].id
    response = client.patch(
        f"/users/{target}", json={"role": "operator", "is_active": False}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["role"] == "operator"
    assert response.json()["is_active"] is False


def test_admin_cannot_demote_or_deactivate_themselves(client, users, login_as):
    headers = login_as(users["admin"])
    me = users["admin"].id
    assert client.patch(f"/users/{me}", json={"role": "client"}, headers=headers).status_code == 400
    assert (
        client.patch(f"/users/{me}", json={"is_active": False}, headers=headers).status_code == 400
    )


def test_patching_a_missing_user_is_404(client, users, login_as):
    response = client.patch("/users/9999", json={"name": "x"}, headers=login_as(users["admin"]))
    assert response.status_code == 404
