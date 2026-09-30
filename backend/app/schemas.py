"""Shapes of the data that goes IN and OUT of the API (the 'order forms')."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Role = Literal["client", "operator", "admin"]
Status = Literal["submitted", "in_progress", "delivered", "accepted", "rejected"]


class LoginIn(BaseModel):
    email: str
    password: str = Field(max_length=72)


class UserOut(BaseModel):
    """What we show about a user. Notice: no password_hash. Fields not listed here
    are never sent to the client, even though they exist in the database."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    organisation: str | None
    role: Role
    is_active: bool


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(min_length=1, max_length=255)
    organisation: str | None = Field(default=None, max_length=255)
    role: Role

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        if len(value.encode()) > 72:
            raise ValueError("password is too long (72 bytes maximum)")
        return value


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    role: Role | None = None
    is_active: bool | None = None


class RequestCreate(BaseModel):
    task_name: str = Field(min_length=1, max_length=255)
    episodes_requested: int = Field(gt=0, le=100_000)
    deadline: date
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("task_name")
    @classmethod
    def clean_task_name(cls, value: str) -> str:
        # Same style as the episodes ("pick cup"), so filters and matching just work.
        value = " ".join(value.split()).lower()
        if not value:
            raise ValueError("task_name must not be empty")
        return value

    @field_validator("deadline")
    @classmethod
    def deadline_not_in_the_past(cls, value: date) -> date:
        if value < date.today():
            raise ValueError("deadline must not be in the past")
        return value


class StatusChange(BaseModel):
    status: Status


class HistoryOut(BaseModel):
    from_status: str | None
    to_status: str
    changed_by_name: str
    changed_at: datetime


class RequestOut(BaseModel):
    id: int
    client_id: int
    client_name: str
    task_name: str
    episodes_requested: int
    episodes_assigned: int
    deadline: date
    notes: str | None
    status: Status
    created_at: datetime
    # The moves the CURRENT viewer may make. The UI shows its buttons from this list.
    allowed_next: list[Status]


class RequestDetailOut(RequestOut):
    history: list[HistoryOut]
