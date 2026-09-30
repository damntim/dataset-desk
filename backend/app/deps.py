"""Guards used by endpoints: 'who is this?' and 'are they allowed?'"""

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.security import decode_access_token

# auto_error=False: we raise our own 401, so every "not logged in" answer looks the same.
bearer = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    """Check the wristband and return the user. 401 if anything is wrong."""
    unauthorized = HTTPException(
        status_code=401,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise unauthorized

    # We reload the user from the database on every request, so a deactivated
    # user or a changed role takes effect immediately (not when the token expires).
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized

    request.state.user_id = user.id  # the logging middleware writes this in the log line
    return user


def require_roles(*roles: str):
    """Build a guard that only lets the given roles through. 403 for everyone else."""

    def guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="You do not have permission to do this")
        return user

    return guard
