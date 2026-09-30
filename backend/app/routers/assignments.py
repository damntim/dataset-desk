"""Giving episodes to a request (and taking them back)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_roles
from app.models import Assignment, DatasetRequest, Episode, User
from app.routers.requests import load_detail
from app.schemas import AssignIn, EpisodeOut, RequestDetailOut, RequestEpisodeOut
from app.workflow import ASSIGNABLE_QUALITIES

router = APIRouter(prefix="/requests", tags=["assignments"])


def _few(items: list) -> str:
    """Show at most 10 items in an error message."""
    shown = ", ".join(str(item) for item in items[:10])
    return shown + (f" (and {len(items) - 10} more)" if len(items) > 10 else "")


def _lock_in_progress_request(db: Session, request_id: int) -> DatasetRequest:
    """Find the request and lock it until we commit. Locking means nobody can change its
    status (say, to 'delivered') while we are adding or removing episodes."""
    request = db.scalar(
        select(DatasetRequest).where(DatasetRequest.id == request_id).with_for_update()
    )
    if request is None:
        raise HTTPException(status_code=404, detail="Request not found")
    if request.status != "in_progress":
        raise HTTPException(
            status_code=409,
            detail=f"Episodes can only be changed while the request is in_progress "
            f"(it is {request.status})",
        )
    return request


@router.post("/{request_id}/assignments", response_model=RequestDetailOut)
def assign_episodes(
    request_id: int,
    body: AssignIn,
    db: Session = Depends(get_db),
    staff: User = Depends(require_roles("operator", "admin")),
):
    request = _lock_in_progress_request(db, request_id)
    ids = list(dict.fromkeys(body.episode_ids))  # same id twice counts once

    episodes = db.scalars(select(Episode).where(Episode.id.in_(ids))).all()
    found = {episode.id for episode in episodes}
    missing = [i for i in ids if i not in found]
    if missing:
        raise HTTPException(status_code=404, detail=f"Episodes not found: {_few(missing)}")

    unusable = [e.episode_id for e in episodes if e.quality not in ASSIGNABLE_QUALITIES]
    if unusable:
        raise HTTPException(
            status_code=409,
            detail=f"Only good or usable episodes can be assigned. Not allowed: {_few(unusable)}",
        )

    taken = db.execute(
        select(Episode.episode_id, Assignment.request_id)
        .join(Assignment, Assignment.episode_id == Episode.id)
        .where(Episode.id.in_(ids))
    ).all()
    if taken:
        listing = [f"{episode_id} (request {req})" for episode_id, req in taken]
        raise HTTPException(
            status_code=409, detail=f"Already assigned: {_few(listing)}. Nothing was assigned."
        )

    db.add_all(
        Assignment(request_id=request.id, episode_id=i, assigned_by=staff.id) for i in ids
    )
    if request.operator_id is None:
        request.operator_id = staff.id  # the first person to assign episodes runs this request
    try:
        db.commit()
    except IntegrityError:
        # Someone else took one of them between our check and our save. The UNIQUE
        # constraint on assignments.episode_id is the final guard, and it just did its job.
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="One of these episodes was just assigned elsewhere. Nothing was assigned.",
        )
    return load_detail(db, request_id, staff)


@router.delete("/{request_id}/assignments/{episode_pk}", response_model=RequestDetailOut)
def unassign_episode(
    request_id: int,
    episode_pk: int,
    db: Session = Depends(get_db),
    staff: User = Depends(require_roles("operator", "admin")),
):
    _lock_in_progress_request(db, request_id)
    assignment = db.scalar(
        select(Assignment).where(
            Assignment.request_id == request_id, Assignment.episode_id == episode_pk
        )
    )
    if assignment is None:
        raise HTTPException(status_code=404, detail="This episode is not assigned to this request")
    if assignment.review_status == "accepted":
        # The client already approved it in an earlier delivery: it is part of their dataset.
        raise HTTPException(
            status_code=409, detail="The client already accepted this episode; it cannot be removed"
        )
    db.delete(assignment)
    db.commit()
    return load_detail(db, request_id, staff)


@router.get("/{request_id}/episodes", response_model=list[RequestEpisodeOut])
def request_episodes(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """The episodes given to a request. A client can see them for their own request only:
    this is what they review before they accept or reject the delivery."""
    visible = select(DatasetRequest.id).where(DatasetRequest.id == request_id)
    if user.role == "client":
        visible = visible.where(DatasetRequest.client_id == user.id)
    if db.scalar(visible) is None:
        raise HTTPException(status_code=404, detail="Request not found")

    rows = db.execute(
        select(Episode, Assignment.review_status, Assignment.review_note)
        .join(Assignment, Assignment.episode_id == Episode.id)
        .where(Assignment.request_id == request_id)
        .order_by(Episode.id)
    ).all()
    return [
        RequestEpisodeOut(
            **EpisodeOut.model_validate(episode).model_dump(),
            review_status=status,
            review_note=note,
        )
        for episode, status, note in rows
    ]
