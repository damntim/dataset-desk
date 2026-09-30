"""Chat rules: the client and the operators who assigned episodes talk; admins read along;
other operators see nothing. Plus unread counts and the floating chat list."""
import pytest

from app.chat_rules import chat_access


# ---------------------------------------------------------------- the rule table itself


@pytest.mark.parametrize(
    "role,user_id,assigned,expected",
    [
        ("client", 10, False, (True, True)),  # the owner
        ("client", 11, False, (False, False)),  # another client
        ("operator", 20, True, (True, True)),  # assigned episodes here
        ("operator", 20, False, (False, False)),  # did not
        ("admin", 30, True, (True, True)),  # admin who assigned episodes here
        ("admin", 30, False, (True, False)),  # admin: read only
    ],
)
def test_chat_access_table(role, user_id, assigned, expected):
    assert chat_access(role, user_id, client_id=10, assigned_episodes=assigned) == expected


# ---------------------------------------------------------------- through the API


@pytest.fixture
def team(users, make_user):
    return {**users, "other_operator": make_user("other-op@test.com", "operator")}


@pytest.fixture
def running(client, team, login_as, make_request, make_episodes):
    """Client A's request, with episodes assigned by `operator`."""
    request_id = make_request(owner="client_a")
    staff = login_as(team["operator"])
    client.post(f"/requests/{request_id}/assignments", json={"episode_ids": make_episodes(1)}, headers=staff)
    return request_id


def post(client, headers, request_id, text):
    return client.post(f"/requests/{request_id}/messages", json={"body": text}, headers=headers)


def read(client, headers, request_id):
    return client.get(f"/requests/{request_id}/messages", headers=headers)


def test_client_and_the_assigning_operator_talk(client, team, login_as, running):
    owner, staff = login_as(team["client_a"]), login_as(team["operator"])

    first = post(client, owner, running, "  Please prefer arm robots  ")
    second = post(client, staff, running, "Will do.")

    assert first.status_code == second.status_code == 201
    assert first.json()["body"] == "Please prefer arm robots"
    assert first.json()["author_name"] == "Acme"  # a client shows as their organisation
    assert [m["body"] for m in read(client, owner, running).json()] == ["Please prefer arm robots", "Will do."]


def test_the_first_assigner_becomes_the_operator_of_the_request(client, team, login_as, running):
    body = client.get(f"/requests/{running}", headers=login_as(team["client_a"])).json()
    assert (body["operator_id"], body["operator_name"]) == (team["operator"].id, "operator")


def test_the_operator_keeps_access_after_their_episodes_are_removed(client, team, login_as, running):
    staff = login_as(team["operator"])
    (episode,) = [e["id"] for e in client.get(f"/requests/{running}/episodes", headers=staff).json()]
    client.delete(f"/requests/{running}/assignments/{episode}", headers=staff)
    assert post(client, staff, running, "still here").status_code == 201


def test_a_second_operator_who_also_assigns_can_join(client, team, login_as, running, make_episodes):
    other = login_as(team["other_operator"])
    assert read(client, other, running).status_code == 403
    client.post(f"/requests/{running}/assignments", json={"episode_ids": make_episodes(1)}, headers=other)
    assert read(client, other, running).status_code == 200
    assert post(client, other, running, "helping out").status_code == 201


def test_other_operators_cannot_see_or_write(client, team, login_as, running):
    other = login_as(team["other_operator"])
    assert read(client, other, running).status_code == 403
    assert post(client, other, running, "hi").status_code == 403
    listed = client.get(f"/requests/{running}", headers=other).json()
    assert (listed["can_read_chat"], listed["message_count"]) == (False, 0)  # nothing leaks


def test_admin_reads_everything_but_cannot_reply_unless_they_assigned(
    client, team, login_as, running, make_request, make_episodes
):
    admin = login_as(team["admin"])
    post(client, login_as(team["client_a"]), running, "hello")
    assert [m["body"] for m in read(client, admin, running).json()] == ["hello"]
    refused = post(client, admin, running, "admin here")
    assert refused.status_code == 403

    own = make_request(owner="client_b")
    client.post(f"/requests/{own}/assignments", json={"episode_ids": make_episodes(1)}, headers=admin)
    assert post(client, admin, own, "I am running this one").status_code == 201


def test_before_anyone_assigns_only_the_client_and_admins_can_see(client, team, login_as, make_request):
    request_id = make_request(owner="client_a", status="submitted")
    assert post(client, login_as(team["client_a"]), request_id, "any news?").status_code == 201
    assert read(client, login_as(team["operator"]), request_id).status_code == 403
    assert read(client, login_as(team["admin"]), request_id).status_code == 200


