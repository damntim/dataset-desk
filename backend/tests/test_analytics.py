"""Analytics: exact numbers we can calculate by hand, boundaries, and access rules."""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import event

from app.db import SessionLocal, engine
from app.models import DatasetRequest, Episode, RequestStatusHistory

UTC = timezone.utc


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def add_episode(recorded_at: str, robot="arm-01", task="pick cup", quality="good", n=1):
    with SessionLocal() as db:
        for _ in range(n):
            db.add(
                Episode(
                    episode_id=f"EP-A{db.query(Episode).count() + 1:06d}",
                    robot_id=robot,
                    task_name=task,
                    recorded_at=at(recorded_at),
                    duration_seconds=30,
                    quality=quality,
                )
            )
            db.flush()
        db.commit()


def add_request(users, created: str, status="submitted", delivered_after: list[timedelta] = ()):
    """A request created at `created`, with a history row for each delivery
    (offsets from creation). Several offsets = delivered, rejected, delivered again..."""
    with SessionLocal() as db:
        request = DatasetRequest(
            client_id=users["client_a"].id,
            task_name="pick cup",
            episodes_requested=1,
            deadline=date(2030, 1, 1),
            status=status,
            created_at=at(created),
        )
        db.add(request)
        db.flush()
        db.add(
            RequestStatusHistory(
                request_id=request.id, from_status=None, to_status="submitted",
                changed_by=users["client_a"].id, changed_at=at(created),
            )
        )
        for offset in delivered_after:
            db.add(
                RequestStatusHistory(
                    request_id=request.id, from_status="in_progress", to_status="delivered",
                    changed_by=users["operator"].id, changed_at=at(created) + offset,
                )
            )
        db.commit()


