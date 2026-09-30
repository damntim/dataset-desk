"""Reports. Every number is computed by the database (GROUP BY, percentile_cont),
so Python only ever receives the small answer, never the millions of rows behind it."""

from datetime import UTC, date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Date, Float, cast, desc, extract, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_roles
from app.models import STATUSES, DatasetRequest, Episode, RequestStatusHistory, User
from app.schemas import AnalyticsOut

router = APIRouter(prefix="/analytics", tags=["analytics"])

MAX_RANGE_DAYS = 366  # keeps any single report bounded


def _range_start_end(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    """Turn two calendar days (both included) into [start, end) in UTC."""
    if date_to < date_from:
        raise HTTPException(status_code=422, detail="'from' must not be after 'to'")
    if (date_to - date_from).days + 1 > MAX_RANGE_DAYS:
        raise HTTPException(status_code=422, detail=f"The range is limited to {MAX_RANGE_DAYS} days")
    try:
        end_day = date_to + timedelta(days=1)
    except OverflowError:
        raise HTTPException(status_code=422, detail="'to' is too far in the future") from None
    start = datetime.combine(date_from, time.min, tzinfo=UTC)
    end = datetime.combine(end_day, time.min, tzinfo=UTC)
    return start, end


@router.get("", response_model=AnalyticsOut)
def analytics(
    date_from: date = Query(alias="from", description="First day, YYYY-MM-DD (included)"),
    date_to: date = Query(alias="to", description="Last day, YYYY-MM-DD (included)"),
    db: Session = Depends(get_db),
    _staff: User = Depends(require_roles("operator", "admin")),
):
    start, end = _range_start_end(date_from, date_to)

    # 1) Episodes recorded per day, per robot (days are UTC days).
    #    The (recorded_at, robot_id) index covers this query completely.
    day = cast(func.timezone("UTC", Episode.recorded_at), Date)
    per_day = db.execute(
        select(day.label("day"), Episode.robot_id, func.count().label("episodes"))
        .where(Episode.recorded_at >= start, Episode.recorded_at < end)
        .group_by(day, Episode.robot_id)
        .order_by(day, Episode.robot_id)
    ).all()

    # 2a) Requests created in the range, counted by their current status.
    created_in_range = (DatasetRequest.created_at >= start, DatasetRequest.created_at < end)
    counted = dict(
        db.execute(
            select(DatasetRequest.status, func.count())
            .where(*created_in_range)
            .group_by(DatasetRequest.status)
        ).all()
    )
    by_status = {status: counted.get(status, 0) for status in STATUSES}

    # 2b) Median time from submitted (= created) to the FIRST delivery, in seconds.
    #     A request that was rejected and re-delivered still counts once.
    first_delivery = (
        select(
            RequestStatusHistory.request_id.label("request_id"),
            func.min(RequestStatusHistory.changed_at).label("at"),
        )
        .where(RequestStatusHistory.to_status == "delivered")
        .group_by(RequestStatusHistory.request_id)
        .subquery()
    )
    seconds_to_deliver = cast(extract("epoch", first_delivery.c.at - DatasetRequest.created_at), Float)
    delivered_count, median = db.execute(
        select(func.count(), func.percentile_cont(0.5).within_group(seconds_to_deliver))
        .select_from(DatasetRequest)
        .join(first_delivery, first_delivery.c.request_id == DatasetRequest.id)
        .where(*created_in_range)
    ).one()

    # 3) The 5 task names with the most GOOD episodes (ties: alphabetical, so it is stable).
    top_tasks = db.execute(
        select(Episode.task_name, func.count().label("good_episodes"))
        .where(Episode.quality == "good", Episode.recorded_at >= start, Episode.recorded_at < end)
        .group_by(Episode.task_name)
        .order_by(desc("good_episodes"), Episode.task_name)
        .limit(5)
    ).all()

    return AnalyticsOut(
        date_from=date_from,
        date_to=date_to,
        episodes_per_day=[{"day": d, "robot_id": robot, "episodes": n} for d, robot, n in per_day],
        requests={
            "by_status": by_status,
            "total": sum(by_status.values()),
            "delivered_count": delivered_count,
            "median_seconds_to_deliver": float(median) if median is not None else None,
        },
        top_tasks_by_good_episodes=[{"task_name": name, "good_episodes": n} for name, n in top_tasks],
    )
