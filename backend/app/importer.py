"""Import episodes from the (messy) CSV export of the recording system.

Two steps, kept apart so each is easy to read and test:
  1. parse_csv   - read the text, clean every row, decide: valid or skipped (and why).
  2. import_episodes - save the valid rows. Safe to run twice: rows whose episode_id
     already exists are left alone (INSERT ... ON CONFLICT DO NOTHING).

Command line:   python -m app.importer path/to/episodes.csv
"""
import csv
import io
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import QUALITIES, Episode

COLUMNS = [
    "episode_id",
    "robot_id",
    "task_name",
    "recorded_at",
    "duration_seconds",
    "operator_name",
    "quality",
]
# In a real system this list would be a table. For now it is the list from seed/README.md.
KNOWN_ROBOTS = {"arm-01", "arm-02", "arm-03", "mobile-01", "humanoid-01"}

ID_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,49}$")
DAY_FIRST_FORMATS = ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M")  # 14/08/2026 09:15 = 14 August
MAX_DURATION = 2_147_483_647  # the biggest number an integer column can hold
CHUNK_SIZE = 5000  # rows per INSERT statement
MAX_DETAILS = 500  # the report lists at most this many rows per list (the counts stay exact)

Issue = tuple[str, str]  # (code, human-readable message)


class ImportFileError(Exception):
    """The whole file is unusable. Nothing is imported."""


@dataclass
class Skipped:
    line: int
    episode_id: str | None
    issues: list[Issue]


@dataclass
class ParseResult:
    total_rows: int = 0
    valid: list[tuple[int, dict]] = field(default_factory=list)  # (line, cleaned values)
    skipped: list[Skipped] = field(default_factory=list)


# ---------------------------------------------------------------- cleaning one value


def _shown(value: str) -> str:
    value = value.strip()
    return f"'{value}'" if value else "empty"


