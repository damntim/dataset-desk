"""Assignment rules: which episodes may go to which request, and when."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.main import app
from app.models import Assignment


def assign(client, headers, request_id, episode_ids):
    return client.post(
        f"/requests/{request_id}/assignments", json={"episode_ids": episode_ids}, headers=headers
    )


def assignment_count() -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count(Assignment.id)))


# ---------------------------------------------------------------- who may assign


def test_operator_assigns_good_and_usable_episodes(
    client, users, login_as, make_request, make_episodes
):
    request_id = make_request()
    ids = make_episodes(1, "good") + make_episodes(1, "usable")

    response = assign(client, login_as(users["operator"]), request_id, ids)

    assert response.status_code == 200
    assert response.json()["episodes_assigned"] == 2


def test_admin_can_assign_too(client, users, login_as, make_request, make_episodes):
    request_id = make_request()
    response = assign(client, login_as(users["admin"]), request_id, make_episodes(1))
    assert response.status_code == 200


def test_clients_cannot_assign_not_even_on_their_own_request(
    client, users, login_as, make_request, make_episodes
):
    request_id = make_request(owner="client_a")
    response = assign(client, login_as(users["client_a"]), request_id, make_episodes(1))
    assert response.status_code == 403
    assert assignment_count() == 0


def test_anonymous_cannot_assign(client, users, make_request, make_episodes):
    assert assign(client, None, make_request(), make_episodes(1)).status_code == 401


# ---------------------------------------------------------------- which episodes


def test_a_bad_episode_is_refused(client, users, login_as, make_request, make_episodes):
    request_id = make_request()
    response = assign(client, login_as(users["operator"]), request_id, make_episodes(1, "bad"))
    assert response.status_code == 409
    assert "good or usable" in response.json()["detail"]
    assert assignment_count() == 0


def test_all_or_nothing_one_bad_episode_stops_the_whole_batch(
    client, users, login_as, make_request, make_episodes
):
    request_id = make_request()
    ids = make_episodes(2, "good") + make_episodes(1, "bad")
    response = assign(client, login_as(users["operator"]), request_id, ids)
    assert response.status_code == 409
    assert assignment_count() == 0  # the two good ones were NOT assigned either


def test_an_episode_cannot_go_to_two_requests(
    client, users, login_as, make_request, make_episodes
):
    staff = login_as(users["operator"])
    first, second = make_request(), make_request(owner="client_b")
    episode = make_episodes(1)

    assert assign(client, staff, first, episode).status_code == 200
    again = assign(client, staff, second, episode)

    assert again.status_code == 409
    assert f"request {first}" in again.json()["detail"]
    assert assignment_count() == 1


def test_assigning_the_same_episode_twice_to_one_request_is_409(
    client, users, login_as, make_request, make_episodes
):
    staff = login_as(users["operator"])
    request_id = make_request()
    episode = make_episodes(1)
    assign(client, staff, request_id, episode)
    assert assign(client, staff, request_id, episode).status_code == 409


def test_the_same_id_listed_twice_in_one_call_counts_once(
    client, users, login_as, make_request, make_episodes
):
    (episode,) = make_episodes(1)
    response = assign(client, login_as(users["operator"]), make_request(), [episode, episode])
    assert response.status_code == 200
    assert response.json()["episodes_assigned"] == 1


def test_unknown_episode_is_404(client, users, login_as, make_request):
    response = assign(client, login_as(users["operator"]), make_request(), [9999])
    assert response.status_code == 404


def test_unknown_request_is_404(client, users, login_as, make_episodes):
    assert assign(client, login_as(users["operator"]), 9999, make_episodes(1)).status_code == 404


@pytest.mark.parametrize("body", [{"episode_ids": []}, {"episode_ids": ["a"]}, {}])
def test_invalid_body_is_422(client, users, login_as, make_request, body):
    response = client.post(
        f"/requests/{make_request()}/assignments", json=body, headers=login_as(users["operator"])
    )
    assert response.status_code == 422


# ---------------------------------------------------------------- when


@pytest.mark.parametrize("status", ["submitted", "delivered", "accepted", "rejected"])
def test_episodes_can_only_be_assigned_while_in_progress(
    client, users, login_as, make_request, make_episodes, status
):
    request_id = make_request(status=status)
    response = assign(client, login_as(users["operator"]), request_id, make_episodes(1))
    assert response.status_code == 409
    assert assignment_count() == 0


# ---------------------------------------------------------------- taking episodes back


def test_unassign_frees_the_episode_for_another_request(
    client, users, login_as, make_request, make_episodes
):
    staff = login_as(users["operator"])
    first, second = make_request(), make_request(owner="client_b")
    (episode,) = make_episodes(1)
    assign(client, staff, first, [episode])

    removed = client.delete(f"/requests/{first}/assignments/{episode}", headers=staff)
    assert removed.status_code == 200
    assert removed.json()["episodes_assigned"] == 0

    assert assign(client, staff, second, [episode]).status_code == 200


def test_cannot_unassign_after_delivery(
    client, users, login_as, make_request, make_episodes, set_status
):
    staff = login_as(users["operator"])
    request_id = make_request(episodes_requested=1)
    (episode,) = make_episodes(1)
    assign(client, staff, request_id, [episode])
    set_status(request_id, "delivered")

    response = client.delete(f"/requests/{request_id}/assignments/{episode}", headers=staff)
    assert response.status_code == 409
    assert assignment_count() == 1


def test_unassigning_something_not_assigned_is_404(
    client, users, login_as, make_request, make_episodes
):
    (episode,) = make_episodes(1)
    response = client.delete(
        f"/requests/{make_request()}/assignments/{episode}", headers=login_as(users["operator"])
    )
    assert response.status_code == 404


def test_clients_cannot_unassign(client, users, login_as, make_request, make_episodes):
    request_id = make_request()
    (episode,) = make_episodes(1)
    assign(client, login_as(users["operator"]), request_id, [episode])
    response = client.delete(
        f"/requests/{request_id}/assignments/{episode}", headers=login_as(users["client_a"])
    )
    assert response.status_code == 403


# ---------------------------------------------------------------- the database is the last guard


def test_database_itself_refuses_a_second_assignment_of_one_episode(
    users, make_request, make_episodes
):
    """Even code that skips our checks cannot break 'one episode, one request'."""
    first, second = make_request(), make_request(owner="client_b")
    (episode,) = make_episodes(1)
    with SessionLocal() as db:
        db.add(Assignment(request_id=first, episode_id=episode, assigned_by=users["operator"].id))
        db.commit()
        db.add(Assignment(request_id=second, episode_id=episode, assigned_by=users["operator"].id))
        with pytest.raises(IntegrityError):
            db.commit()


def test_two_operators_racing_for_one_episode_exactly_one_wins(
    client, users, login_as, make_request, make_episodes
):
    """Two requests, two operators, one episode, at the same moment. Whatever the timing,
    exactly one gets it and the other gets a clean 409 (never a 500)."""
    first, second = make_request(episodes_requested=50), make_request(owner="client_b", episodes_requested=50)
    headers = [login_as(users["operator"]), login_as(users["admin"])]

    for round_number in range(1, 9):  # a race is not always lost the same way: repeat it
        (episode,) = make_episodes(1)  # a FRESH episode each round, so every round is a real race

        def attempt(args):
            request_id, header = args
            return assign(TestClient(app), header, request_id, [episode]).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = sorted(pool.map(attempt, [(first, headers[0]), (second, headers[1])]))
        assert codes == [200, 409], f"round {round_number}: {codes}"
        assert assignment_count() == round_number


# ---------------------------------------------------------------- end to end with delivery


def test_assigning_enough_episodes_through_the_api_unlocks_delivery(
    client, users, login_as, make_request, make_episodes
):
    staff = login_as(users["operator"])
    request_id = make_request(episodes_requested=2)
    deliver = lambda: client.patch(  # noqa: E731
        f"/requests/{request_id}/status", json={"status": "delivered"}, headers=staff
    )

    assign(client, staff, request_id, make_episodes(1))
    assert deliver().status_code == 409  # 1 of 2
    assign(client, staff, request_id, make_episodes(1))
    assert deliver().status_code == 200  # 2 of 2


# ---------------------------------------------------------------- browsing episodes


def test_episode_list_filters_by_task_and_quality(client, users, login_as, make_episodes):
    make_episodes(3, "good", "pick cup")
    make_episodes(2, "bad", "pick cup")
    make_episodes(4, "good", "fold towel")
    staff = login_as(users["operator"])

    everything = client.get("/episodes", headers=staff).json()
    assert everything["total"] == 9

    cups = client.get("/episodes?task_name=Pick  Cup", headers=staff).json()  # capitals/spaces ok
    assert cups["total"] == 5

    good_cups = client.get("/episodes?task_name=pick cup&quality=good", headers=staff).json()
    assert good_cups["total"] == 3
    assert {i["quality"] for i in good_cups["items"]} == {"good"}


def test_episode_list_can_show_only_free_episodes(
    client, users, login_as, make_request, make_episodes
):
    staff = login_as(users["operator"])
    request_id = make_request()
    given, free = make_episodes(1), make_episodes(2)
    assign(client, staff, request_id, given)

    free_only = client.get("/episodes?unassigned=true", headers=staff).json()
    assert sorted(i["id"] for i in free_only["items"]) == sorted(free)
    assert all(i["assigned_request_id"] is None for i in free_only["items"])

    mine = client.get(f"/episodes?request_id={request_id}", headers=staff).json()
    assert [i["id"] for i in mine["items"]] == given
    assert mine["items"][0]["assigned_request_id"] == request_id


def test_episode_list_is_paged_and_total_counts_all_pages(client, users, login_as, make_episodes):
    make_episodes(5)
    staff = login_as(users["operator"])
    page = client.get("/episodes?limit=2&offset=2", headers=staff).json()
    assert (page["total"], len(page["items"]), page["limit"], page["offset"]) == (5, 2, 2, 2)
    assert client.get("/episodes?limit=0", headers=staff).status_code == 422
    assert client.get("/episodes?limit=201", headers=staff).status_code == 422
    assert client.get("/episodes?quality=excellent", headers=staff).status_code == 422


def test_task_names_lists_each_name_once(client, users, login_as, make_episodes):
    make_episodes(2, "good", "pick cup")
    make_episodes(1, "good", "fold towel")
    names = client.get("/episodes/task-names", headers=login_as(users["operator"])).json()
    assert names == ["fold towel", "pick cup"]


def test_clients_cannot_browse_all_episodes(client, users, login_as):
    headers = login_as(users["client_a"])
    assert client.get("/episodes", headers=headers).status_code == 403
    assert client.get("/episodes/task-names", headers=headers).status_code == 403
    assert client.get("/episodes").status_code == 401


# ---------------------------------------------------------------- what the client reviews


def test_client_sees_the_episodes_of_their_own_request_only(
    client, users, login_as, make_request, make_episodes
):
    request_id = make_request(owner="client_a")
    ids = make_episodes(2)
    assign(client, login_as(users["operator"]), request_id, ids)

    mine = client.get(f"/requests/{request_id}/episodes", headers=login_as(users["client_a"]))
    assert mine.status_code == 200
    assert [e["id"] for e in mine.json()] == ids

    other = client.get(f"/requests/{request_id}/episodes", headers=login_as(users["client_b"]))
    assert other.status_code == 404  # not even admitted to exist

    staff = client.get(f"/requests/{request_id}/episodes", headers=login_as(users["operator"]))
    assert staff.status_code == 200
