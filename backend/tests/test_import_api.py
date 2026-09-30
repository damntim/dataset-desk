"""The import endpoint: who may use it, and that running it twice changes nothing."""

from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.db import SessionLocal
from app.models import Episode
from tests.test_import_parsing import GOOD, HEADER, csv_of


def upload(client, headers, text: str | bytes, name="episodes.csv"):
    data = text.encode("utf-8") if isinstance(text, str) else text
    return client.post("/episodes/import", files={"file": (name, data, "text/csv")}, headers=headers)


def episode_count() -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count(Episode.id)))


def three_episodes() -> str:
    return csv_of(
        "EP-1,arm-01,pick cup,2026-08-01T10:00:00,30,Aline,good",
        "EP-2,arm-02,fold towel,2026-08-02T10:00:00,40,Eric,usable",
        "EP-3,arm-03,open drawer,2026-08-03T10:00:00,50,Diane,bad",
    )


# ---------------------------------------------------------------- authorization


@pytest.mark.parametrize("who", ["operator", "admin"])
def test_staff_can_import(client, users, login_as, who):
    response = upload(client, login_as(users[who]), three_episodes())
    assert response.status_code == 200
    assert response.json()["imported"] == 3


def test_clients_cannot_import(client, users, login_as):
    assert upload(client, login_as(users["client_a"]), three_episodes()).status_code == 403
    assert episode_count() == 0


def test_anonymous_cannot_import(client, users):
    assert upload(client, None, three_episodes()).status_code == 401


# ---------------------------------------------------------------- idempotency (the important one)


def test_importing_the_same_file_twice_creates_no_duplicates(client, users, login_as):
    staff = login_as(users["operator"])

    first = upload(client, staff, three_episodes()).json()
    assert (first["imported"], first["already_existed"], first["skipped"]) == (3, 0, 0)
    assert episode_count() == 3

    second = upload(client, staff, three_episodes()).json()
    assert (second["imported"], second["already_existed"], second["skipped"]) == (0, 3, 0)
    assert episode_count() == 3  # still 3, not 6


def test_overlapping_files_only_add_the_new_rows(client, users, login_as):
    staff = login_as(users["operator"])
    upload(client, staff, three_episodes())
    bigger = three_episodes() + "EP-4,arm-01,pick cup,2026-08-04T10:00:00,60,Aline,good\n"

    report = upload(client, staff, bigger).json()
    assert (report["imported"], report["already_existed"]) == (1, 3)
    assert episode_count() == 4


def test_an_existing_episode_is_never_overwritten(client, users, login_as):
    staff = login_as(users["operator"])
    upload(client, staff, csv_of(GOOD))
    changed = "EP-1,arm-03,wipe table,2026-01-01T00:00:00,999,Kevin,bad"

    report = upload(client, staff, csv_of(changed)).json()
    assert report["already_existed"] == 1
    with SessionLocal() as db:
        episode = db.scalar(select(Episode).where(Episode.episode_id == "EP-1"))
    assert (episode.robot_id, episode.quality) == ("arm-01", "good")


# ---------------------------------------------------------------- the report


def test_report_adds_up_and_explains_every_skipped_row(client, users, login_as):
    text = csv_of(
        GOOD,
        "EP-2,arm-99,pick cup,2026-08-01T10:00:00,30,Aline,good",  # line 3: unknown robot
        "EP-3,arm-01,pick cup,2026-08-01T10:00:00,30,Aline,excellent",  # line 4: bad quality
        GOOD,  # line 5: duplicate of line 2
        "",  # line 6: blank
    )
    report = upload(client, login_as(users["operator"]), text).json()

    assert report["total_rows"] == 5
    assert report["imported"] + report["already_existed"] + report["skipped"] == 5
    assert (report["imported"], report["skipped"]) == (1, 4)
    assert report["skipped_by_reason"] == {
        "unknown_robot": 1,
        "invalid_quality": 1,
        "duplicate_in_file": 1,
        "blank_line": 1,
    }
    lines = {row["line"]: row for row in report["skipped_details"]}
    assert set(lines) == {3, 4, 5, 6}
    assert lines[3]["episode_id"] == "EP-2"
    assert lines[3]["reasons"][0]["code"] == "unknown_robot"


