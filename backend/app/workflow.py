"""The life of a request: which status moves are allowed, and by which roles.

Plain data and one tiny function. No database, no web code, so it is easy to read and test.
"""

# Only episodes of these qualities may be given to a request.
ASSIGNABLE_QUALITIES = ("good", "usable")

OPERATORS = {"operator", "admin"}
CLIENTS = {"client"}

# (from_status, to_status) -> roles allowed to do this step.
TRANSITIONS: dict[tuple[str, str], set[str]] = {
    ("submitted", "in_progress"): OPERATORS,
    ("in_progress", "delivered"): OPERATORS,
    ("delivered", "accepted"): CLIENTS,
    ("delivered", "rejected"): CLIENTS,
    ("rejected", "in_progress"): OPERATORS,  # rework
}


def next_statuses(current: str, role: str) -> list[str]:
    """Which statuses this role could move a request to from `current`.
    The frontend uses this to show the right buttons."""
    return [to for (frm, to), roles in TRANSITIONS.items() if frm == current and role in roles]
