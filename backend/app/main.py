import logging
import time

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.logging_config import setup_logging
from app.routers import auth, users

setup_logging()
log = logging.getLogger("app.request")

app = FastAPI(title="Dataset Request Desk")
app.include_router(auth.router)
app.include_router(users.router)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Runs around EVERY request and writes one log line when it finishes."""
    start = time.perf_counter()
    request.state.user_id = None  # the login code (Phase 3) will fill this in
    status = 500  # if the code crashes, this is what we report
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        log.info(
            "request",
            extra={
                "fields": {
                    "method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                    "user_id": request.state.user_id,
                }
            },
        )


@app.get("/health")
def health(db: Session = Depends(get_db)):
    """Is the app alive, and can it reach the database?"""
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "degraded", "db": "down"})
    return {"status": "ok", "db": "up"}
