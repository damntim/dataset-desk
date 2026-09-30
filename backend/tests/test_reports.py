"""The admin insight report, checked against a small story whose numbers are worked out by hand.

The story (all times UTC, range = August 2026):

  R1  Acme, run by op1   created Mon 08-03 08:00  started +1h  delivered +10h  accepted +12h
      deadline 08-10 (on time)   3 episodes arm-01 "pick cup", all accepted
  R2  Acme, run by op2   created Tue 08-04 08:00  started +3h  delivered +30h  rejected +34h
      deadline 08-04 (LATE)      2 arm-01 accepted + 2 arm-02 rejected ("blurry"), "fold towel"
  R3  Beta, run by op1   created Mon 08-10 08:00  started +2h  delivered +20h  accepted +21h
      deadline 08-20 (on time)   2 episodes arm-03 "pick cup", accepted
  R4  Beta, nobody yet   created Wed 08-12, still submitted, deadline yesterday (overdue)
  R5  Acme, run by op1   created in JULY (outside the range), accepted
"""

from datetime import UTC, date, datetime, timedelta
from itertools import count

import pytest

from app.db import SessionLocal
from app.models import Assignment, DatasetRequest, Episode, RequestStatusHistory

HOUR = 3600
_ids = count(1)


def at(text):
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def add_request(client, operator, created, deadline, steps, episodes=(), status=None):
    """steps: [(status, hours after creation, who)]. episodes: [(robot, task, verdict, note)]."""
    with SessionLocal() as db:
        request = DatasetRequest(
            client_id=client.id,
            operator_id=operator.id if operator else None,
            task_name="pick cup",
            episodes_requested=max(1, len(episodes)),
            deadline=deadline,
            status=status or (steps[-1][0] if steps else "submitted"),
            created_at=created,
        )
        db.add(request)
        db.flush()
        db.add(
            RequestStatusHistory(
                request_id=request.id, to_status="submitted", changed_by=client.id, changed_at=created
            )
        )
        previous = "submitted"
        for to_status, hours, who in steps:
            moment = created + timedelta(hours=hours)
            db.add(
                RequestStatusHistory(
                    request_id=request.id,
                    from_status=previous,
                    to_status=to_status,
                    changed_by=who.id,
                    changed_at=moment,
                )
            )
            previous = to_status
        decided_at = created + timedelta(hours=steps[-1][1]) if steps else None
        for robot, task, verdict, note in episodes:
            episode = Episode(
                episode_id=f"EP-R{next(_ids):05d}",
                robot_id=robot,
                task_name=task,
                recorded_at=at("2026-07-01T10:00:00"),
                duration_seconds=30,
                quality="good",
            )
            db.add(episode)
            db.flush()
            db.add(
                Assignment(
                    request_id=request.id,
                    episode_id=episode.id,
                    assigned_by=operator.id,
                    review_status=verdict,
                    review_note=note,
                    reviewed_at=decided_at if verdict != "pending" else None,
                )
            )
        db.commit()
        return request.id


@pytest.fixture
def story(users, make_user):
    op1, admin = users["operator"], users["admin"]
    op2 = make_user("op2@test.com", "operator")
    acme, beta = users["client_a"], users["client_b"]
    ids = {}
    ids["R1"] = add_request(
        acme,
        op1,
        at("2026-08-03T08:00:00"),
        date(2026, 8, 10),
        [("in_progress", 1, op1), ("delivered", 10, op1), ("accepted", 12, acme)],
        [("arm-01", "pick cup", "accepted", None)] * 3,
    )
    ids["R2"] = add_request(
        acme,
        op2,
        at("2026-08-04T08:00:00"),
        date(2026, 8, 4),
        [("in_progress", 3, op2), ("delivered", 30, op2), ("rejected", 34, acme)],
        [("arm-01", "fold towel", "accepted", None)] * 2
        + [("arm-02", "fold towel", "rejected", "blurry")] * 2,
    )
    ids["R3"] = add_request(
        beta,
        op1,
        at("2026-08-10T08:00:00"),
        date(2026, 8, 20),
        [("in_progress", 2, op1), ("delivered", 20, op1), ("accepted", 21, beta)],
        [("arm-03", "pick cup", "accepted", None)] * 2,
    )
    ids["R4"] = add_request(beta, None, at("2026-08-12T08:00:00"), date.today() - timedelta(days=1), [])
    ids["R5"] = add_request(
        acme,
        op1,
        at("2026-07-15T08:00:00"),
        date(2026, 7, 30),
        [("in_progress", 1, op1), ("delivered", 2, op1), ("accepted", 3, acme)],
        [("arm-01", "pick cup", "accepted", None)],
    )
    return {"ids": ids, "op1": op1, "op2": op2, "admin": admin}


