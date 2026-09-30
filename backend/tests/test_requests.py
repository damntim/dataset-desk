"""Requests: who can create and see them, and how they move through the workflow."""

from datetime import date, timedelta

import pytest

from app.workflow import TRANSITIONS

ALL = ["submitted", "in_progress", "delivered", "accepted", "rejected"]


def payload(**changes) -> dict:
    body = {
        "task_name": "  Pick   Cup ",
        "episodes_requested": 2,
        "deadline": (date.today() + timedelta(days=30)).isoformat(),
        "notes": "Please use good lighting",
    }
    return {**body, **changes}


@pytest.fixture
def request_id(client, users, login_as):
    """A fresh request (2 episodes wanted), created by client A."""
    response = client.post("/requests", json=payload(), headers=login_as(users["client_a"]))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def move(client, headers, request_id, status):
    return client.patch(f"/requests/{request_id}/status", json={"status": status}, headers=headers)


# ---------------------------------------------------------------- creating


def test_client_creates_request_and_history_starts(client, users, login_as):
    response = client.post("/requests", json=payload(), headers=login_as(users["client_a"]))
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "submitted"
    assert body["task_name"] == "pick cup"  # cleaned: spaces and capitals
    assert body["client_id"] == users["client_a"].id
    assert body["episodes_assigned"] == 0
    assert len(body["history"]) == 1
    assert body["history"][0]["from_status"] is None
    assert body["history"][0]["to_status"] == "submitted"
    assert body["history"][0]["changed_by_name"] == "client-a"


@pytest.mark.parametrize("who", ["operator", "admin"])
def test_only_clients_can_create_requests(client, users, login_as, who):
    response = client.post("/requests", json=payload(), headers=login_as(users[who]))
    assert response.status_code == 403


def test_anonymous_cannot_create_or_list(client):
    assert client.post("/requests", json=payload()).status_code == 401
    assert client.get("/requests").status_code == 401


@pytest.mark.parametrize(
    "change",
    [
        {"episodes_requested": 0},
        {"episodes_requested": -5},
        {"task_name": "   "},
        {"deadline": (date.today() - timedelta(days=1)).isoformat()},
        {"deadline": "not-a-date"},
    ],
)
def test_invalid_request_data_is_422(client, users, login_as, change):
    response = client.post("/requests", json=payload(**change), headers=login_as(users["client_a"]))
    assert response.status_code == 422


# ---------------------------------------------------------------- who sees what


def test_client_only_sees_their_own_requests_but_operator_sees_all(client, users, login_as):
    client.post("/requests", json=payload(), headers=login_as(users["client_a"]))
    client.post("/requests", json=payload(), headers=login_as(users["client_b"]))

    a_list = client.get("/requests", headers=login_as(users["client_a"])).json()
    assert [r["client_id"] for r in a_list] == [users["client_a"].id]

    all_list = client.get("/requests", headers=login_as(users["operator"])).json()
    assert len(all_list) == 2


def test_another_clients_request_is_404_not_403(client, users, login_as, request_id):
    """We do not even admit that request exists."""
    other = login_as(users["client_b"])
    assert client.get(f"/requests/{request_id}", headers=other).status_code == 404
    assert move(client, other, request_id, "in_progress").status_code == 404


@pytest.mark.parametrize("who", ["operator", "admin"])
def test_staff_can_open_any_request(client, users, login_as, request_id, who):
    assert client.get(f"/requests/{request_id}", headers=login_as(users[who])).status_code == 200


def test_missing_request_is_404(client, users, login_as):
    assert client.get("/requests/9999", headers=login_as(users["operator"])).status_code == 404


def test_list_can_filter_by_status(client, users, login_as, request_id, set_status):
    client.post("/requests", json=payload(), headers=login_as(users["client_a"]))
    set_status(request_id, "in_progress")
    staff = login_as(users["operator"])
    assert len(client.get("/requests?status=in_progress", headers=staff).json()) == 1
    assert len(client.get("/requests?status=submitted", headers=staff).json()) == 1
    assert client.get("/requests?status=flying", headers=staff).status_code == 422


def test_buttons_shown_depend_on_who_is_looking(client, users, login_as, request_id, set_status):
    set_status(request_id, "delivered")
    as_client = client.get(f"/requests/{request_id}", headers=login_as(users["client_a"])).json()
    as_operator = client.get(f"/requests/{request_id}", headers=login_as(users["operator"])).json()
    assert as_client["allowed_next"] == ["accepted", "rejected"]
    assert as_operator["allowed_next"] == []


