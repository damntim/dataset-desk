from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import LoginIn, TokenOut, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

# Used when the email does not exist, so we still spend the same time on bcrypt.
# Otherwise a fast answer would tell an attacker "this email is not registered".
DUMMY_HASH = hash_password("not-a-real-password")


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    password_ok = verify_password(body.password, user.password_hash if user else DUMMY_HASH)

    # One message for every failure: never reveal WHICH part was wrong.
    if user is None or not password_ok or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return TokenOut(access_token=create_access_token(user.id), user=user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
