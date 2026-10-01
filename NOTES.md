# Notes

A short visual summary of the same material, with a live-demo script, is in [presentation.html](presentation.html) (open it in any browser).

## 1. Design

### Data model

```
users ──< requests >── (operator_id) users
            ├──< request_status_history   (from, to, who, when)
            ├──< request_messages         (author, body, when)
            ├──< message_reads            (one row per user: last message read)
            └──< assignments >── episodes
                 (episode_id UNIQUE, review_status: pending | accepted | rejected)
```

- **episodes**: `episode_id` is UNIQUE, so a second import cannot create a duplicate.
- **requests**: status is a CHECK-constrained column. `operator_id` is the first person who assigned episodes to it.
- **request_status_history**: one row per status change (who, when), written in the same transaction as the change.
- **assignments**: the link between an episode and a request. `UNIQUE(episode_id)` makes "an episode belongs to at most one request" a database rule, not only an application check. `review_status` holds the client's verdict on each delivered episode.

**Where state lives.** Everything durable is in PostgreSQL: users, episodes, requests, status, history, assignments, chat and read markers. The API is stateless: the JWT only says who you are, and the user is reloaded on every request, so deactivating someone or changing their role takes effect immediately. The browser keeps only the token and the theme.

**Where rules live.** In the server. The status table is 10 lines in `workflow.py`; the chat rule is one function in `chat_rules.py`. The UI draws its buttons from `allowed_next`, which the API computes per user, so the rules are never duplicated in the frontend. The database is the last guard: UNIQUE and CHECK constraints, a row lock (`SELECT … FOR UPDATE`) on the request during status changes and assignments, and foreign keys.

### The decisions I found hardest

**1. Duplicate episode ids with different values in the same file.** EP-00011 appears twice, identical except `bad` vs `good`. EP-00003 appears twice as two different recordings (different robot, task and date). "First row wins" is simple but arbitrary: line order means nothing, and it silently keeps possibly wrong data in a dataset we sell. I chose to **import neither** and report both lines as `conflicting_duplicate`. Identical duplicates are harmless, so one copy is kept. Because the import is idempotent, someone fixes the file and imports it again. A missing episode is visible in the report; a wrong one inside a delivered dataset is not.

**2. How much to trust the database versus the code.** The API checks everything first, to give clear messages: quality, "already assigned to request 4", "deliver needs 5 episodes". I still put the rules in the database as well, because two operators can click at the same moment. A test runs two threads assigning the same episode to two requests, eight rounds; every round exactly one gets 200 and the other a clean 409, never a 500 and never a double assignment. Removing my pre-check on purpose makes only the error-message test fail: the UNIQUE constraint still holds.

**3. What "accept" means when a delivery is not all-or-nothing.** The brief's model is accept or reject the whole delivery. Real reviews are rarely that clean, so the client reviews each episode: **keep**, **return** or **reject** (with a reason). Rejected episodes stop counting toward delivery and go back for rework; accepted ones are locked, and the operator cannot remove them later. If a delivery has more than was requested (asked for 2, got 5), a plain accept is refused. The client must return the extras, which frees them for other requests, or explicitly extend the request, which is recorded in the chat. The simple whole-delivery accept and reject endpoints still work and apply the same rules.