def test_other_clients_get_404_and_anonymous_401(client, team, login_as, running):
    assert read(client, login_as(team["client_b"]), running).status_code == 404
    assert post(client, login_as(team["client_b"]), running, "hi").status_code == 404
    assert client.get(f"/requests/{running}/messages").status_code == 401


@pytest.mark.parametrize("text", ["", "    ", "x" * 2001])
def test_empty_or_huge_messages_are_422(client, team, login_as, running, text):
    assert post(client, login_as(team["client_a"]), running, text).status_code == 422


def test_polling_returns_only_newer_messages(client, team, login_as, running):
    owner = login_as(team["client_a"])
    first_id = post(client, owner, running, "one").json()["id"]
    post(client, owner, running, "two")
    newer = client.get(f"/requests/{running}/messages?after_id={first_id}", headers=owner).json()
    assert [m["body"] for m in newer] == ["two"]


# ---------------------------------------------------------------- unread counts


def unread(client, headers, request_id):
    return client.get(f"/requests/{request_id}", headers=headers).json()["unread_messages"]


def test_unread_counts_other_peoples_messages_until_marked_read(client, team, login_as, running):
    owner, staff = login_as(team["client_a"]), login_as(team["operator"])
    post(client, owner, running, "one")
    last = post(client, owner, running, "two").json()["id"]

    assert unread(client, owner, running) == 0  # my own messages are never unread
    assert unread(client, staff, running) == 2

    marked = client.post(f"/requests/{running}/messages/read", json={"last_read_id": last}, headers=staff)
    assert marked.status_code == 204
    assert unread(client, staff, running) == 0

    post(client, owner, running, "three")
    assert unread(client, staff, running) == 1


def test_read_marker_never_moves_backwards(client, team, login_as, running):
    owner, staff = login_as(team["client_a"]), login_as(team["operator"])
    ids = [post(client, owner, running, t).json()["id"] for t in ("a", "b")]
    client.post(f"/requests/{running}/messages/read", json={"last_read_id": ids[1]}, headers=staff)
    client.post(f"/requests/{running}/messages/read", json={"last_read_id": ids[0]}, headers=staff)
    assert unread(client, staff, running) == 0


def test_replying_marks_the_thread_read_for_me(client, team, login_as, running):
    owner, staff = login_as(team["client_a"]), login_as(team["operator"])
    post(client, owner, running, "question?")
    post(client, staff, running, "answer.")
    assert unread(client, staff, running) == 0
    assert unread(client, owner, running) == 1


def test_cannot_mark_read_a_chat_you_cannot_see(client, team, login_as, running):
    other = login_as(team["other_operator"])
    response = client.post(f"/requests/{running}/messages/read", json={"last_read_id": 1}, headers=other)
    assert response.status_code == 403


# ---------------------------------------------------------------- the floating chat list


def chats(client, headers):
    response = client.get("/chats", headers=headers)
    assert response.status_code == 200
    return response.json()


def test_chat_list_shows_the_right_conversations_to_each_person(
    client, team, login_as, running, make_request
):
    other_request = make_request(owner="client_b")
    post(client, login_as(team["client_b"]), other_request, "from Beta")
    post(client, login_as(team["client_a"]), running, "from Acme")

    assert [c["request_id"] for c in chats(client, login_as(team["client_a"]))] == [running]
    assert [c["request_id"] for c in chats(client, login_as(team["operator"]))] == [running]
    assert chats(client, login_as(team["other_operator"])) == []
    admin_view = {c["request_id"]: c["can_write"] for c in chats(client, login_as(team["admin"]))}
    assert admin_view == {running: False, other_request: False}  # read only, both have messages


def test_chat_list_puts_unread_first_and_shows_the_last_message(
    client, team, login_as, running, make_request, make_episodes
):
    staff = login_as(team["operator"])
    quiet = make_request(owner="client_b")
    client.post(f"/requests/{quiet}/assignments", json={"episode_ids": make_episodes(1)}, headers=staff)
    post(client, staff, quiet, "I wrote last here")
    post(client, login_as(team["client_a"]), running, "Hello, any update?")

    listed = chats(client, staff)
    assert [c["request_id"] for c in listed] == [running, quiet]
    assert (listed[0]["unread"], listed[0]["last_body"], listed[0]["last_author"]) == (1, "Hello, any update?", "Acme")
    assert listed[1]["unread"] == 0
