"""Cleaning rules of the CSV import. Pure functions: no database, no web."""

from datetime import UTC, datetime, timedelta

import pytest

from app.importer import ImportFileError, decode_file, parse_csv

HEADER = "episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality"
GOOD = "EP-1,arm-01,pick cup,2026-08-01T10:00:00,30,Aline,good"


def csv_of(*lines: str) -> str:
    return HEADER + "\n" + "\n".join(lines) + "\n"


def only_row(line: str):
    """Parse a one-row file and return (valid values or None, skipped issue codes)."""
    result = parse_csv(csv_of(line))
    assert result.total_rows == 1
    if result.valid:
        return result.valid[0][1], []
    return None, [code for code, _ in result.skipped[0].issues]


# ---------------------------------------------------------------- washing (accepted)


def test_dirty_but_valid_row_is_cleaned():
    values, codes = only_row(" ep-00003 , ARM-01 ,  Pick   CUP , 2026-08-01T10:00:00 , 30 ,  Aline  , GOOD ")
    assert codes == []
    assert values == {
        "episode_id": "EP-00003",
        "robot_id": "arm-01",
        "task_name": "pick cup",
        "recorded_at": datetime(2026, 8, 1, 10, 0, tzinfo=UTC),
        "duration_seconds": 30,
        "operator_name": "Aline",
        "quality": "good",
    }


@pytest.mark.parametrize(
    "text",
    [
        "2026-08-14T09:20:00",  # ISO, no timezone: taken as UTC
        "2026-08-14 09:20:00",  # space instead of T
        "2026-08-14T09:20:00Z",  # Z = UTC
        "2026-08-14T11:20:00+02:00",  # other timezone: converted to UTC
        "14/08/2026 09:20",  # day first
    ],
)
def test_accepted_date_formats_all_become_the_same_utc_time(text):
    values, codes = only_row(f"EP-1,arm-01,pick cup,{text},30,Aline,good")
    assert codes == []
    assert values["recorded_at"] == datetime(2026, 8, 14, 9, 20, tzinfo=UTC)


@pytest.mark.parametrize("text,expected", [("45.5", 46), ("44.5", 45), ("30", 30), ("30.4", 30)])
def test_fractional_duration_is_rounded_half_up(text, expected):
    values, codes = only_row(f"EP-1,arm-01,pick cup,2026-08-01T10:00:00,{text},Aline,good")
    assert codes == []
    assert values["duration_seconds"] == expected


