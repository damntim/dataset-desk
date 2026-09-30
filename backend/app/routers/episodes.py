from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_roles
from app.importer import ImportFileError, decode_file, import_episodes
from app.models import User
from app.schemas import ImportReportOut

router = APIRouter(prefix="/episodes", tags=["episodes"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # ~25 MB. 200,000 episodes is about 12 MB.


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
        raise HTTPException(status_code=400, detail=str(exc))
