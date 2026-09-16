from datetime import datetime

import config
import database

from timezone_service import (
    events_overlap,
    get_user_timezone,
    now_for_user,
    parse_user_datetime,
)


def test_missing_user_timezone_falls_back_to_default(monkeypatch, tmp_path):
    db_path = tmp_path / "agent.db"
    monkeypatch.setattr(config, "DATABASE_PATH", str(db_path))
    monkeypatch.setattr(database, "DATABASE_PATH", str(db_path))
    database.init_database()

    assert get_user_timezone("missing-user") == "Asia/Tashkent"
    assert now_for_user("missing-user").tzinfo is not None


def test_invalid_timezone_falls_back_to_default(monkeypatch, tmp_path):
    db_path = tmp_path / "agent.db"
    monkeypatch.setattr(config, "DATABASE_PATH", str(db_path))
    monkeypatch.setattr(database, "DATABASE_PATH", str(db_path))
    database.init_database()

    db = database.get_db()
    db.execute(
        "INSERT INTO users (user_id, timezone) VALUES (?, ?)",
        ("u-1", "Not/AZone"),
    )
    db.commit()
    db.close()

    assert get_user_timezone("u-1") == "Asia/Tashkent"


def test_parse_user_datetime_in_user_timezone(monkeypatch, tmp_path):
    db_path = tmp_path / "agent.db"
    monkeypatch.setattr(config, "DATABASE_PATH", str(db_path))
    monkeypatch.setattr(database, "DATABASE_PATH", str(db_path))
    database.init_database()

    db = database.get_db()
    db.execute(
        "INSERT INTO users (user_id, timezone) VALUES (?, ?)",
        ("u-2", "Europe/Berlin"),
    )
    db.commit()
    db.close()

    value = "2026-09-16 09:00"
    parsed = parse_user_datetime("u-2", value)

    assert parsed.tzinfo is not None
    assert parsed.isoformat().endswith("+02:00")


def test_events_overlap_boundaries_are_correct():
    assert not events_overlap(
        "2026-09-16 09:00",
        "2026-09-16 10:00",
        "2026-09-16 10:00",
        "2026-09-16 11:00",
    )
    assert events_overlap(
        "2026-09-16 09:00",
        "2026-09-16 10:00",
        "2026-09-16 09:59",
        "2026-09-16 11:00",
    )
    assert not events_overlap(
        "2026-09-16 09:00",
        "2026-09-16 10:00",
        "2026-09-16 08:00",
        "2026-09-16 09:00",
    )
    assert events_overlap(
        "2026-09-16 09:00",
        "2026-09-16 10:00",
        "2026-09-16 08:30",
        "2026-09-16 09:30",
    )


def test_parse_user_datetime_rejects_naive_aware_mismatch(monkeypatch, tmp_path):
    db_path = tmp_path / "agent.db"
    monkeypatch.setattr(config, "DATABASE_PATH", str(db_path))
    monkeypatch.setattr(database, "DATABASE_PATH", str(db_path))
    database.init_database()

    db = database.get_db()
    db.execute(
        "INSERT INTO users (user_id, timezone) VALUES (?, ?)",
        ("u-3", "UTC"),
    )
    db.commit()
    db.close()

    parsed = parse_user_datetime("u-3", "2026-09-16 12:00")

    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == datetime.fromisoformat("2026-09-16T12:00:00+00:00").utcoffset()