def test_long_lists_are_cut_but_the_counts_stay_exact(client, users, login_as, monkeypatch):
    monkeypatch.setattr("app.importer.MAX_DETAILS", 2)
    lines = [f"EP-{i},arm-99,pick cup,2026-08-01T10:00:00,30,Aline,good" for i in range(5)]
    report = upload(client, login_as(users["operator"]), csv_of(*lines)).json()
    assert report["skipped"] == 5
    assert len(report["skipped_details"]) == 2
    assert report["details_truncated"] is True


def test_large_batches_are_split_into_chunks(client, users, login_as, monkeypatch):
    monkeypatch.setattr("app.importer.CHUNK_SIZE", 2)
    lines = [f"EP-{i},arm-01,pick cup,2026-08-01T10:00:00,30,Aline,good" for i in range(5)]
    report = upload(client, login_as(users["operator"]), csv_of(*lines)).json()
    assert report["imported"] == 5
    assert episode_count() == 5


# ---------------------------------------------------------------- bad files


def test_file_with_missing_column_is_400_and_imports_nothing(client, users, login_as):
    response = upload(client, login_as(users["operator"]), "episode_id,robot_id\nEP-1,arm-01\n")
    assert response.status_code == 400
    assert "Missing column" in response.json()["detail"]
    assert episode_count() == 0


def test_non_utf8_file_is_400(client, users, login_as):
    response = upload(client, login_as(users["operator"]), HEADER.encode() + b"\ncaf\xe9\n")
    assert response.status_code == 400


def test_oversized_upload_is_413(client, users, login_as, monkeypatch):
    monkeypatch.setattr("app.routers.episodes.MAX_UPLOAD_BYTES", 50)
    assert upload(client, login_as(users["operator"]), three_episodes()).status_code == 413
    assert episode_count() == 0


def test_request_without_a_file_is_422(client, users, login_as):
    assert client.post("/episodes/import", headers=login_as(users["operator"])).status_code == 422


# ---------------------------------------------------------------- the real messy export


SEED_FILE = Path(settings.seed_dir) / "episodes.csv"


@pytest.mark.skipif(not SEED_FILE.exists(), reason="seed/episodes.csv not available")
def test_real_seed_file_gives_the_expected_report_and_is_repeatable(client, users, login_as):
    staff = login_as(users["operator"])
    data = SEED_FILE.read_bytes()

    first = upload(client, staff, data).json()
    assert first["total_rows"] == 191
    assert (first["imported"], first["already_existed"], first["skipped"]) == (172, 0, 19)
    assert first["skipped_by_reason"] == {
        "duplicate_in_file": 2,  # EP-00030, EP-00074: identical copies
        "conflicting_duplicate": 4,  # EP-00003, EP-00011: two lines each, different values
        "missing_episode_id": 1,
        "invalid_quality": 2,  # empty, "excellent"
        "invalid_duration": 3,  # empty, -5, N/A
        "invalid_date": 1,  # "not a date"
        "future_date": 1,  # EP-00025, recorded "2031-01-01"
        "unknown_robot": 1,  # arm-99
        "missing_robot": 1,
        "malformed_row": 1,  # only 5 columns
        "blank_line": 2,
    }

    second = upload(client, staff, data).json()
    assert (second["imported"], second["already_existed"], second["skipped"]) == (0, 172, 19)
    assert episode_count() == 172

    with SessionLocal() as db:
        # These were dirty in the file and must be clean in the database.
        by_id = {e.episode_id: e for e in db.scalars(select(Episode))}
    assert by_id["EP-00008"].robot_id == "arm-01"  # was " arm-01"
    assert by_id["EP-00006"].task_name == "pick cup"  # was "  Pick Cup "
    assert by_id["EP-00009"].quality == "good"  # was "Good"
    assert "EP-00003" not in by_id and "EP-00011" not in by_id  # conflicting: neither imported
    assert by_id["EP-00014"].recorded_at.day == 14  # was "14/08/2026 09:15"
    assert by_id["EP-00018"].duration_seconds in (45, 46)  # was 45.5
    assert all(
        e.robot_id in {"arm-01", "arm-02", "arm-03", "mobile-01", "humanoid-01"} for e in by_id.values()
    )
