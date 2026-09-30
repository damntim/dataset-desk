"""Who may read and write a request's chat. One small pure function, easy to test.

The operators on a request are the people who assigned its episodes (videos):
the first one (saved as requests.operator_id) and anyone else with episodes assigned there.

| Person                                   | Read | Write |
|------------------------------------------|------|-------|
| the client who owns the request          | yes  | yes   |
| an operator/admin who assigned episodes  | yes  | yes   |
| an admin who did not                     | yes  | no    |  (oversight, read only)
| any other operator                       | no   | no    |
| another client                           | (the request itself is hidden: 404)
"""


def chat_access(role: str, user_id: int, client_id: int, assigned_episodes: bool) -> tuple[bool, bool]:
    """Return (can_read, can_write). `assigned_episodes`: this user assigned episodes here."""
    if role == "client":
        mine = user_id == client_id
        return mine, mine
    if assigned_episodes:
        return True, True
    if role == "admin":
        return True, False
    return False, False
