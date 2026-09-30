"""Shapes of the data that goes IN and OUT of the API (the 'order forms')."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Role = Literal["client", "operator", "admin"]
Status = Literal["submitted", "in_progress", "delivered", "accepted", "rejected"]
Quality = Literal["good", "usable", "bad"]


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
    episodes_assigned: int  # counts toward delivery (the client's rejected ones are left out)
    episodes_rejected: int  # rejected by the client, still waiting to be swapped out
    operator_id: int | None  # first person who assigned episodes (see chat_rules.py)
    operator_name: str | None
    can_read_chat: bool
    can_write_chat: bool
    message_count: int
    unread_messages: int
    deadline: date
    notes: str | None
    status: Status
    created_at: datetime
    # The moves the CURRENT viewer may make. The UI shows its buttons from this list.
    allowed_next: list[Status]


class RequestDetailOut(RequestOut):
    history: list[HistoryOut]


class EpisodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    episode_id: str
    robot_id: str
    task_name: str
    recorded_at: datetime
    duration_seconds: int
    operator_name: str | None
    quality: Quality


class EpisodeListItem(EpisodeOut):
    assigned_request_id: int | None  # which request has it (empty = still free)


class EpisodePage(BaseModel):
    items: list[EpisodeListItem]
    total: int  # how many match the filters, across all pages
    limit: int
    offset: int


class RequestEpisodeOut(EpisodeOut):
    """An episode inside a request, with the client's verdict on it."""

    review_status: Literal["pending", "accepted", "rejected"]
    review_note: str | None


class ReviewIn(BaseModel):
    """The client's review of a delivery, episode by episode. Every episode NOT listed
    is kept (accepted).
    - rejected: not good enough -> the request goes back for rework (reason required)
    - returned: fine, but more than I asked for -> given back, free for other requests
    - extend: keep ALL the extra episodes by raising my request to match"""

    rejected_episode_ids: list[int] = Field(default_factory=list, max_length=100_000)
    returned_episode_ids: list[int] = Field(default_factory=list, max_length=100_000)
    reason: str | None = Field(default=None, max_length=2000)
    extend: bool = False

    @field_validator("reason")
    @classmethod
    def blank_is_none(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None


class MessageIn(BaseModel):
    body: str = Field(max_length=2000)

    @field_validator("body")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be empty")
        return value


class ReadIn(BaseModel):
    last_read_id: int = Field(ge=0)


class ChatSummaryOut(BaseModel):
    """One conversation in the floating chat list."""

    request_id: int
    task_name: str
    client_name: str
    status: Status
    operator_name: str | None
    can_write: bool
    unread: int
    last_body: str | None
    last_author: str | None
    last_at: datetime | None


class MessageOut(BaseModel):
    id: int
    author_id: int
    author_name: str
    author_role: Role
    body: str
    created_at: datetime


class AssignIn(BaseModel):
    episode_ids: list[int] = Field(min_length=1, max_length=500)  # database ids


class DailyRobotCount(BaseModel):
    day: date
    robot_id: str
    episodes: int


class RequestFulfilment(BaseModel):
    by_status: dict[str, int]  # every status is listed, with 0 when there are none
    total: int
    delivered_count: int  # requests that were delivered at least once (used for the median)
    median_seconds_to_deliver: float | None  # None when nothing was delivered


class TaskCount(BaseModel):
    task_name: str
    good_episodes: int


class AnalyticsOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    date_from: date = Field(alias="from")
    date_to: date = Field(alias="to")
    episodes_per_day: list[DailyRobotCount]
    requests: RequestFulfilment
    top_tasks_by_good_episodes: list[TaskCount]


class ReasonOut(BaseModel):
    code: str
    message: str


class SkippedRowOut(BaseModel):
    line: int
    episode_id: str | None
    reasons: list[ReasonOut]


class ExistingRowOut(BaseModel):
    line: int
    episode_id: str


class ImportReportOut(BaseModel):
    """imported + already_existed + skipped = total_rows"""

    total_rows: int
    imported: int
    already_existed: int
    skipped: int
    skipped_by_reason: dict[str, int]
    skipped_details: list[SkippedRowOut]
    already_existed_details: list[ExistingRowOut]
    details_truncated: bool
