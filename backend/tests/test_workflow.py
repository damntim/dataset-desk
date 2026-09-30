"""The transition table itself: pure rules, no database, no web."""

from app.workflow import TRANSITIONS, next_statuses

ALL = ["submitted", "in_progress", "delivered", "accepted", "rejected"]


def test_exactly_five_moves_exist():
    assert set(TRANSITIONS) == {
        ("submitted", "in_progress"),
        ("in_progress", "delivered"),
        ("delivered", "accepted"),
        ("delivered", "rejected"),
        ("rejected", "in_progress"),
    }


def test_only_clients_can_accept_or_reject():
    assert TRANSITIONS[("delivered", "accepted")] == {"client"}
    assert TRANSITIONS[("delivered", "rejected")] == {"client"}


def test_every_other_move_belongs_to_operators_and_admins():
    for move, roles in TRANSITIONS.items():
        if move[0] != "delivered":
            assert roles == {"operator", "admin"}


def test_accepted_is_the_end_of_the_road():
    assert all(frm != "accepted" for frm, _ in TRANSITIONS)


def test_next_statuses_depends_on_role():
    assert next_statuses("delivered", "client") == ["accepted", "rejected"]
    assert next_statuses("delivered", "operator") == []
    assert next_statuses("submitted", "operator") == ["in_progress"]
    assert next_statuses("submitted", "client") == []
    assert next_statuses("accepted", "admin") == []
