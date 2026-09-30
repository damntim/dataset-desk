# Dataset Request Desk

An internal platform that replaces the dataset-request spreadsheet: **clients** request robot teleoperation episodes, **operators** assemble them from the recording system's exports, and the client reviews and accepts or rejects the delivery.

- **Backend:** Python 3.13, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16
- **Frontend:** React 19 + Vite, served by nginx
- **Tests:** pytest (255 tests) against a real PostgreSQL · **CI:** GitHub Actions
- **Design notes, decisions and trade-offs:** see [NOTES.md](NOTES.md)
- **Slide deck:** open [presentation.html](presentation.html) in a browser: the problem, the design, how it was tested, and a demo script (← → to navigate, F fullscreen, N speaker notes)

![CI](https://github.com/damntim/dataset-desk/actions/workflows/ci.yml/badge.svg)

---

## Run it

Requirements: Docker with Docker Compose. Nothing else.

```bash
git clone https://github.com/damntim/dataset-desk.git
cd dataset-desk
docker compose up --build
```

On first start the API container applies the migrations, creates the seed users and imports `seed/episodes.csv`. Then open:

| What | Where |
|---|---|
| Web app | http://localhost:3000 |
| API docs (interactive) | http://localhost:8000/docs |
| Health check | http://localhost:8000/health (also http://localhost:3000/api/health) |

Stop with `docker compose down`. Add `-v` to also delete the database and start from zero.

**Configuration** (all optional, safe defaults for local use): copy `.env.example` to `.env` and set `POSTGRES_PASSWORD` and `JWT_SECRET`. Other settings: `JWT_EXPIRE_MINUTES` (default 60), `BCRYPT_ROUNDS` (default 12).

## Seed accounts

The login page also has one-click buttons for these.

| Role | Email | Password |
|---|---|---|
| admin | admin@example.com | admin123 |
| operator | ops1@example.com | ops123 |
| operator | ops2@example.com | ops123 |
| client (Acme Robotics) | client-a@example.com | client123 |
| client (Beta Labs) | client-b@example.com | client123 |

Passwords are stored as bcrypt hashes.

## Run the tests

```bash
docker compose run --rm api pytest -q
```

The tests use their own database (`desk_test`, created automatically in the same PostgreSQL), run the real migrations, and empty the tables before each test, so they never touch your data. About 90 seconds.

Most important areas: authorization (`test_auth.py`, `test_users_admin.py`, `test_chat.py`), status transitions (`test_workflow.py`, `test_requests.py`), assignment rules (`test_assignments.py`, `test_review.py`), import idempotency and cleaning (`test_import_api.py`, `test_import_parsing.py`), analytics (`test_analytics.py`).

Lint: `docker compose run --rm api ruff check .` and `ruff format --check .`

**CI** (`.github/workflows/ci.yml`) runs on every push: lint, the full test suite against PostgreSQL, the frontend build, and a smoke test that runs `docker compose up --build` from a clean checkout and calls `/health` and the login through the web app.

## Import episodes

From the web app: **Import** page (operator or admin), drop a CSV.

From the command line:

```bash
docker compose exec api python -m app.importer /seed/episodes.csv
```

Both return a report: `imported + already_existed + skipped = total_rows`, with the line number and reason of every skipped row. Importing the same file again imports nothing new. The seed file gives **172 imported, 19 skipped**. The cleaning rules are listed in [NOTES.md](NOTES.md#b-data-cleaning-rules) (appendix).

**Optional demo history** (so the reports have something to show; never runs by itself, safe to run twice):

```bash
docker compose exec api python -m app.demo_data
```

It creates 24 requests over the last 60 days in every state (accepted, reworked, rejected, in progress, overdue), following the same rules as the API.

A large clean file for load testing: `python seed/generate_episodes.py 200000 > seed/episodes_large.csv`.

## API overview

All endpoints except `/auth/login` and `/health` need `Authorization: Bearer <token>`. Authorization is enforced on the server for every call.

| Method and path | Who | What |
|---|---|---|
| `POST /auth/login`, `GET /auth/me` | anyone / logged in | Get a token; who am I |
| `GET /users`, `POST /users`, `PATCH /users/{id}` | admin | List, create, change role, deactivate |
| `POST /requests` | client | Create a request |
| `GET /requests`, `GET /requests/{id}` | all (clients: own only) | List (filter by `status`), detail with status history |
| `PATCH /requests/{id}/status` | per transition | Move through the workflow (see below) |
| `POST /requests/{id}/review` | owning client | Review a delivery episode by episode |
| `GET /episodes` | operator, admin | Filter by `task_name`, `quality`, `unassigned`; paginated |
| `POST /episodes/import` | operator, admin | CSV upload (25 MB max) |
| `POST /requests/{id}/assignments`, `DELETE …/assignments/{episode}` | operator, admin | Assign / unassign episodes |
| `GET /requests/{id}/episodes` | owning client, staff | Episodes in a request, with the client's verdict |
| `GET/POST /requests/{id}/messages`, `POST …/messages/read`, `GET /chats` | see NOTES.md | Chat per request, unread counts |
| `GET /analytics?from=YYYY-MM-DD&to=YYYY-MM-DD` | operator, admin | Reports (below) |
| `GET /reports/overview?from=…&to=…` | admin | Insights report: response, delivery and review times, on-time rate, operator leaderboard, client rejection rates, rejections by robot and task, every rejected video, requests at risk |
| `GET /health` | anyone | App and database status |

**Workflow:** `submitted → in_progress → delivered → accepted`, or `delivered → rejected → in_progress` (rework). Clients accept or reject their own deliveries; operators and admins do every other step. A request can only be delivered once it has at least the requested number of episodes. Every change is recorded with who and when. An invalid move answers 409, the wrong role 403, and another client's request 404.

## Analytics, and what happens at 5 million episodes

`GET /analytics` returns, for a date range (days in UTC, both ends included, 366 days max):

- episodes recorded per day per robot (`GROUP BY` day, robot);
- requests by status, and the median time from submitted to (first) delivered (`percentile_cont(0.5)`);
- the top 5 task names by number of good episodes.

Every number is computed in PostgreSQL; Python receives only the result rows, and the number of queries does not grow with the data (a test checks this).

Measured with 200,000 generated episodes (`EXPLAIN ANALYZE`):

| Query | 30-day range | 365-day range |
|---|---|---|
| Per day per robot | 18 ms (index-only scan) | 321 ms (sequential scan + sort spilling to disk) |
| Top 5 tasks by good episodes | 5.6 ms (covering index) | 53 ms (parallel sequential scan) |
| Median time to deliver (50,000 requests) | | 122 ms |

**At 5 million episodes** (about 25 times more): a narrow range stays fast, because the indexes on `(recorded_at, robot_id)` and `(quality, recorded_at) INCLUDE (task_name)` read only the rows in the range, so the cost follows the range, not the table. A full-year range has to touch almost every row: roughly 8 seconds, with the sort going to disk. The fix I would apply first is a daily roll-up table (one row per day, robot, task and quality, updated at import time: at most 365 × 5 × 7 × 3 ≈ 38,000 rows per year), which answers every report in milliseconds. After that: monthly partitioning of `episodes` by `recorded_at`, and a BRIN index. Details in [NOTES.md](NOTES.md#5-scale).

## Project layout

```
backend/
  app/            FastAPI app: models, schemas, routers, import, rules
  alembic/        migrations
  tests/          pytest
frontend/
  src/            React pages and components
seed/             users.json, episodes.csv, generator
docker-compose.yml
.github/workflows/ci.yml
```
