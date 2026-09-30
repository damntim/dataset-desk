"""The admin's insight report. Like /analytics, every number is computed by PostgreSQL.

Key idea: one "timeline" sub-query gives, for each request created in the range, the moments
that matter (read from the status history):

    created ──> started (first in_progress) ──> delivered (first delivery) ──> decided (first
                 accept/reject by the client after a delivery)

    first response time = started   - created
    delivery time       = delivered - created
    client review time  = decided   - delivered
    on time             = delivered (as a UTC day) <= deadline
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Date, Float, and_, cast, extract, func, select
from sqlalchemy.orm import Session, aliased

from app.db import get_db
from app.deps import require_roles
from app.models import Assignment, DatasetRequest, Episode, RequestStatusHistory, User
from app.routers.analytics import range_start_end
from app.schemas import ReportOut

router = APIRouter(prefix="/reports", tags=["reports"])

H = RequestStatusHistory
LIST_LIMIT = 50  # longest list in the report (rejected videos)
AT_RISK_DAYS = 3  # "due within 3 days" counts as at risk


def _seconds(later, earlier):
    return cast(extract("epoch", later - earlier), Float)


def _median(expression):
    return func.percentile_cont(0.5).within_group(expression)


def _rate(part, whole):
    return round(part / whole, 4) if whole else None


def _first(status: str):
    """For each request: the first time it reached `status`."""
    return (
        select(H.request_id, func.min(H.changed_at).label("at"))
        .where(H.to_status == status)
        .group_by(H.request_id)
        .subquery()
    )


def _timeline(start, end):
    started, delivered = _first("in_progress"), _first("delivered")
    decided = (
        select(H.request_id, func.min(H.changed_at).label("at"))
        .where(H.from_status == "delivered", H.to_status.in_(["accepted", "rejected"]))
        .group_by(H.request_id)
        .subquery()
    )
    return (
        select(
            DatasetRequest.id,
            DatasetRequest.client_id,
            DatasetRequest.operator_id,
            DatasetRequest.status,
            DatasetRequest.deadline,
            DatasetRequest.created_at,
            started.c.at.label("started"),
            delivered.c.at.label("delivered"),
            decided.c.at.label("decided"),
        )
        .outerjoin(started, started.c.request_id == DatasetRequest.id)
        .outerjoin(delivered, delivered.c.request_id == DatasetRequest.id)
        .outerjoin(decided, decided.c.request_id == DatasetRequest.id)
        .where(DatasetRequest.created_at >= start, DatasetRequest.created_at < end)
        .subquery("t")
    )


def _request_stats(t):
    """The same set of request numbers, used for the headline and per operator/client."""
    on_time = and_(t.c.delivered.isnot(None), cast(func.timezone("UTC", t.c.delivered), Date) <= t.c.deadline)
    return [
        func.count().label("requests"),
        func.count(t.c.delivered).label("delivered"),
        func.count().filter(t.c.status == "accepted").label("accepted"),
        func.count().filter(on_time).label("on_time"),
        _median(_seconds(t.c.started, t.c.created_at)).label("median_response"),
        _median(_seconds(t.c.delivered, t.c.created_at)).label("median_delivery"),
        _median(_seconds(t.c.decided, t.c.delivered)).label("median_review"),
    ]


def _episode_stats():
    return [
        func.count(Assignment.id).label("episodes"),
        func.count().filter(Assignment.review_status == "accepted").label("accepted"),
        func.count().filter(Assignment.review_status == "rejected").label("rejected"),
    ]


@router.get("/overview", response_model=ReportOut)
def overview(
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles("admin")),
):
    start, end = range_start_end(date_from, date_to)
    t = _timeline(start, end)

    # ------------------------------------------------ headline numbers
    kpi = db.execute(select(*_request_stats(t))).one()
    episodes = db.execute(select(*_episode_stats()).join(t, t.c.id == Assignment.request_id)).one()
    reviewed = episodes.accepted + episodes.rejected

    # ------------------------------------------------ weekly trend (weeks start on Monday, UTC)
    def week(column):
        return cast(func.date_trunc("week", func.timezone("UTC", column)), Date)

    trend = {}
    for key, column, source in (
        ("created", t.c.created_at, t),
        ("delivered", t.c.delivered, t),
        ("accepted", H.changed_at, None),
    ):
        if source is None:  # acceptances that happened in the range
            query = (
                select(week(H.changed_at).label("w"), func.count())
                .where(H.to_status == "accepted", H.changed_at >= start, H.changed_at < end)
                .group_by("w")
            )
        else:
            query = select(week(column).label("w"), func.count()).where(column.isnot(None)).group_by("w")
        for w, n in db.execute(query).all():
            trend.setdefault(w, {"created": 0, "delivered": 0, "accepted": 0})[key] = n

    # ------------------------------------------------ operators (the person who ran the request)
    Operator = aliased(User)
    by_operator = {
        row.id: row
        for row in db.execute(
            select(Operator.id, Operator.name, *_request_stats(t))
            .join(t, t.c.operator_id == Operator.id)
            .group_by(Operator.id, Operator.name)
        ).all()
    }
    # the episodes each person assigned (for requests in the range)
    episodes_by_assigner = {
        row.assigned_by: row
        for row in db.execute(
            select(Assignment.assigned_by, *_episode_stats())
            .join(t, t.c.id == Assignment.request_id)
            .group_by(Assignment.assigned_by)
        ).all()
    }
    names = dict(
        db.execute(
            select(User.id, User.name).where(User.id.in_(set(by_operator) | set(episodes_by_assigner)))
        ).all()
    )
    operators = []
    for user_id in set(by_operator) | set(episodes_by_assigner):
        r, e = by_operator.get(user_id), episodes_by_assigner.get(user_id)
        ep_reviewed = (e.accepted + e.rejected) if e else 0
        operators.append(
            {
                "user_id": user_id,
                "name": names[user_id],
                "requests": r.requests if r else 0,
                "delivered": r.delivered if r else 0,
                "accepted": r.accepted if r else 0,
                "on_time_rate": _rate(r.on_time, r.delivered) if r else None,
                "median_delivery_seconds": r.median_delivery if r else None,
                "episodes_assigned": e.episodes if e else 0,
                "episodes_accepted": e.accepted if e else 0,
                "episodes_rejected": e.rejected if e else 0,
                "episode_acceptance_rate": _rate(e.accepted, ep_reviewed) if e else None,
            }
        )
    # Ranking: most accepted requests, then best episode acceptance, then fastest delivery.
    operators.sort(
        key=lambda o: (
            -o["accepted"],
            -(o["episode_acceptance_rate"] or 0),
            o["median_delivery_seconds"] if o["median_delivery_seconds"] is not None else float("inf"),
            o["name"],
        )
    )

    # ------------------------------------------------ clients
    Client = aliased(User)
    client_rows = db.execute(
        select(Client.id, func.coalesce(Client.organisation, Client.name).label("name"), *_request_stats(t))
        .join(t, t.c.client_id == Client.id)
        .group_by(Client.id, Client.organisation, Client.name)
    ).all()
    client_episodes = {
        row.client_id: row
        for row in db.execute(
            select(t.c.client_id, *_episode_stats())
            .join(Assignment, Assignment.request_id == t.c.id)
            .group_by(t.c.client_id)
        ).all()
    }
    clients = []
    for row in client_rows:
        e = client_episodes.get(row.id)
        ep_reviewed = (e.accepted + e.rejected) if e else 0
        clients.append(
            {
                "user_id": row.id,
                "name": row.name,
                "requests": row.requests,
                "accepted": row.accepted,
                "episodes_reviewed": ep_reviewed,
                "episodes_rejected": e.rejected if e else 0,
                "rejection_rate": _rate(e.rejected, ep_reviewed) if e else None,
                "median_review_seconds": row.median_review,
            }
        )
    clients.sort(key=lambda c: (-(c["rejection_rate"] or 0), -c["requests"], c["name"]))

    # ------------------------------------------------ what gets rejected (by robot, by task)
    def rejections_by(column):
        rows = db.execute(
            select(
                column.label("key"),
                func.count().filter(Assignment.review_status.in_(["accepted", "rejected"])).label("reviewed"),
                func.count().filter(Assignment.review_status == "rejected").label("rejected"),
            )
            .select_from(Assignment)
            .join(Episode, Episode.id == Assignment.episode_id)
            .join(t, t.c.id == Assignment.request_id)
            .group_by(column)
        ).all()
        result = [
            {
                "key": r.key,
                "reviewed": r.reviewed,
                "rejected": r.rejected,
                "rate": _rate(r.rejected, r.reviewed),
            }
            for r in rows
            if r.reviewed
        ]
        return sorted(result, key=lambda x: (-(x["rate"] or 0), -x["rejected"], x["key"]))

    # ------------------------------------------------ every rejected video, newest first
    ClientUser, Assigner = aliased(User), aliased(User)
    rejected_rows = db.execute(
        select(
            Episode.id,
            Episode.episode_id,
            Episode.robot_id,
            Episode.task_name,
            Episode.quality,
            Assignment.request_id,
            Assignment.review_note,
            Assignment.reviewed_at,
            func.coalesce(ClientUser.organisation, ClientUser.name).label("client_name"),
            Assigner.name.label("assigned_by_name"),
        )
        .select_from(Assignment)
        .join(Episode, Episode.id == Assignment.episode_id)
        .join(DatasetRequest, DatasetRequest.id == Assignment.request_id)
        .join(ClientUser, ClientUser.id == DatasetRequest.client_id)
        .join(Assigner, Assigner.id == Assignment.assigned_by)
        .where(
            Assignment.review_status == "rejected",
            Assignment.reviewed_at >= start,
            Assignment.reviewed_at < end,
        )
        .order_by(Assignment.reviewed_at.desc(), Episode.id)
        .limit(LIST_LIMIT)
    ).all()

    # ------------------------------------------------ at risk: open, overdue or due soon (today's state)
    counting = (
        select(func.count(Assignment.id))
        .where(Assignment.request_id == DatasetRequest.id, Assignment.review_status != "rejected")
        .correlate(DatasetRequest)
        .scalar_subquery()
    )
    RiskClient, RiskOperator = aliased(User), aliased(User)
    today = date.today()
    at_risk = db.execute(
        select(
            DatasetRequest.id,
            DatasetRequest.task_name,
            DatasetRequest.status,
            DatasetRequest.deadline,
            DatasetRequest.episodes_requested,
            counting.label("episodes_assigned"),
            func.coalesce(RiskClient.organisation, RiskClient.name).label("client_name"),
            RiskOperator.name.label("operator_name"),
        )
        .join(RiskClient, RiskClient.id == DatasetRequest.client_id)
        .outerjoin(RiskOperator, RiskOperator.id == DatasetRequest.operator_id)
        .where(
            DatasetRequest.status != "accepted",
            DatasetRequest.deadline <= today + timedelta(days=AT_RISK_DAYS),
        )
        .order_by(DatasetRequest.deadline, DatasetRequest.id)
        .limit(20)
    ).all()

    return ReportOut(
        date_from=date_from,
        date_to=date_to,
        kpis={
            "requests": kpi.requests,
            "delivered": kpi.delivered,
            "accepted": kpi.accepted,
            "on_time_rate": _rate(kpi.on_time, kpi.delivered),
            "median_first_response_seconds": kpi.median_response,
            "median_delivery_seconds": kpi.median_delivery,
            "median_client_review_seconds": kpi.median_review,
            "episodes_delivered": episodes.episodes,
            "episodes_reviewed": reviewed,
            "episodes_rejected": episodes.rejected,
            "episode_rejection_rate": _rate(episodes.rejected, reviewed),
        },
        weekly=[{"week": w, **counts} for w, counts in sorted(trend.items())],
        operators=operators,
        top_operator=operators[0] if operators and operators[0]["accepted"] > 0 else None,
        clients=clients,
        rejections_by_robot=rejections_by(Episode.robot_id),
        rejections_by_task=rejections_by(Episode.task_name),
        rejected_episodes=[dict(r._mapping) for r in rejected_rows],
        at_risk=[{**dict(r._mapping), "days_left": (r.deadline - today).days} for r in at_risk],
    )