# ---------------------------------------------------------------- the workflow


def test_full_journey_records_who_and_when(client, users, login_as, request_id, assign_episodes):
    staff = login_as(users["operator"])
    owner = login_as(users["client_a"])

    assert move(client, staff, request_id, "in_progress").status_code == 200
    assign_episodes(request_id, 2, users["operator"].id)
    assert move(client, staff, request_id, "delivered").status_code == 200
    final = move(client, owner, request_id, "accepted")

    assert final.status_code == 200
    assert final.json()["status"] == "accepted"
    steps = [(h["from_status"], h["to_status"], h["changed_by_name"]) for h in final.json()["history"]]
    assert steps == [
        (None, "submitted", "client-a"),
        ("submitted", "in_progress", "operator"),
        ("in_progress", "delivered", "operator"),
        ("delivered", "accepted", "client-a"),
    ]
    assert all(h["changed_at"] for h in final.json()["history"])


def test_rejected_delivery_goes_back_for_rework_then_can_be_accepted(
    client, users, login_as, request_id, assign_episodes
):
    staff = login_as(users["admin"])  # admins can do everything operators can
    owner = login_as(users["client_a"])
    move(client, staff, request_id, "in_progress")
    assign_episodes(request_id, 2, users["admin"].id)
    move(client, staff, request_id, "delivered")

    assert move(client, owner, request_id, "rejected").status_code == 200
    assert move(client, staff, request_id, "in_progress").status_code == 200  # rework
    # Rejecting the whole delivery rejects its episodes: they no longer count.
    assert move(client, staff, request_id, "delivered").status_code == 409
    assign_episodes(request_id, 2, users["admin"].id)  # fresh replacements
    assert move(client, staff, request_id, "delivered").status_code == 200
    assert move(client, owner, request_id, "accepted").status_code == 200


INVALID_MOVES = [(a, b) for a in ALL for b in ALL if (a, b) not in TRANSITIONS]


@pytest.mark.parametrize("current,target", INVALID_MOVES)
def test_every_invalid_move_is_409_and_changes_nothing(
    client, users, login_as, request_id, set_status, current, target
):
    set_status(request_id, current)
    response = move(client, login_as(users["admin"]), request_id, target)
    assert response.status_code == 409
    after = client.get(f"/requests/{request_id}", headers=login_as(users["admin"])).json()
    assert after["status"] == current
    assert len(after["history"]) == 1  # only the creation row: no new diary entry


VALID_MOVES_WRONG_ROLE = [
    (move_, who)
    for move_, roles in TRANSITIONS.items()
    for who in ["client_a", "operator", "admin"]
    if {"client_a": "client", "operator": "operator", "admin": "admin"}[who] not in roles
]


@pytest.mark.parametrize("move_,who", VALID_MOVES_WRONG_ROLE)
def test_valid_move_by_the_wrong_role_is_403(
    client, users, login_as, request_id, set_status, assign_episodes, move_, who
):
    current, target = move_
    set_status(request_id, current)
    assign_episodes(request_id, 2, users["admin"].id)  # so only the ROLE can be the problem
    response = move(client, login_as(users[who]), request_id, target)
    assert response.status_code == 403


def test_cannot_deliver_without_enough_episodes(
    client, users, login_as, request_id, assign_episodes, set_status
):
    staff = login_as(users["operator"])
    set_status(request_id, "in_progress")

    nothing = move(client, staff, request_id, "delivered")
    assert nothing.status_code == 409
    assert "0 episodes assigned, 2 requested" in nothing.json()["detail"]

    assign_episodes(request_id, 1, users["operator"].id)
    assert move(client, staff, request_id, "delivered").status_code == 409  # 1 of 2

    assign_episodes(request_id, 1, users["operator"].id)
    assert move(client, staff, request_id, "delivered").status_code == 200  # 2 of 2

    after = client.get(f"/requests/{request_id}", headers=staff).json()
    assert after["status"] == "delivered"


def test_delivering_more_than_requested_is_fine(
    client, users, login_as, request_id, assign_episodes, set_status
):
    set_status(request_id, "in_progress")
    assign_episodes(request_id, 3, users["operator"].id)
    assert move(client, login_as(users["operator"]), request_id, "delivered").status_code == 200


def test_unknown_status_value_is_422(client, users, login_as, request_id):
    response = move(client, login_as(users["operator"]), request_id, "teleported")
    assert response.status_code == 422