def parse_datetime(value: str) -> datetime | None:
    """ISO ('2026-08-14T09:20:00', with a space, with Z or an offset) or DD/MM/YYYY HH:MM.
    A time without a timezone is taken as UTC. Everything is stored in UTC."""
    value = value.strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        parsed = None
        for fmt in DAY_FIRST_FORMATS:
            try:
                parsed = datetime.strptime(value, fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            return None
    try:
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def parse_duration(value: str) -> int | None:
    """A positive number of seconds. '45.5' is rounded to 46. Anything else: None."""
    try:
        number = Decimal(value.strip())
        if not number.is_finite():
            return None
        seconds = int(number.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return None
    return seconds if 0 < seconds <= MAX_DURATION else None


def clean_row(row: dict[str, str]) -> tuple[dict, list[Issue]]:
    """Wash one row. Returns the cleaned values and the list of problems (empty = valid)."""
    issues: list[Issue] = []

    episode_id = row["episode_id"].strip().upper()
    if not episode_id:
        issues.append(("missing_episode_id", "episode_id is empty"))
    elif not ID_PATTERN.match(episode_id):
        issues.append(
            ("invalid_episode_id", f"episode_id is {_shown(row['episode_id'])}; "
             "use letters, digits, '-' or '_' (max 50 characters)")
        )

    robot_id = row["robot_id"].strip().lower()
    if not robot_id:
        issues.append(("missing_robot", "robot_id is empty"))
    elif robot_id not in KNOWN_ROBOTS:
        issues.append(("unknown_robot", f"robot_id is {_shown(robot_id)}; this robot is not known"))

    task_name = " ".join(row["task_name"].split()).lower()
    if not task_name:
        issues.append(("missing_task_name", "task_name is empty"))
    elif len(task_name) > 255:
        issues.append(("invalid_task_name", "task_name is longer than 255 characters"))

    recorded_at = parse_datetime(row["recorded_at"])
    if recorded_at is None:
        issues.append(
            ("invalid_date", f"recorded_at is {_shown(row['recorded_at'])}; expected an ISO "
             "date-time or DD/MM/YYYY HH:MM")
        )

    duration = parse_duration(row["duration_seconds"])
    if duration is None:
        issues.append(
            ("invalid_duration", f"duration_seconds is {_shown(row['duration_seconds'])}; "
             "it must be a positive number")
        )

    operator_name = " ".join(row["operator_name"].split()) or None  # empty is allowed
    if operator_name and len(operator_name) > 255:
        issues.append(("invalid_operator_name", "operator_name is longer than 255 characters"))

    quality = row["quality"].strip().lower()
    if quality not in QUALITIES:
        issues.append(
            ("invalid_quality", f"quality is {_shown(row['quality'])}; it must be good, usable or bad")
        )

    values = {
        "episode_id": episode_id,
        "robot_id": robot_id,
        "task_name": task_name,
        "recorded_at": recorded_at,
        "duration_seconds": duration,
        "operator_name": operator_name,
        "quality": quality,
    }
    return values, issues


# ---------------------------------------------------------------- step 1: read the file


def decode_file(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")  # utf-8-sig also removes an Excel byte-order mark
    except UnicodeDecodeError:
        raise ImportFileError("The file is not valid UTF-8 text") from None


def parse_csv(text: str) -> ParseResult:
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise ImportFileError("The file is empty") from None
    except csv.Error as exc:
        raise ImportFileError(f"The header row could not be read: {exc}") from None

    names = [h.strip().lower() for h in header]
    missing = [c for c in COLUMNS if c not in names]
    if missing:
        raise ImportFileError("Missing column(s): " + ", ".join(missing))
    position = {name: names.index(name) for name in COLUMNS}  # so column order does not matter

    result = ParseResult()
    seen: dict[str, tuple[int, dict]] = {}  # episode_id -> (line, values) of the first valid row

    while True:
        try:
            cells = next(reader)
        except StopIteration:
            break
        except csv.Error as exc:
            result.total_rows += 1
            result.skipped.append(
                Skipped(reader.line_num, None, [("malformed_row", f"row could not be read: {exc}")])
            )
            continue

        line = reader.line_num
        result.total_rows += 1

        if not any(cell.strip() for cell in cells):
            result.skipped.append(Skipped(line, None, [("blank_line", "blank line")]))
            continue

        guessed_id = None
        if len(cells) > position["episode_id"]:
            guessed_id = cells[position["episode_id"]].strip().upper() or None

        if len(cells) != len(names):
            message = f"expected {len(names)} columns, got {len(cells)}"
            result.skipped.append(Skipped(line, guessed_id, [("malformed_row", message)]))
            continue
        if any("\x00" in cell for cell in cells):  # PostgreSQL cannot store NUL characters
            result.skipped.append(
                Skipped(line, guessed_id, [("malformed_row", "row contains a NUL character")])
            )
            continue

        values, issues = clean_row({name: cells[pos] for name, pos in position.items()})
        if not issues:
            first = seen.get(values["episode_id"])
            if first is not None:
                first_line, first_values = first
                detail = "same values" if first_values == values else (
                    "different values, the first one was kept"
                )
                issues.append(
                    ("duplicate_in_file", f"episode_id already appears on line {first_line} ({detail})")
                )
            else:
                seen[values["episode_id"]] = (line, values)
                result.valid.append((line, values))
                continue
        result.skipped.append(Skipped(line, values["episode_id"] or guessed_id, issues))

    return result


# ---------------------------------------------------------------- step 2: save the valid rows


def import_episodes(db: Session, text: str) -> dict:
    parsed = parse_csv(text)

    imported: set[str] = set()
    rows = [values for _, values in parsed.valid]
    for start in range(0, len(rows), CHUNK_SIZE):
        statement = (
            insert(Episode)
            .values(rows[start : start + CHUNK_SIZE])
            .on_conflict_do_nothing(index_elements=["episode_id"])  # already there? do nothing
            .returning(Episode.episode_id)  # ...and tell us which rows were really new
        )
        imported.update(db.execute(statement).scalars())
    db.commit()  # all chunks together: the import happens completely or not at all

    already_existed = [
        {"line": line, "episode_id": values["episode_id"]}
        for line, values in parsed.valid
        if values["episode_id"] not in imported
    ]
    skipped_details = [
        {
            "line": s.line,
            "episode_id": s.episode_id,
            "reasons": [{"code": code, "message": message} for code, message in s.issues],
        }
        for s in parsed.skipped
    ]
    return {
        "total_rows": parsed.total_rows,
        "imported": len(imported),
        "already_existed": len(already_existed),
        "skipped": len(parsed.skipped),
        # one row can have several problems, so these counts can add up to more than "skipped"
        "skipped_by_reason": dict(Counter(code for s in parsed.skipped for code, _ in s.issues)),
        "skipped_details": skipped_details[:MAX_DETAILS],
        "already_existed_details": already_existed[:MAX_DETAILS],
        "details_truncated": len(skipped_details) > MAX_DETAILS
        or len(already_existed) > MAX_DETAILS,
    }


# ---------------------------------------------------------------- command line


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m app.importer path/to/episodes.csv", file=sys.stderr)
        return 2
    from app.db import SessionLocal  # imported here so the pure functions above need no database

    try:
        text = decode_file(Path(argv[1]).read_bytes())
        with SessionLocal() as db:
            report = import_episodes(db, text)
    except (ImportFileError, OSError) as exc:
        print(f"import failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