def report(client, headers, start="2026-08-01", end="2026-08-31"):
    response = client.get(f"/analytics?from={start}&to={end}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def staff(login_as, users):
    return login_as(users["operator"])


# ---------------------------------------------------------------- who may look


@pytest.mark.parametrize("who", ["operator", "admin"])
def test_staff_can_read_analytics(client, users, login_as, who):
    assert client.get("/analytics?from=2026-08-01&to=2026-08-31", headers=login_as(users[who])).status_code == 200


def test_clients_cannot_read_analytics(client, users, login_as):
    headers = login_as(users["client_a"])
    assert client.get("/analytics?from=2026-08-01&to=2026-08-31", headers=headers).status_code == 403


def test_anonymous_cannot_read_analytics(client):
    assert client.get("/analytics?from=2026-08-01&to=2026-08-31").status_code == 401


# ---------------------------------------------------------------- bad input


@pytest.mark.parametrize(
    "query",
    [
        "",  # both missing
        "from=2026-08-01",  # 'to' missing
        "from=2026-08-31&to=2026-08-01",  # backwards
        "from=2026-08-01&to=not-a-date",
        "from=2025-01-01&to=2026-12-31",  # more than 366 days
        "from=2026-01-01&to=9999-12-31",
    ],
)
def test_invalid_ranges_are_422(client, users, login_as, query):
    assert client.get(f"/analytics?{query}", headers=login_as(users["operator"])).status_code == 422


def test_a_range_of_exactly_366_days_is_allowed(client, users, staff):
    assert client.get("/analytics?from=2025-01-01&to=2026-01-01", headers=staff).status_code == 200


# ---------------------------------------------------------------- nothing there yet


def test_empty_database_gives_zeros_and_empty_lists(client, users, staff):
    body = report(client, staff)
    assert body["from"] == "2026-08-01" and body["to"] == "2026-08-31"
    assert body["episodes_per_day"] == []
    assert body["top_tasks_by_good_episodes"] == []
    assert body["requests"] == {
        "by_status": {"submitted": 0, "in_progress": 0, "delivered": 0, "accepted": 0, "rejected": 0},
        "total": 0,
        "delivered_count": 0,
        "median_seconds_to_deliver": None,
    }


# ---------------------------------------------------------------- episodes per day per robot


def test_episodes_are_counted_per_day_and_per_robot(client, users, staff):
    add_episode("2026-08-05T10:00:00", robot="arm-01", n=3)
    add_episode("2026-08-05T18:30:00", robot="arm-02", n=2)
    add_episode("2026-08-06T09:00:00", robot="arm-01", n=1)
    add_episode("2026-08-05T23:00:00", robot="arm-01", quality="bad", n=1)  # quality does not matter here

    rows = report(client, staff)["episodes_per_day"]
    assert rows == [
        {"day": "2026-08-05", "robot_id": "arm-01", "episodes": 4},
        {"day": "2026-08-05", "robot_id": "arm-02", "episodes": 2},
        {"day": "2026-08-06", "robot_id": "arm-01", "episodes": 1},
    ]


def test_range_includes_the_whole_first_and_last_day_and_nothing_else(client, users, staff):
    add_episode("2026-07-31T23:59:59")  # just before the range
    add_episode("2026-08-01T00:00:00")  # first moment of the first day: IN
    add_episode("2026-08-31T23:59:59")  # last moment of the last day: IN
    add_episode("2026-09-01T00:00:00")  # first moment after the range

    rows = report(client, staff, "2026-08-01", "2026-08-31")["episodes_per_day"]
    assert [(r["day"], r["episodes"]) for r in rows] == [("2026-08-01", 1), ("2026-08-31", 1)]


def test_days_are_utc_days(client, users, staff):
    add_episode("2026-08-05T23:59:59")
    add_episode("2026-08-06T00:00:00")
    days = [r["day"] for r in report(client, staff)["episodes_per_day"]]
    assert days == ["2026-08-05", "2026-08-06"]


# ---------------------------------------------------------------- top 5 tasks


def test_top_five_tasks_count_only_good_episodes_and_break_ties_alphabetically(client, users, staff):
    for task, good in [("a", 9), ("b", 8), ("c", 7), ("d", 6), ("e", 5), ("f", 4), ("g", 3)]:
        add_episode("2026-08-10T10:00:00", task=task, n=good)
    add_episode("2026-08-10T10:00:00", task="g", quality="usable", n=50)  # not good: ignored
    add_episode("2026-08-10T10:00:00", task="g", quality="bad", n=50)  # not good: ignored
    add_episode("2026-09-10T10:00:00", task="g", n=50)  # outside the range: ignored

    top = report(client, staff)["top_tasks_by_good_episodes"]
    assert [(t["task_name"], t["good_episodes"]) for t in top] == [
        ("a", 9), ("b", 8), ("c", 7), ("d", 6), ("e", 5),
    ]


def test_tied_tasks_come_out_in_alphabetical_order(client, users, staff):
    for task in ["zebra", "apple", "mango"]:
        add_episode("2026-08-10T10:00:00", task=task, n=2)
    names = [t["task_name"] for t in report(client, staff)["top_tasks_by_good_episodes"]]
    assert names == ["apple", "mango", "zebra"]


# ---------------------------------------------------------------- requests: counts and median


def test_requests_are_counted_by_status_for_requests_created_in_the_range(client, users, staff):
    add_request(users, "2026-08-05T10:00:00", "submitted")
    add_request(users, "2026-08-06T10:00:00", "submitted")
    add_request(users, "2026-08-07T10:00:00", "accepted")
    add_request(users, "2026-07-31T10:00:00", "accepted")  # created before the range
    add_request(users, "2026-09-01T10:00:00", "rejected")  # created after the range

    requests = report(client, staff)["requests"]
    assert requests["by_status"] == {
        "submitted": 2, "in_progress": 0, "delivered": 0, "accepted": 1, "rejected": 0,
    }
    assert requests["total"] == 3


def test_median_of_an_odd_number_of_requests_is_the_middle_one(client, users, staff):
    for hours in (1, 2, 10):  # the 10 hour outlier must not matter
        add_request(users, "2026-08-05T08:00:00", "accepted", [timedelta(hours=hours)])
    requests = report(client, staff)["requests"]
    assert requests["delivered_count"] == 3
    assert requests["median_seconds_to_deliver"] == 2 * 3600


def test_median_of_an_even_number_is_halfway_between_the_two_middle_ones(client, users, staff):
    for hours in (1, 2, 3, 4):
        add_request(users, "2026-08-05T08:00:00", "accepted", [timedelta(hours=hours)])
    assert report(client, staff)["requests"]["median_seconds_to_deliver"] == 2.5 * 3600


def test_only_the_first_delivery_counts_when_a_request_is_reworked(client, users, staff):
    # delivered after 1h, rejected, delivered again after 30h: counts as 1h, and only once
    add_request(users, "2026-08-05T08:00:00", "accepted", [timedelta(hours=1), timedelta(hours=30)])
    requests = report(client, staff)["requests"]
    assert requests["delivered_count"] == 1
    assert requests["median_seconds_to_deliver"] == 3600


def test_requests_that_were_never_delivered_are_left_out_of_the_median(client, users, staff):
    add_request(users, "2026-08-05T08:00:00", "in_progress")
    add_request(users, "2026-08-05T08:00:00", "submitted")
    add_request(users, "2026-08-05T08:00:00", "rejected", [timedelta(hours=4)])  # was delivered once
    requests = report(client, staff)["requests"]
    assert requests["delivered_count"] == 1
    assert requests["median_seconds_to_deliver"] == 4 * 3600


def test_median_only_uses_requests_created_in_the_range(client, users, staff):
    add_request(users, "2026-08-05T08:00:00", "accepted", [timedelta(hours=2)])
    add_request(users, "2026-07-05T08:00:00", "accepted", [timedelta(hours=100)])  # earlier
    assert report(client, staff)["requests"]["median_seconds_to_deliver"] == 2 * 3600


# ---------------------------------------------------------------- the work happens in the database


def count_sql_statements(action) -> int:
    seen = []
    listener = lambda conn, cursor, statement, *rest: seen.append(statement)  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        action()
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    return len(seen)


def test_the_number_of_queries_does_not_grow_with_the_amount_of_data(client, users, staff):
    """No 'load every row and loop in Python': the same few queries however much data there is."""
    add_episode("2026-08-05T10:00:00", n=2)
    add_request(users, "2026-08-05T08:00:00", "accepted", [timedelta(hours=1)])
    small = count_sql_statements(lambda: report(client, staff))

    for day in range(1, 20):
        add_episode(f"2026-08-{day:02d}T10:00:00", robot="arm-02", task=f"task {day}", n=5)
        add_request(users, f"2026-08-{day:02d}T08:00:00", "accepted", [timedelta(hours=day)])
    large = count_sql_statements(lambda: report(client, staff))

    assert small == large
    assert large <= 6  # 1 user lookup + 4 report queries (+ 1 spare)
