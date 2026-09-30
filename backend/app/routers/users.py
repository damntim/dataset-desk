"""User management: admin only."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_roles
from app.models import User
from app.schemas import UserCreate, UserOut, UserUpdate
from app.security import hash_password

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles("admin")),
):
    return db.scalars(select(User).order_by(User.id)).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles("admin")),
):
    user = User(
        email=str(body.email).lower(),
        password_hash=hash_password(body.password),
        name=body.name,
        organisation=body.organisation,
        role=body.role,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # The UNIQUE constraint on email is the real guard, even if two admins
        # create the same email at the same second.
        db.rollback()
        raise HTTPException(status_code=409, detail="A user with this email already exists")
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("admin")),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    changes = body.model_dump(exclude_none=True)

    # Stop an admin from locking themselves out.
    if user.id == admin.id and (
        changes.get("role", user.role) != "admin" or changes.get("is_active") is False
    ):
        raise HTTPException(status_code=400, detail="You cannot demote or deactivate yourself")

    for field, value in changes.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user
