from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, aliased

from app.chat_rules import chat_access
from app.db import get_db
from app.deps import get_current_user, require_roles
from app.models import (
    Assignment,
    DatasetRequest,
    MessageRead,
    RequestMessage,
    RequestStatusHistory,
    User,
)
from app.schemas import (
    HistoryOut,
    RequestCreate,
    RequestDetailOut,
    RequestOut,
    ReviewIn,
    Status,
    StatusChange,
)
from app.workflow import TRANSITIONS, next_statuses

router = APIRouter(prefix="/requests", tags=["requests"])


def _count(model, *conditions):
    """A per-request count, as a small sub-query inside the main query."""
    return (
        select(func.count(model.id))
        .where(model.request_id == DatasetRequest.id, *conditions)
        .correlate(DatasetRequest)
        .scalar_subquery()
    )


Operator = aliased(User)  # a second "copy" of users, for the request's operator


def request_rows_query(viewer: User):
    """Request + its client + its operator + episode counts + chat counts FOR THIS VIEWER."""
    assigned_here = (  # did the viewer assign any episode to this request?
        select(Assignment.id)
        .where(Assignment.request_id == DatasetRequest.id, Assignment.assigned_by == viewer.id)
        .correlate(DatasetRequest)
        .exists()
    )
    last_read = (
        select(MessageRead.last_read_id)
        .where(MessageRead.user_id == viewer.id, MessageRead.request_id == DatasetRequest.id)
        .correlate(DatasetRequest)
        .scalar_subquery()
    )
    unread = _count(  # messages from OTHER people, newer than what the viewer has read
        RequestMessage,
        RequestMessage.author_id != viewer.id,
        RequestMessage.id > func.coalesce(last_read, 0),
    )
    return (
        select(
            DatasetRequest,
            User,
            _count(Assignment, Assignment.review_status != "rejected").label("assigned"),
            _count(Assignment, Assignment.review_status == "rejected").label("rejected"),
            _count(RequestMessage).label("messages"),
            unread.label("unread"),
            Operator.name.label("operator_name"),
            assigned_here.label("assigned_here"),
        )
        .join(User, User.id == DatasetRequest.client_id)
        .outerjoin(Operator, Operator.id == DatasetRequest.operator_id)
    )


def counting_assignments(request_id: int) -> int:
    """Episodes that count toward delivery: everything except what the client rejected."""
    return select(func.count(Assignment.id)).where(
        Assignment.request_id == request_id, Assignment.review_status != "rejected"
    )


def request_out(row, viewer: User) -> dict:
    request, client, assigned, rejected, messages, unread, operator_name, assigned_here = row
    can_read, can_write = chat_access(
        viewer.role, viewer.id, request.client_id, assigned_here or request.operator_id == viewer.id
    )
    return {
        "id": request.id,
        "client_id": request.client_id,
        "client_name": client.organisation or client.name,
        "task_name": request.task_name,
        "episodes_requested": request.episodes_requested,
        "episodes_assigned": assigned,
        "episodes_rejected": rejected,
        "operator_id": request.operator_id,
        "operator_name": operator_name,
        "can_read_chat": can_read,
        "can_write_chat": can_write,
        "message_count": messages if can_read else 0,  # never leak a hidden chat
        "unread_messages": unread if can_read else 0,
        "deadline": request.deadline,
        "notes": request.notes,
        "status": request.status,
        "created_at": request.created_at,
        "allowed_next": next_statuses(request.status, viewer.role),
    }


def load_detail(db: Session, request_id: int, viewer: User) -> RequestDetailOut:
    """One request with its history. A client only ever sees their own: for anything
    else we answer 404, so we do not even reveal that the request exists."""
    stmt = request_rows_query(viewer).where(DatasetRequest.id == request_id)
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
    return RequestDetailOut(**request_out(row, viewer), history=history)


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
    return load_detail(db, request.id, client)


