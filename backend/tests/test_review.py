"""Episode-by-episode review of a delivery (the chat is tested in test_chat.py)."""
import pytest


@pytest.fixture
def delivered(client, users, login_as, make_request, make_episodes):
    """A request for 3 episodes, delivered with exactly 3. Returns (request_id, episode ids)."""
    staff = login_as(users["operator"])
    request_id = make_request(episodes_requested=3)
    ids = make_episodes(3)
    assert client.post(f"/requests/{request_id}/assignments", json={"episode_ids": ids}, headers=staff).status_code == 200
    assert client.patch(f"/requests/{request_id}/status", json={"status": "delivered"}, headers=staff).status_code == 200
    return request_id, ids


def review(client, headers, request_id, rejected=(), reason=None):
    body = {"rejected_episode_ids": list(rejected), "reason": reason}
    return client.post(f"/requests/{request_id}/review", json=body, headers=headers)


def verdicts(client, headers, request_id) -> dict[int, str]:
    episodes = client.get(f"/requests/{request_id}/episodes", headers=headers).json()
    return {e["id"]: e["review_status"] for e in episodes}


# ---------------------------------------------------------------- reviewing a delivery


def test_accepting_everything_accepts_the_request(client, users, login_as, delivered):
    request_id, ids = delivered
    owner = login_as(users["client_a"])

    response = review(client, owner, request_id)

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert set(verdicts(client, owner, request_id).values()) == {"accepted"}


def test_rejecting_some_episodes_accepts_the_others_and_sends_it_back(client, users, login_as, delivered):
    request_id, ids = delivered
    owner = login_as(users["client_a"])

    response = review(client, owner, request_id, rejected=[ids[0]], reason="Robot arm is blurry")

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "rejected"
    assert (body["episodes_assigned"], body["episodes_rejected"]) == (2, 1)
    assert verdicts(client, owner, request_id) == {ids[0]: "rejected", ids[1]: "accepted", ids[2]: "accepted"}
    rejected = next(e for e in client.get(f"/requests/{request_id}/episodes", headers=owner).json() if e["id"] == ids[0])
    assert rejected["review_note"] == "Robot arm is blurry"
    assert body["history"][-1]["to_status"] == "rejected"


def test_rejecting_needs_a_reason(client, users, login_as, delivered):
    request_id, ids = delivered
    response = review(client, login_as(users["client_a"]), request_id, rejected=[ids[0]], reason="   ")
    assert response.status_code == 422


def test_cannot_reject_an_episode_that_is_not_in_the_delivery(
    client, users, login_as, delivered, make_episodes
):
    request_id, _ = delivered
    (stranger,) = make_episodes(1)
    response = review(client, login_as(users["client_a"]), request_id, rejected=[stranger], reason="x")
    assert response.status_code == 409


def test_only_the_owning_client_can_review(client, users, login_as, delivered):
    request_id, _ = delivered
    assert review(client, login_as(users["client_b"]), request_id).status_code == 404
    assert review(client, login_as(users["operator"]), request_id).status_code == 403
    assert review(client, None, request_id).status_code == 401


@pytest.mark.parametrize("status", ["submitted", "in_progress", "accepted", "rejected"])
def test_review_only_works_on_a_delivered_request(client, users, login_as, make_request, status):
    request_id = make_request(status=status)
    assert review(client, login_as(users["client_a"]), request_id).status_code == 409


def test_the_whole_delivery_buttons_still_work_and_mark_every_episode(client, users, login_as, delivered):
    request_id, _ = delivered
    owner = login_as(users["client_a"])
    response = client.patch(f"/requests/{request_id}/status", json={"status": "rejected"}, headers=owner)
    assert response.status_code == 200
    assert set(verdicts(client, owner, request_id).values()) == {"rejected"}


# ---------------------------------------------------------------- rework after a partial rejection


def test_rework_swaps_rejected_episodes_and_keeps_accepted_ones(
    client, users, login_as, delivered, make_episodes
):
    request_id, ids = delivered
    owner, staff = login_as(users["client_a"]), login_as(users["operator"])
    review(client, owner, request_id, rejected=[ids[0]], reason="blurry")
    client.patch(f"/requests/{request_id}/status", json={"status": "in_progress"}, headers=staff)

    # Only 2 of 3 count now, so delivering again is refused.
    again = client.patch(f"/requests/{request_id}/status", json={"status": "delivered"}, headers=staff)
    assert again.status_code == 409
    assert "2 episodes assigned, 3 requested" in again.json()["detail"]

    # An accepted episode is part of the client's dataset: it cannot be removed.
    locked = client.delete(f"/requests/{request_id}/assignments/{ids[1]}", headers=staff)
    assert locked.status_code == 409

    # Swap the rejected one for a new one, then deliver.
    assert client.delete(f"/requests/{request_id}/assignments/{ids[0]}", headers=staff).status_code == 200
    (new,) = make_episodes(1)
    client.post(f"/requests/{request_id}/assignments", json={"episode_ids": [new]}, headers=staff)
    assert client.patch(f"/requests/{request_id}/status", json={"status": "delivered"}, headers=staff).status_code == 200

    # The client only reviews the new episode now; the earlier verdicts stay.
    assert verdicts(client, owner, request_id) == {ids[1]: "accepted", ids[2]: "accepted", new: "pending"}
    assert review(client, owner, request_id, rejected=[ids[1]], reason="changed my mind").status_code == 409
    assert review(client, owner, request_id).json()["status"] == "accepted"
    assert set(verdicts(client, owner, request_id).values()) == {"accepted"}


