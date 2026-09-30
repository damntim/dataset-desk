"""OPTIONAL demo history, so the reports have something to show. Never runs by itself.

    docker compose exec api python -m app.demo_data

Creates 24 requests spread over the last 60 days: accepted, delivered and waiting,
rejected then reworked, in progress, submitted, some overdue, with a few chat messages.
It follows the same rules as the API (only free good/usable episodes, one request per
episode, history for every step). Safe to run twice: it does nothing if demo data exists.
"""

import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Assignment, DatasetRequest, Episode, RequestMessage, RequestStatusHistory, User

MARK = "[demo]"  # demo requests carry this in their notes
REQUEST_NOTES = ["Arm robots preferred", "Good lighting please", "For grasp training", "Any robot is fine"]
REJECT_REASONS = [
    "Gripper is out of frame for most of the clip",
    "Too dark: the object is hard to see",
    "The cup falls at the end; we need clean grasps",
    "Camera shakes, unusable for training",
]
# How many requests end in each state. A fixed plan (shuffled), so every state is always shown.
PLAN = {
    "accepted": 10,
    "reworked_accepted": 4,
    "delivered": 3,
    "in_progress": 3,
    "submitted": 2,
    "rejected": 2,
}


def run(seed: int = 7) -> None:
    rng = random.Random(seed)
    now = datetime.now(UTC)
    with SessionLocal() as db:
        if db.scalar(select(DatasetRequest.id).where(DatasetRequest.notes.like(f"{MARK}%")).limit(1)):
            print("demo data already exists: nothing to do")
            return

        users = {u.email: u for u in db.scalars(select(User))}
        clients = [users["client-a@example.com"], users["client-b@example.com"]]
        operators = (
            [users["ops1@example.com"]] * 5
            + [users["ops2@example.com"]] * 4
            + [users["admin@example.com"]] * 2
        )

        taken = set(db.scalars(select(Assignment.episode_id)))
        free: dict[str, list[Episode]] = {}
        for episode in db.scalars(
            select(Episode).where(Episode.quality.in_(["good", "usable"])).order_by(Episode.id)
        ):
            if episode.id not in taken:
                free.setdefault(episode.task_name, []).append(episode)

        def take(task, n):
            pool = free.get(task, [])
            picked, free[task] = pool[:n], pool[n:]
            return picked

        def step(request, to_status, at, who):
            db.add(
                RequestStatusHistory(
                    request_id=request.id,
                    from_status=request.status,
                    to_status=to_status,
                    changed_by=who.id,
                    changed_at=at,
                )
            )
            request.status = to_status

        def assign(request, episodes, who, at):
            for e in episodes:
                db.add(Assignment(request_id=request.id, episode_id=e.id, assigned_by=who.id, assigned_at=at))
            if request.operator_id is None:
                request.operator_id = who.id

        def review(request, verdict, at, only=None, note=None):
            db.flush()
            for a in db.scalars(
                select(Assignment).where(
                    Assignment.request_id == request.id, Assignment.review_status == "pending"
                )
            ):
                if only is None or a.episode_id in only:
                    a.review_status, a.reviewed_at, a.review_note = verdict, at, note

        created_count = 0
        plan = [outcome for outcome, n in PLAN.items() for _ in range(n)]
        rng.shuffle(plan)
        for outcome in plan:
            tasks = [t for t, pool in free.items() if len(pool) >= 7]
            if not tasks:
                break
            client, operator, task = rng.choice(clients), rng.choice(operators), rng.choice(tasks)
            wanted = rng.randint(2, 4)
            created = now - timedelta(
                days=rng.uniform(3, 60) if outcome not in ("submitted",) else rng.uniform(0.2, 5)
            )
            # overdue on purpose for some open requests
            open_late = outcome in ("in_progress", "submitted", "rejected") and rng.random() < 0.4
            deadline = (
                created + timedelta(days=rng.randint(3, 6) if open_late else rng.randint(8, 30))
            ).date()

            request = DatasetRequest(
                client_id=client.id,
                task_name=task,
                episodes_requested=wanted,
                deadline=deadline,
                notes=f"{MARK} {rng.choice(REQUEST_NOTES)}",
                status="submitted",
                created_at=created,
            )
            db.add(request)
            db.flush()
            db.add(
                RequestStatusHistory(
                    request_id=request.id, to_status="submitted", changed_by=client.id, changed_at=created
                )
            )
            if outcome == "submitted":
                created_count += 1
                continue

            t = created + timedelta(hours=rng.uniform(0.3, 30))
            step(request, "in_progress", t, operator)
            batch = take(task, wanted if outcome != "in_progress" else rng.randint(0, wanted - 1))
            assign(request, batch, operator, t + timedelta(minutes=20))
            if outcome == "in_progress":
                created_count += 1
                continue

            t += timedelta(hours=rng.uniform(4, 90))
            step(request, "delivered", t, operator)
            if outcome == "delivered":
                created_count += 1
                continue

            t += timedelta(hours=rng.uniform(1, 40))
            if outcome == "accepted":
                review(request, "accepted", t)
                step(request, "accepted", t, client)
            else:  # rejected (maybe reworked afterwards)
                bad = {e.id for e in rng.sample(batch, k=min(len(batch), rng.randint(1, 2)))}
                reason = rng.choice(REJECT_REASONS)
                review(request, "rejected", t, only=bad, note=reason)
                review(request, "accepted", t)
                step(request, "rejected", t, client)
                db.add(
                    RequestMessage(
                        request_id=request.id,
                        author_id=client.id,
                        body=f"I rejected {len(bad)}: {reason}.",
                        created_at=t,
                    )
                )
                if outcome == "reworked_accepted":
                    t += timedelta(hours=rng.uniform(1, 20))
                    db.add(
                        RequestMessage(
                            request_id=request.id,
                            author_id=operator.id,
                            body="Sorry about that, swapping them now.",
                            created_at=t,
                        )
                    )
                    step(request, "in_progress", t, operator)
                    assign(request, take(task, len(bad)), operator, t + timedelta(minutes=30))
                    t += timedelta(hours=rng.uniform(2, 24))
                    step(request, "delivered", t, operator)
                    t += timedelta(hours=rng.uniform(1, 12))
                    review(request, "accepted", t)
                    step(request, "accepted", t, client)
            created_count += 1
        db.commit()
    print(f"demo data: {created_count} requests created")


if __name__ == "__main__":
    run()