@router.get("", response_model=list[RequestOut])
def list_requests(
    status: Status | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = request_rows_query(user)
    if user.role == "client":
        stmt = stmt.where(DatasetRequest.client_id == user.id)  # only their own
    if status:
        stmt = stmt.where(DatasetRequest.status == status)
    stmt = (
        stmt.order_by(DatasetRequest.created_at.desc(), DatasetRequest.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [request_out(row, user) for row in db.execute(stmt).all()]


@router.get("/{request_id}", response_model=RequestDetailOut)
def get_request(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return load_detail(db, request_id, user)


def _lock_visible_request(db: Session, request_id: int, user: User) -> DatasetRequest:
    """Find the request and lock its row until we commit. If two people change the same
    request at the same moment, the second waits, then sees the NEW status."""
    request = db.scalar(
        select(DatasetRequest).where(DatasetRequest.id == request_id).with_for_update()
    )
    if request is None or (user.role == "client" and request.client_id != user.id):
        raise HTTPException(status_code=404, detail="Request not found")
    return request


def _check_move(db: Session, request: DatasetRequest, target: str, user: User) -> None:
    """Every rule about moving a request, in one place. Raises the right HTTP error."""
    allowed_roles = TRANSITIONS.get((request.status, target))
    if allowed_roles is None:
        raise HTTPException(
            status_code=409, detail=f"Cannot move a request from {request.status} to {target}"
        )
    if user.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Your role cannot make this change")

    if target == "delivered":
        assigned = db.scalar(counting_assignments(request.id))
        if assigned < request.episodes_requested:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Cannot deliver: {assigned} episodes assigned, "
                    f"{request.episodes_requested} requested"
                ),
            )


def _record_move(db: Session, request: DatasetRequest, target: str, user: User) -> None:
    db.add(
        RequestStatusHistory(
            request_id=request.id, from_status=request.status, to_status=target, changed_by=user.id
        )
    )
    request.status = target


def _review_pending(db: Session, request_id: int, verdict: str, note: str | None = None, only=None):
    """Give the not-yet-reviewed episodes of a request a verdict ('accepted'/'rejected').
    `only`: limit to these episode ids."""
    statement = (
        update(Assignment)
        .where(Assignment.request_id == request_id, Assignment.review_status == "pending")
        .values(review_status=verdict, review_note=note, reviewed_at=datetime.now(timezone.utc))
    )
    if only is not None:
        statement = statement.where(Assignment.episode_id.in_(only))
    db.execute(statement)


@router.patch("/{request_id}/status", response_model=RequestDetailOut)
def change_status(
    request_id: int,
    body: StatusChange,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    request = _lock_visible_request(db, request_id, user)
    _check_move(db, request, body.status, user)

    if body.status == "accepted":
        kept = db.scalar(counting_assignments(request.id))
        if kept > request.episodes_requested:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"This delivery has {kept} episodes but you requested "
                    f"{request.episodes_requested}. Review it to choose which to keep, "
                    "or extend your request."
                ),
            )

    # A whole-delivery decision is the same as reviewing every episode the same way.
    if body.status in ("accepted", "rejected"):
        _review_pending(db, request.id, body.status)

    _record_move(db, request, body.status, user)
    db.commit()  # status change + history row (+ episode verdicts): one transaction
    return load_detail(db, request_id, user)


@router.post("/{request_id}/review", response_model=RequestDetailOut)
def review_delivery(
    request_id: int,
    body: ReviewIn,
    db: Session = Depends(get_db),
    client: User = Depends(require_roles("client")),
):
    """The client reviews a delivery episode by episode (see ReviewIn).
    Nothing rejected -> the request is accepted, and the client must end up keeping exactly
    what they asked for: return the extras, or extend the request to keep them all.
    Something rejected -> the request goes back to the operators for rework."""
    request = _lock_visible_request(db, request_id, client)
    rejected = set(body.rejected_episode_ids)
    returned = set(body.returned_episode_ids)
    target = "rejected" if rejected else "accepted"
    _check_move(db, request, target, client)

    if rejected & returned:
        raise HTTPException(status_code=422, detail="An episode cannot be both rejected and returned")
    if rejected and not body.reason:
        raise HTTPException(status_code=422, detail="Please give a reason for rejecting episodes")
    if rejected and body.extend:
        raise HTTPException(status_code=422, detail="You can only extend a request when accepting")

    statuses = dict(
        db.execute(
            select(Assignment.episode_id, Assignment.review_status).where(
                Assignment.request_id == request.id, Assignment.review_status != "rejected"
            )
        ).all()
    )
    pending = {episode for episode, status in statuses.items() if status == "pending"}
    not_in_delivery = sorted((rejected | returned) - pending)
    if not_in_delivery:
        raise HTTPException(
            status_code=409,
            detail=f"These episodes are not waiting for your review in this delivery: {not_in_delivery[:10]}",
        )

    if target == "accepted":
        kept = len(statuses) - len(returned)  # earlier accepted + pending, minus given back
        wanted = request.episodes_requested
        if kept < wanted:
            raise HTTPException(
                status_code=409,
                detail=f"You requested {wanted} episodes; keep at least {wanted}, "
                "or reject some to get replacements",
            )
        if kept > wanted and not body.extend:
            raise HTTPException(
                status_code=409,
                detail=f"You are keeping {kept} episodes but requested {wanted}. "
                f"Return {kept - wanted}, or extend your request to {kept}.",
            )
        if kept > wanted:
            # Keep an audit trail in the conversation: who raised the request, from what, to what.
            db.add(
                RequestMessage(
                    request_id=request.id,
                    author_id=client.id,
                    body=f"Extended this request from {wanted} to {kept} episodes to keep the extra ones.",
                )
            )
            request.episodes_requested = kept

    if returned:  # given back: the episodes become free for other requests
        db.execute(
            delete(Assignment).where(
                Assignment.request_id == request.id, Assignment.episode_id.in_(returned)
            )
        )
    if rejected:
        _review_pending(db, request.id, "rejected", body.reason, only=rejected)
    _review_pending(db, request.id, "accepted")  # everything else that was waiting
    _record_move(db, request, target, client)
    db.commit()  # all verdicts, returns, the extension and the status change together
    return load_detail(db, request_id, client)