def test_a_rejected_episode_left_in_place_does_not_count_toward_delivery(
    client, users, login_as, delivered, make_episodes
):
    request_id, ids = delivered
    staff = login_as(users["operator"])
    review(client, login_as(users["client_a"]), request_id, rejected=ids, reason="all wrong")
    client.patch(f"/requests/{request_id}/status", json={"status": "in_progress"}, headers=staff)
    client.post(f"/requests/{request_id}/assignments", json={"episode_ids": make_episodes(2)}, headers=staff)
    response = client.patch(f"/requests/{request_id}/status", json={"status": "delivered"}, headers=staff)
    assert response.status_code == 409  # 2 new, the 3 rejected do not count


# ---------------------------------------------------------------- more episodes than requested


@pytest.fixture
def over_delivered(client, users, login_as, make_request, make_episodes):
    """Asked for 2, delivered 5. Returns (request_id, episode ids)."""
    staff = login_as(users["operator"])
    request_id = make_request(episodes_requested=2)
    ids = make_episodes(5)
    client.post(f"/requests/{request_id}/assignments", json={"episode_ids": ids}, headers=staff)
    assert client.patch(f"/requests/{request_id}/status", json={"status": "delivered"}, headers=staff).status_code == 200
    return request_id, ids


def test_accepting_an_over_delivery_forces_a_choice(client, users, login_as, over_delivered):
    request_id, _ = over_delivered
    owner = login_as(users["client_a"])
    plain = client.patch(f"/requests/{request_id}/status", json={"status": "accepted"}, headers=owner)
    assert plain.status_code == 409
    assert "5 episodes but you requested 2" in plain.json()["detail"]
    silent = review(client, owner, request_id)
    assert silent.status_code == 409
    assert "Return 3, or extend your request to 5" in silent.json()["detail"]


def test_keeping_only_what_was_asked_returns_the_rest_to_the_pool(
    client, users, login_as, over_delivered, make_request
):
    request_id, ids = over_delivered
    owner = login_as(users["client_a"])
    body = {"returned_episode_ids": ids[2:]}
    response = client.post(f"/requests/{request_id}/review", json=body, headers=owner)

    assert response.status_code == 200
    assert (response.json()["status"], response.json()["episodes_assigned"]) == ("accepted", 2)
    assert verdicts(client, owner, request_id) == {ids[0]: "accepted", ids[1]: "accepted"}
    # the returned ones are free again: another request can take them
    staff = login_as(users["operator"])
    other = make_request(owner="client_b")
    again = client.post(f"/requests/{other}/assignments", json={"episode_ids": ids[2:]}, headers=staff)
    assert again.status_code == 200


def test_extending_the_request_keeps_everything_and_leaves_a_trace(client, users, login_as, over_delivered):
    request_id, ids = over_delivered
    owner = login_as(users["client_a"])
    response = client.post(f"/requests/{request_id}/review", json={"extend": True}, headers=owner)

    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["episodes_requested"], body["episodes_assigned"]) == ("accepted", 5, 5)
    chat = client.get(f"/requests/{request_id}/messages", headers=owner).json()
    assert chat[-1]["body"] == "Extended this request from 2 to 5 episodes to keep the extra ones."


def test_returning_too_many_is_refused(client, users, login_as, over_delivered):
    request_id, ids = over_delivered
    body = {"returned_episode_ids": ids[1:]}  # would keep only 1 of 2
    response = client.post(f"/requests/{request_id}/review", json=body, headers=login_as(users["client_a"]))
    assert response.status_code == 409


def test_reject_some_and_return_others_in_one_review(client, users, login_as, over_delivered):
    request_id, ids = over_delivered
    owner = login_as(users["client_a"])
    body = {"rejected_episode_ids": [ids[0]], "returned_episode_ids": ids[3:], "reason": "blurry"}
    response = client.post(f"/requests/{request_id}/review", json=body, headers=owner)
    assert response.json()["status"] == "rejected"
    assert verdicts(client, owner, request_id) == {ids[0]: "rejected", ids[1]: "accepted", ids[2]: "accepted"}


@pytest.mark.parametrize(
    "body",
    [
        {"rejected_episode_ids": [1], "returned_episode_ids": [1], "reason": "x"},  # both
        {"rejected_episode_ids": [1], "reason": "x", "extend": True},  # extend while rejecting
    ],
)
def test_contradictory_reviews_are_422(client, users, login_as, over_delivered, body):
    request_id, _ = over_delivered
    response = client.post(f"/requests/{request_id}/review", json=body, headers=login_as(users["client_a"]))
    assert response.status_code == 422
