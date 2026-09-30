from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_roles
from app.importer import ImportFileError, decode_file, import_episodes
from app.models import Assignment, Episode, User
from app.schemas import EpisodeListItem, EpisodeOut, EpisodePage, ImportReportOut, Quality

router = APIRouter(prefix="/episodes", tags=["episodes"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # ~25 MB. 200,000 episodes is about 12 MB.


@router.get("", response_model=EpisodePage)
def list_episodes(
    task_name: str | None = None,
    quality: Quality | None = None,
    unassigned: bool = False,
    request_id: int | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _staff: User = Depends(require_roles("operator", "admin")),
):
    """Browse episodes, one page at a time. Filters combine (AND)."""
    filters = []
    if task_name:
        filters.append(Episode.task_name == " ".join(task_name.split()).lower())
    if quality:
        filters.append(Episode.quality == quality)
    if unassigned:
        filters.append(Assignment.request_id.is_(None))  # no assignment row = still free
    if request_id is not None:
        filters.append(Assignment.request_id == request_id)

    matching = (
        select(Episode, Assignment.request_id)
        .outerjoin(Assignment, Assignment.episode_id == Episode.id)
        .where(*filters)
    )
    total = db.scalar(select(func.count()).select_from(matching.subquery()))
    rows = db.execute(matching.order_by(Episode.id).limit(limit).offset(offset)).all()

    items = [
        EpisodeListItem(**EpisodeOut.model_validate(ep).model_dump(), assigned_request_id=req_id)
        for ep, req_id in rows
    ]
    return EpisodePage(items=items, total=total, limit=limit, offset=offset)


@router.get("/task-names", response_model=list[str])
def task_names(
    db: Session = Depends(get_db),
    _staff: User = Depends(require_roles("operator", "admin")),
):
    """Every task name that exists, for the filter drop-down."""
    return db.scalars(select(Episode.task_name).distinct().order_by(Episode.task_name)).all()


@router.post("/import", response_model=ImportReportOut)
def import_csv(
    file: UploadFile,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_roles("operator", "admin")),
):
    """Upload the CSV export. Safe to send the same file again: nothing is duplicated."""
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is too large (limit 25 MB)")
    try:
        return import_episodes(db, decode_file(data))
    except ImportFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
