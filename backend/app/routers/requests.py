from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_roles
from app.models import Assignment, DatasetRequest, RequestStatusHistory, User
from app.schemas import (
    HistoryOut,
    RequestCreate,
    RequestDetailOut,
    RequestOut,
    Status,
    StatusChange,
)
from app.workflow import TRANSITIONS, next_statuses

router = APIRouter(prefix="/requests", tags=["requests"])


def _base_query():
    """Request + its client + how many episodes are assigned so far."""
    assigned = (
        select(func.count(Assignment.id))
        .where(Assignment.request_id == DatasetRequest.id)
        .correlate(DatasetRequest)
        .scalar_subquery()
    )
    return select(DatasetRequest, User, assigned.label("assigned")).join(
        User, User.id == DatasetRequest.client_id
    )


def _to_out(row, viewer: User) -> dict:
    request, client, assigned = row
    return {
        "id": request.id,
        "client_id": request.client_id,
        "client_name": client.organisation or client.name,
        "task_name": request.task_name,
        "episodes_requested": request.episodes_requested,
        "episodes_assigned": assigned,
        "deadline": request.deadline,
        "notes": request.notes,
        "status": request.status,
        "created_at": request.created_at,
        "allowed_next": next_statuses(request.status, viewer.role),
    }


def _load_detail(db: Session, request_id: int, viewer: User) -> RequestDetailOut:
    """One request with its history. A client only ever sees their own: for anything
    else we answer 404, so we do not even reveal that the request exists."""
    stmt = _base_query().where(DatasetRequest.id == request_id)
    if viewer.role == "client":
        stmt = stmt.where(DatasetRequest.client_id == viewer.id)
    row = db.execute(stmt).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Request not found")

    history_rows = db.execute(
        select(RequestStatusHistory, User.name)
        .join(User, User.id == RequestStatusHistory.changed_by)
        .where(RequestStatusHistory.request_id == request_id)
        .order_by(RequestStatusHistory.changed_at, RequestStatusHistory.id)
    ).all()
    history = [
        HistoryOut(
            from_status=h.from_status,
            to_status=h.to_status,
            changed_by_name=name,
            changed_at=h.changed_at,
        )
        for h, name in history_rows
    ]
    return RequestDetailOut(**_to_out(row, viewer), history=history)


@router.post("", response_model=RequestDetailOut, status_code=201)
def create_request(
    body: RequestCreate,
    db: Session = Depends(get_db),
    client: User = Depends(require_roles("client")),
):
    request = DatasetRequest(
        client_id=client.id,
        task_name=body.task_name,
        episodes_requested=body.episodes_requested,
        deadline=body.deadline,
        notes=body.notes,
        status="submitted",
    )
    db.add(request)
    db.flush()  # gives the new request its id, without saving yet
    db.add(
        RequestStatusHistory(
            request_id=request.id, from_status=None, to_status="submitted", changed_by=client.id
        )
    )
    db.commit()  # request + first history row are saved together, or not at all
    return _load_detail(db, request.id, client)


@router.get("", response_model=list[RequestOut])
def list_requests(
    status: Status | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = _base_query()
    if user.role == "client":
        stmt = stmt.where(DatasetRequest.client_id == user.id)  # only their own
    if status:
        stmt = stmt.where(DatasetRequest.status == status)
    stmt = (
        stmt.order_by(DatasetRequest.created_at.desc(), DatasetRequest.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [_to_out(row, user) for row in db.execute(stmt).all()]


@router.get("/{request_id}", response_model=RequestDetailOut)
def get_request(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _load_detail(db, request_id, user)


@router.patch("/{request_id}/status", response_model=RequestDetailOut)
def change_status(
    request_id: int,
    body: StatusChange,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # FOR UPDATE locks this row until we commit. If two people change the same
    # request at the same moment, the second waits, then sees the NEW status.
    request = db.scalar(
        select(DatasetRequest).where(DatasetRequest.id == request_id).with_for_update()
    )
    if request is None or (user.role == "client" and request.client_id != user.id):
        raise HTTPException(status_code=404, detail="Request not found")

    allowed_roles = TRANSITIONS.get((request.status, body.status))
    if allowed_roles is None:
        raise HTTPException(
            status_code=409, detail=f"Cannot move a request from {request.status} to {body.status}"
        )
    if user.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Your role cannot make this change")

    if body.status == "delivered":
        assigned = db.scalar(
            select(func.count(Assignment.id)).where(Assignment.request_id == request.id)
        )
        if assigned < request.episodes_requested:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Cannot deliver: {assigned} episodes assigned, "
                    f"{request.episodes_requested} requested"
                ),
            )

    db.add(
        RequestStatusHistory(
            request_id=request.id,
            from_status=request.status,
            to_status=body.status,
            changed_by=user.id,
        )
    )
    request.status = body.status
    db.commit()  # status change + history row: one transaction
    return _load_detail(db, request_id, user)
