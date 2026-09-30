"""Chat on a request, between its client and the operators who assigned its episodes.
Who may read and write: see app/chat_rules.py."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exists, func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on, insert
from sqlalchemy.orm import Session

from app.chat_rules import chat_access
from app.db import get_db
from app.deps import get_current_user
from app.models import Assignment, DatasetRequest, MessageRead, RequestMessage, User
from app.routers.requests import request_out, request_rows_query
from app.schemas import ChatSummaryOut, MessageIn, MessageOut, ReadIn

router = APIRouter(tags=["chat"])


def _access(db: Session, request_id: int, user: User) -> tuple[bool, bool]:
    """(can_read, can_write) for this user on this request. 404 if they cannot see the request."""
    request = db.get(DatasetRequest, request_id)
    if request is None or (user.role == "client" and request.client_id != user.id):
        raise HTTPException(status_code=404, detail="Request not found")
    assigned_here = request.operator_id == user.id or db.scalar(
        select(exists().where(Assignment.request_id == request_id, Assignment.assigned_by == user.id))
    )
    return chat_access(user.role, user.id, request.client_id, bool(assigned_here))


def _display_name(user: User) -> str:
    """A client shows as their organisation; staff show as their own name."""
    return user.organisation if user.role == "client" and user.organisation else user.name


def _messages(db: Session, request_id: int, after_id: int = 0) -> list[MessageOut]:
    rows = db.execute(
        select(RequestMessage, User)
        .join(User, User.id == RequestMessage.author_id)
        .where(RequestMessage.request_id == request_id, RequestMessage.id > after_id)
        .order_by(RequestMessage.id)
        .limit(500)
    ).all()
    return [
        MessageOut(
            id=m.id,
            author_id=m.author_id,
            author_name=_display_name(author),
            author_role=author.role,
            body=m.body,
            created_at=m.created_at,
        )
        for m, author in rows
    ]


@router.get("/requests/{request_id}/messages", response_model=list[MessageOut])
def list_messages(
    request_id: int,
    after_id: int = Query(0, ge=0, description="Only messages newer than this id (for polling)"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    can_read, _ = _access(db, request_id, user)
    if not can_read:
        raise HTTPException(
            status_code=403,
            detail="Only the operators who assigned episodes to this request can see its chat",
        )
    return _messages(db, request_id, after_id)


@router.post("/requests/{request_id}/messages", response_model=MessageOut, status_code=201)
def send_message(
    request_id: int,
    body: MessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _, can_write = _access(db, request_id, user)
    if not can_write:
        raise HTTPException(
            status_code=403,
            detail="You can read this chat, but only the client and the operators on this request can reply",
        )
    message = RequestMessage(request_id=request_id, author_id=user.id, body=body.body)
    db.add(message)
    db.flush()
    _mark_read(db, user.id, request_id, message.id)  # your own message is read by you
    db.commit()
    return _messages(db, request_id, message.id - 1)[0]


def _mark_read(db: Session, user_id: int, request_id: int, last_id: int) -> None:
    """Remember how far this user has read. Never moves backwards (GREATEST)."""
    statement = insert(MessageRead).values(user_id=user_id, request_id=request_id, last_read_id=last_id)
    db.execute(
        statement.on_conflict_do_update(
            index_elements=["user_id", "request_id"],
            set_={"last_read_id": func.greatest(MessageRead.last_read_id, statement.excluded.last_read_id)},
        )
    )


@router.post("/requests/{request_id}/messages/read", status_code=204)
def mark_read(
    request_id: int,
    body: ReadIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    can_read, _ = _access(db, request_id, user)
    if not can_read:
        raise HTTPException(status_code=403, detail="You cannot see this chat")
    _mark_read(db, user.id, request_id, body.last_read_id)
    db.commit()


@router.get("/chats", response_model=list[ChatSummaryOut])
def my_chats(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """The conversations for the floating chat: the ones this user can read, newest first."""
    query = request_rows_query(user)
    if user.role == "client":
        query = query.where(DatasetRequest.client_id == user.id)
    elif user.role == "operator":
        mine = (
            select(Assignment.id)
            .where(Assignment.request_id == DatasetRequest.id, Assignment.assigned_by == user.id)
            .correlate(DatasetRequest)
            .exists()
        )
        query = query.where(or_(DatasetRequest.operator_id == user.id, mine))
    rows = [request_out(row, user) for row in db.execute(query.limit(200)).all()]
    # Admins see every chat, but only the ones that have messages (or that they run).
    rows = [
        r
        for r in rows
        if r["can_read_chat"] and (user.role != "admin" or r["message_count"] or r["can_write_chat"])
    ]

    # The last message of each conversation, in one query.
    last = {}
    if rows:
        for message, author in db.execute(
            select(RequestMessage, User)
            .join(User, User.id == RequestMessage.author_id)
            .where(RequestMessage.request_id.in_([r["id"] for r in rows]))
            .ext(distinct_on(RequestMessage.request_id))  # one row per conversation: the newest
            .order_by(RequestMessage.request_id, RequestMessage.id.desc())
        ).all():
            last[message.request_id] = (message, author)

    chats = []
    for r in rows:
        message, author = last.get(r["id"], (None, None))
        chats.append(
            ChatSummaryOut(
                request_id=r["id"],
                task_name=r["task_name"],
                client_name=r["client_name"],
                status=r["status"],
                operator_name=r["operator_name"],
                can_write=r["can_write_chat"],
                unread=r["unread_messages"],
                last_body=message.body[:120] if message else None,
                last_author=_display_name(author) if author else None,
                last_at=message.created_at if message else None,
            )
        )
    # Unread first, then most recent conversation, then newest request.
    chats.sort(key=lambda c: (c.unread == 0, -(c.last_at.timestamp() if c.last_at else 0), -c.request_id))
    return chats