Other ambiguous points and the full data-cleaning rules are in the [Appendix](#appendix).

## 2. What I left out or simplified, and the next two days

**Left out or simplified**
- **Known robots are a constant** in `importer.py`; they should be a table managed by admins.
- **The CSV is read fully into memory** (fine for 200,000 rows, 12 MB). For millions I would stream it and use `COPY` into a staging table.
- **The requests list** loads at most 200 requests and filters in the browser.
- **The chat and unread counts refresh by polling** every 4 to 8 seconds, not WebSockets.
- **No stretch item was completed.** I spent that time on the per-episode review and the chat instead; the closest to the "real-time" stretch is the polling.
- **The token is kept in `localStorage`** (see Security).
- **No password reset, no email, no audit log for user management.**

**With two more days**
1. Replace polling with Server-Sent Events, for request changes and chat (the real-time stretch).
2. A daily roll-up table for analytics, and an index on `requests.created_at`.
3. Move the token to an httpOnly, SameSite cookie, and add login rate limiting.
4. A robots table and a staging-table import with `COPY`, plus import history (who imported which file, when, and the report).
5. Frontend tests for the review panel, and end-to-end tests (Playwright) for the main flows.

## 3. Something that went wrong

**Tests failed at random, about 1 run in 40, with a 401 on a valid token.** It never failed when I ran a single test. I wrote a temporary test that logged in and called the API 250 times, and on failure printed the JWT's `iat` next to `time.time()`. The token claimed it was issued about **22 seconds in the future**, and PyJWT correctly rejected it (`ImmatureSignatureError`). The cause was not our code: Docker Desktop's virtual machine clock on Windows was drifting and jumping. Two machines' clocks never agree exactly, so the fix was to accept 60 seconds of clock difference (`leeway` in `security.py`), with a test that a token 25 seconds ahead passes and one 10 minutes ahead fails.

**The 200,000-row import took 92 seconds.** Profiling showed parsing took 5.5 s, but building each 5,000-row `INSERT` statement took 1.3 s and executing it 2 s, because SQLAlchemy turned `.values(list)` into a single 1.2 MB SQL string. Passing the rows to `execute()` lets the driver send them in batches: 36 s in total, still idempotent (a second run: 0 imported, 200,000 already existed).

## 4. Security

**Passwords and tokens.** Passwords are hashed with bcrypt (cost 12; tests use 4 for speed), and must be 8 to 72 bytes, because bcrypt only uses the first 72 bytes. Login gives one message for both a wrong email and a wrong password, and runs bcrypt against a dummy hash when the email is unknown, so the response time does not reveal which emails exist. JWTs are signed with HS256; the algorithm is fixed on decode, so an unsigned `alg: none` token is refused (tested). They expire after 60 minutes. The user is reloaded on every request, so a deactivated account is locked out at once, not when its token expires. Secrets come from environment variables; the development defaults are only for local use.

**Input validation.** Every body and query goes through Pydantic schemas (types, ranges, lengths, allowed values). The database repeats the key rules with CHECK constraints (role, status, quality, review status, positive counts and durations). CSV uploads are capped at 25 MB and must be UTF-8; rows with NUL characters are rejected; every value is validated before insert. All SQL goes through SQLAlchemy with bound parameters, never string formatting.

**The two things I would worry about most**
1. **Broken access control (IDOR):** a client changing `/requests/7` to `/requests/8`, or an operator reading a chat they are not part of. Every endpoint checks ownership or role on the server, another client's request answers 404, and each of these rules has tests for the roles involved. This is still the kind of bug that appears when a new endpoint is added and forgets the check, so I would add a test that lists every route and asserts it requires authentication.
2. **Token theft through XSS.** The token is in `localStorage`, readable by any script running on the page. React escapes output and we never inject HTML, but one vulnerable dependency or future `dangerouslySetInnerHTML` would be enough. The next step is an httpOnly, SameSite cookie, plus a Content-Security-Policy header in nginx. Related: there is no login rate limiting yet, so passwords can be guessed slowly.

## 5. Scale

**10× users.** The API is stateless, so it scales by running more containers behind a load balancer. What breaks first is the **polling**: every open browser asks for `/chats` every 8 seconds and for a thread every 4 seconds, so 10× users means 10× those queries, each with per-request sub-counts. I would move to Server-Sent Events (push only when something changes), add the missing index on `request_messages(request_id, id)` for the unread count, and put PgBouncer in front of PostgreSQL, because each API worker holds its own connection pool.

**100× episodes (millions).**
- **Analytics over long ranges** break first: a full-year report reads nearly every row (321 ms at 200,000 rows, so about 30 s at 20 million). Fix: a daily roll-up table updated at import time, then monthly partitions of `episodes` by `recorded_at`.
- **The episode list's exact `total`** (`COUNT(*)` for paging) becomes slow; switch to keyset paging ("next page after id X") and an estimated count.
- **`GET /episodes/task-names`** uses `DISTINCT` over the whole table; it should become a small table.
- **The import** holds the whole file in memory and does one big transaction; switch to streaming, `COPY` into a staging table, then one `INSERT … SELECT … ON CONFLICT DO NOTHING`, run as a background job with progress.

Indexes already in place: `(recorded_at, robot_id)` for the per-day report and date filters, `(quality, recorded_at) INCLUDE (task_name)` for top tasks (measured 17 ms → 5.6 ms), `(quality, task_name)` for the episode filters, and the UNIQUE indexes on `episode_id`.

## 6. AI tooling

I used **Claude Code** (Anthropic's coding assistant) throughout as a pair programmer. I was the **developer and project lead**, responsible for the product decisions, implementation direction, testing, and final review. Claude Code proposed implementation plans and wrote much of the code, tests, and configuration, while I ran everything myself, reviewed and questioned the code, and made the necessary changes.

The product decisions were mine after discussing the options, including how conflicting duplicates are handled, rejecting future dates, the per-episode review and over-delivery rule, and who may use the chat.

To trust the result rather than relying solely on the assistant, every rule has tests, and for each important rule we deliberately broke the implementation to verify that the tests failed as expected. For example, removing `ON CONFLICT DO NOTHING` caused four import tests to fail. We also measured performance using real query plans and checked the UI with automated screenshots at both desktop and phone sizes.


---

## Appendix

### A. Ambiguities and how I decided

- **404, not 403,** when a client opens another client's request: we don't admit it exists.
- Order of checks on a status change: an impossible move is 409 before a wrong role is 403.
- `rejected → in_progress` (rework) is an operator step, like every step except accept and reject.
- Assigning more episodes than requested is allowed ("at least N"); the client then decides what to keep.
- Assignments are kept on rework; only the client's rejected ones stop counting.
- Median time to deliver: from creation to the **first** delivery, over requests created in the chosen range.
- Analytics days are UTC days; `from` and `to` are both included.
- Task names are stored lower case with single spaces, for requests and episodes alike, so filters match.
- Chat: the client and the operators who assigned episodes to the request read and write; an admin can read every chat but only write where they assigned episodes; other operators see nothing.

### B. Data cleaning rules

| In the file | What the import does |
|---|---|
| Spaces and mixed case (` arm-01`, `PICK CUP`, `Good`, `ep-00003`) | Cleaned |
| `2026-08-14 09:12:00`, `14/08/2026 09:15` (day first), trailing `Z`, `+02:00` | Accepted, stored in UTC; no time zone means UTC |
| `not a date` | Skipped: `invalid_date` |
| A date more than 1 day in the future (EP-00025: 2031) | Skipped: `future_date` |
| Duration `45.5` | Rounded half up to 46 |
| Duration empty, `N/A`, `-5`, `0` | Skipped: `invalid_duration` |
| Quality empty or `excellent` | Skipped: `invalid_quality` |
| Unknown robot (`arm-99`) or empty robot | Skipped: `unknown_robot` / `missing_robot` |
| Empty episode id | Skipped: `missing_episode_id` |
| Empty operator name | Imported, stored as NULL (the only optional field) |
| Wrong number of columns, blank lines | Skipped: `malformed_row` / `blank_line` |
| Same id twice, same values | One kept, the other `duplicate_in_file` |
| Same id twice, different values | Neither imported: `conflicting_duplicate` |
| Already in the database | Left unchanged, counted as `already_existed` |

A row with several problems reports all of them. The whole import is one transaction. The seed file gives 172 imported and 19 skipped, and running it again gives 0 imported and 172 already existed.
