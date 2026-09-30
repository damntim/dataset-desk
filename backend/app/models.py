from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

ROLES = ("client", "operator", "admin")
QUALITIES = ("good", "usable", "bad")
STATUSES = ("submitted", "in_progress", "delivered", "accepted", "rejected")
# The client's verdict on ONE delivered episode. "pending" = not reviewed yet.
REVIEW_STATUSES = ("pending", "accepted", "rejected")


def _one_of(column: str, values: tuple[str, ...]) -> str:
    """Build the SQL text  column IN ('a','b','c')  for a CHECK constraint."""
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_one_of("role", ROLES), name="ck_users_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    organisation: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Episode(Base):
    __tablename__ = "episodes"
    __table_args__ = (
        CheckConstraint(_one_of("quality", QUALITIES), name="ck_episodes_quality"),
        CheckConstraint("duration_seconds > 0", name="ck_episodes_duration_positive"),
        # These two indexes make the analytics and the episode filters fast.
        Index("ix_episodes_recorded_at_robot_id", "recorded_at", "robot_id"),
        Index("ix_episodes_quality_task_name", "quality", "task_name"),
        # For "top tasks by good episodes in a date range": the index alone holds everything
        # the query needs (quality, recorded_at, task_name), so PostgreSQL never opens the
        # table. Measured with 200k rows: 17 ms -> 5.6 ms for a 30-day range.
        Index("ix_episodes_quality_recorded_at", "quality", "recorded_at",
              postgresql_include=["task_name"]),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # The id from the recording system, e.g. "EP-00156". UNIQUE = no duplicates,
    # which is what makes the CSV import safe to run twice.
    episode_id: Mapped[str] = mapped_column(String(50), unique=True)
    robot_id: Mapped[str] = mapped_column(String(50))
    task_name: Mapped[str] = mapped_column(String(255))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int]
    operator_name: Mapped[str | None] = mapped_column(String(255))
    quality: Mapped[str] = mapped_column(String(10))


class DatasetRequest(Base):
    __tablename__ = "requests"
    __table_args__ = (
        CheckConstraint(_one_of("status", STATUSES), name="ck_requests_status"),
        CheckConstraint("episodes_requested > 0", name="ck_requests_count_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    task_name: Mapped[str] = mapped_column(String(255))
    episodes_requested: Mapped[int]
    deadline: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), default="submitted", server_default="submitted"
    )
    # The operator of this request: whoever FIRST assigned episodes to it (kept even if
    # those episodes are swapped later). Empty until then. Used for the chat rules.
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RequestStatusHistory(Base):
    """One row every time a request changes status: who did it, and when."""

    __tablename__ = "request_status_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(20))  # empty for the first row
    to_status: Mapped[str] = mapped_column(String(20))
    changed_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Assignment(Base):
    """An episode given to a request, and the client's verdict on it."""

    __tablename__ = "assignments"
    __table_args__ = (
        CheckConstraint(_one_of("review_status", REVIEW_STATUSES), name="ck_assignments_review_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), index=True)
    # UNIQUE: an episode can belong to at most ONE request. The database enforces it.
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id"), unique=True)
    assigned_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    review_status: Mapped[str] = mapped_column(
        String(10), default="pending", server_default="pending"
    )
    review_note: Mapped[str | None] = mapped_column(Text)  # why the client rejected it
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MessageRead(Base):
    """How far one person has read one request's chat (for unread counts)."""

    __tablename__ = "message_reads"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), primary_key=True)
    last_read_id: Mapped[int] = mapped_column(default=0)


class RequestMessage(Base):
    """One chat message on a request, between its client and the operators."""

    __tablename__ = "request_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    # index: messages are always read per request, oldest first
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