def test_a_date_a_few_hours_ahead_is_tolerated():
    """Clocks and time zones differ a little: up to 1 day ahead is accepted."""
    soon = (datetime.now(UTC) + timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%S")
    values, codes = only_row(f"EP-1,arm-01,pick cup,{soon},30,Aline,good")
    assert codes == []


def test_empty_operator_name_is_allowed_and_stored_as_null():
    values, codes = only_row("EP-1,arm-01,pick cup,2026-08-01T10:00:00,30,,good")
    assert codes == []
    assert values["operator_name"] is None


# ---------------------------------------------------------------- rejected, with a reason


REJECTED = [
    ("EP-1,arm-99,pick cup,2026-08-01T10:00:00,30,Aline,good", "unknown_robot"),
    ("EP-1,,pick cup,2026-08-01T10:00:00,30,Aline,good", "missing_robot"),
    (",arm-01,pick cup,2026-08-01T10:00:00,30,Aline,good", "missing_episode_id"),
    ("EP 1!,arm-01,pick cup,2026-08-01T10:00:00,30,Aline,good", "invalid_episode_id"),
    ("EP-1,arm-01,,2026-08-01T10:00:00,30,Aline,good", "missing_task_name"),
    (f"EP-1,arm-01,{'x' * 300},2026-08-01T10:00:00,30,Aline,good", "invalid_task_name"),
    ("EP-1,arm-01,pick cup,not a date,30,Aline,good", "invalid_date"),
    ("EP-1,arm-01,pick cup,,30,Aline,good", "invalid_date"),
    ("EP-1,arm-01,pick cup,31/02/2026 10:00,30,Aline,good", "invalid_date"),
    ("EP-1,arm-01,pick cup,2099-01-01T00:00:00,30,Aline,good", "future_date"),
    ("EP-1,arm-01,pick cup,2026-08-01T10:00:00,,Aline,good", "invalid_duration"),
    ("EP-1,arm-01,pick cup,2026-08-01T10:00:00,N/A,Aline,good", "invalid_duration"),
    ("EP-1,arm-01,pick cup,2026-08-01T10:00:00,-5,Aline,good", "invalid_duration"),
    ("EP-1,arm-01,pick cup,2026-08-01T10:00:00,0,Aline,good", "invalid_duration"),
    ("EP-1,arm-01,pick cup,2026-08-01T10:00:00,0.4,Aline,good", "invalid_duration"),
    ("EP-1,arm-01,pick cup,2026-08-01T10:00:00,NaN,Aline,good", "invalid_duration"),
    ("EP-1,arm-01,pick cup,2026-08-01T10:00:00,99999999999,Aline,good", "invalid_duration"),
    ("EP-1,arm-01,pick cup,2026-08-01T10:00:00,30,Aline,", "invalid_quality"),
    ("EP-1,arm-01,pick cup,2026-08-01T10:00:00,30,Aline,excellent", "invalid_quality"),
    ("EP-1,arm-01,pick cup,2026-08-01T10:00:00,30", "malformed_row"),  # too few columns
    ("EP-1,arm-01,pick cup,2026-08-01T10:00:00,30,Aline,good,extra", "malformed_row"),
    ("EP-1,arm-01,pick cup,2026-08-01T10:00:00,30,Ali\x00ne,good", "malformed_row"),  # NUL
    ("", "blank_line"),
    ("   ", "blank_line"),
]


@pytest.mark.parametrize("line,code", REJECTED)
def test_bad_rows_are_skipped_with_the_right_reason(line, code):
    values, codes = only_row(line)
    assert values is None
    assert code in codes


def test_a_row_with_several_problems_reports_all_of_them():
    _, codes = only_row("EP-1,arm-99,pick cup,not a date,-5,Aline,excellent")
    assert set(codes) == {"unknown_robot", "invalid_date", "invalid_duration", "invalid_quality"}


# ---------------------------------------------------------------- duplicates inside one file


def test_duplicate_with_same_values_is_skipped_and_points_to_the_first():
    result = parse_csv(csv_of(GOOD, GOOD))
    assert len(result.valid) == 1
    ((code, message),) = result.skipped[0].issues
    assert code == "duplicate_in_file"
    assert "line 2" in message and "same values" in message


def test_duplicate_with_different_values_imports_neither_and_reports_both_lines():
    other = "ep-1,arm-02,fold towel,2026-08-02T10:00:00,99,Eric,bad"  # also different capitals
    result = parse_csv(csv_of(GOOD, other))
    assert result.valid == []
    assert [s.line for s in result.skipped] == [2, 3]
    assert all(s.issues[0][0] == "conflicting_duplicate" for s in result.skipped)


def test_an_invalid_first_row_does_not_block_a_valid_second_row_with_the_same_id():
    bad_first = "EP-1,arm-99,pick cup,2026-08-01T10:00:00,30,Aline,good"
    result = parse_csv(csv_of(bad_first, GOOD))
    assert len(result.valid) == 1 and len(result.skipped) == 1


def test_line_numbers_point_at_the_line_in_the_file():
    result = parse_csv(csv_of(GOOD, "EP-2,arm-99,pick cup,2026-08-01T10:00:00,30,Aline,good"))
    assert result.valid[0][0] == 2
    assert result.skipped[0].line == 3


# ---------------------------------------------------------------- the file as a whole


def test_columns_may_come_in_any_order_and_extra_columns_are_fine():
    text = "quality,notes,episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name\n"
    text += "good,hello,EP-1,arm-01,pick cup,2026-08-01T10:00:00,30,Aline\n"
    result = parse_csv(text)
    assert result.valid[0][1]["episode_id"] == "EP-1"


def test_missing_column_rejects_the_whole_file():
    with pytest.raises(ImportFileError, match="Missing column.*quality"):
        parse_csv("episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name\n")


def test_empty_file_is_rejected():
    with pytest.raises(ImportFileError, match="empty"):
        parse_csv("")


def test_excel_byte_order_mark_is_ignored():
    data = ("﻿" + csv_of(GOOD)).encode("utf-8")
    assert len(parse_csv(decode_file(data)).valid) == 1


def test_file_that_is_not_utf8_is_rejected():
    with pytest.raises(ImportFileError, match="UTF-8"):
        decode_file("caf\xe9".encode("latin-1"))
