"""Shapes of the data that goes IN and OUT of the API (the 'order forms')."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Role = Literal["client", "operator", "admin"]


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