def report(client, headers, start="2026-08-01", end="2026-08-31"):
    response = client.get(f"/reports/overview?from={start}&to={end}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def admin_headers(users, login_as):
    return login_as(users["admin"])


# ---------------------------------------------------------------- access


@pytest.mark.parametrize("who", ["operator", "client_a"])
def test_only_admins_can_read_the_report(client, users, login_as, who):
    response = client.get("/reports/overview?from=2026-08-01&to=2026-08-31", headers=login_as(users[who]))
    assert response.status_code == 403


def test_anonymous_gets_401(client):
    assert client.get("/reports/overview?from=2026-08-01&to=2026-08-31").status_code == 401


def test_invalid_range_is_422(client, admin_headers):
    assert (
        client.get("/reports/overview?from=2026-08-31&to=2026-08-01", headers=admin_headers).status_code
        == 422
    )


def test_empty_database_gives_zeros_and_no_top_operator(client, admin_headers):
    body = report(client, admin_headers)
    assert body["kpis"]["requests"] == 0
    assert body["kpis"]["median_delivery_seconds"] is None
    assert body["kpis"]["on_time_rate"] is None
    assert body["top_operator"] is None
    assert body["operators"] == body["clients"] == body["rejected_episodes"] == []


# ---------------------------------------------------------------- headline numbers


def test_headline_numbers(client, admin_headers, story):
    k = report(client, admin_headers)["kpis"]
    assert (k["requests"], k["delivered"], k["accepted"]) == (4, 3, 2)  # R5 is outside the range
    assert k["on_time_rate"] == round(2 / 3, 4)  # R1 and R3 on time, R2 late
    assert k["median_first_response_seconds"] == 2 * HOUR  # 1h, 3h, 2h
    assert k["median_delivery_seconds"] == 20 * HOUR  # 10h, 30h, 20h
    assert k["median_client_review_seconds"] == 2 * HOUR  # 2h, 4h, 1h
    assert (k["episodes_delivered"], k["episodes_reviewed"], k["episodes_rejected"]) == (9, 9, 2)
    assert k["episode_rejection_rate"] == round(2 / 9, 4)


def test_weekly_trend_by_monday(client, admin_headers, story):
    assert report(client, admin_headers)["weekly"] == [
        {"week": "2026-08-03", "created": 2, "delivered": 2, "accepted": 1},
        {"week": "2026-08-10", "created": 2, "delivered": 1, "accepted": 1},
    ]


# ---------------------------------------------------------------- operators


def test_operator_leaderboard_and_top_operator(client, admin_headers, story):
    body = report(client, admin_headers)
    first, second = body["operators"]
    assert first["user_id"] == story["op1"].id
    assert (first["requests"], first["delivered"], first["accepted"]) == (2, 2, 2)
    assert first["on_time_rate"] == 1.0
    assert first["median_delivery_seconds"] == 15 * HOUR  # 10h and 20h
    assert (first["episodes_assigned"], first["episodes_accepted"], first["episodes_rejected"]) == (5, 5, 0)
    assert first["episode_acceptance_rate"] == 1.0

    assert second["user_id"] == story["op2"].id
    assert (second["accepted"], second["on_time_rate"]) == (0, 0.0)
    assert (second["episodes_assigned"], second["episode_acceptance_rate"]) == (4, 0.5)

    assert body["top_operator"]["user_id"] == story["op1"].id


# ---------------------------------------------------------------- clients and rejections


def test_client_insights_sorted_by_rejection_rate(client, admin_headers, story):
    acme, beta = report(client, admin_headers)["clients"]
    assert acme["name"] == "Acme"
    assert (acme["requests"], acme["accepted"], acme["episodes_reviewed"], acme["episodes_rejected"]) == (
        2,
        1,
        7,
        2,
    )
    assert acme["rejection_rate"] == round(2 / 7, 4)
    assert acme["median_review_seconds"] == 3 * HOUR  # 2h and 4h
    assert (beta["name"], beta["rejection_rate"], beta["median_review_seconds"]) == ("Beta", 0.0, 1 * HOUR)


def test_what_gets_rejected_by_robot_and_task(client, admin_headers, story):
    body = report(client, admin_headers)
    assert body["rejections_by_robot"][0] == {"key": "arm-02", "reviewed": 2, "rejected": 2, "rate": 1.0}
    assert {r["key"] for r in body["rejections_by_robot"]} == {"arm-01", "arm-02", "arm-03"}
    assert body["rejections_by_task"][0] == {"key": "fold towel", "reviewed": 4, "rejected": 2, "rate": 0.5}


def test_every_rejected_video_is_listed_with_reason_client_and_operator(client, admin_headers, story):
    rejected = report(client, admin_headers)["rejected_episodes"]
    assert len(rejected) == 2
    assert {r["request_id"] for r in rejected} == {story["ids"]["R2"]}
    assert all(r["review_note"] == "blurry" and r["client_name"] == "Acme" for r in rejected)
    assert all(r["assigned_by_name"] == "op2" and r["robot_id"] == "arm-02" for r in rejected)


def test_at_risk_lists_open_requests_that_are_overdue_or_due_soon(client, admin_headers, story):
    at_risk = report(client, admin_headers)["at_risk"]
    assert [r["id"] for r in at_risk] == [story["ids"]["R2"], story["ids"]["R4"]]  # accepted ones never
    r4 = at_risk[1]
    assert (r4["days_left"], r4["operator_name"], r4["status"]) == (-1, None, "submitted")


def test_a_narrower_range_only_counts_what_happened_in_it(client, admin_headers, story):
    k = report(client, admin_headers, "2026-08-10", "2026-08-16")["kpis"]
    assert (k["requests"], k["delivered"], k["accepted"]) == (2, 1, 1)  # R3 and R4
