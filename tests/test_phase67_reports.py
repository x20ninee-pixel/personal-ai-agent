from datetime import datetime

import database

from tools import execute_tool


def _seed_user_data(user_id, *, day="2026-09-16"):
    db = database.get_db()
    db.execute(
        "INSERT INTO tasks (user_id, title, status, priority, due_date, category, estimated_minutes) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, "Russian lesson", "COMPLETED", "HIGH", f"{day} 09:00:00", "RUSSIAN", 60),
    )
    db.execute(
        "INSERT INTO tasks (user_id, title, status, priority, due_date, category, estimated_minutes) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, "Excel lesson", "PARTIAL", "MEDIUM", f"{day} 10:00:00", "EXCEL", 80),
    )
    db.execute(
        "INSERT INTO tasks (user_id, title, status, priority, due_date, category, estimated_minutes) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, "Gym session", "MISSED", "HIGH", f"{day} 18:00:00", "FITNESS", 70),
    )
    db.execute(
        "INSERT INTO tasks (user_id, title, status, priority, due_date, category, estimated_minutes) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, "Russian review", "SKIPPED", "MEDIUM", f"{day} 20:00:00", "RUSSIAN", 45),
    )
    db.execute(
        "INSERT INTO tasks (user_id, title, status, priority, due_date, category, estimated_minutes) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, "Deep work", "PLANNED", "LOW", f"{day} 21:00:00", "GENERAL", 30),
    )
    db.execute(
        "INSERT INTO goals (user_id, name, category, status, target_value, current_progress, unit, priority) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, "Russian B2", "RUSSIAN", "ACTIVE", 55, 17, "lessons", "HIGH"),
    )
    db.execute(
        "INSERT INTO habits (user_id, name, target, unit, frequency, active) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, "Walking", 10000, "steps", "DAILY", 1),
    )
    habit_id = db.execute(
        "SELECT id FROM habits WHERE user_id = ? AND name = 'Walking'",
        (user_id,),
    ).fetchone()[0]
    db.execute(
        "INSERT INTO habit_logs (habit_id, date, value) VALUES (?, ?, ?)",
        (habit_id, day, 9420),
    )
    db.execute(
        "INSERT INTO habits (user_id, name, target, unit, frequency, active) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, "Reading", 30, "minutes", "DAILY", 1),
    )
    db.commit()
    db.close()


def test_get_daily_report_uses_real_metrics_and_user_scope(tmp_path, monkeypatch):
    db_path = tmp_path / "agent.db"
    monkeypatch.setattr(database, "DATABASE_PATH", str(db_path))
    database.init_database()

    _seed_user_data("u-1")
    _seed_user_data("u-2")

    result = execute_tool("u-1", "get_daily_report", {"date": "2026-09-16"})

    assert result["ok"] is True
    assert result["summary"]["completed"] == 1
    assert result["summary"]["partial"] == 1
    assert result["summary"]["skipped"] == 1
    assert result["summary"]["missed"] == 1
    assert result["goal_progress"][0]["name"] == "Russian B2"
    assert result["habit_progress"][0]["name"] == "Walking"
    assert result["habit_progress"][0]["current"] == 9420
    assert result["habit_progress"][0]["target"] == 10000

    other = execute_tool("u-2", "get_daily_report", {"date": "2026-09-16"})
    assert other["ok"] is True
    assert other["summary"]["completed"] == 1


def test_get_weekly_report_and_empty_report_are_safe(tmp_path, monkeypatch):
    db_path = tmp_path / "agent.db"
    monkeypatch.setattr(database, "DATABASE_PATH", str(db_path))
    database.init_database()

    _seed_user_data("u-1")

    weekly = execute_tool("u-1", "get_weekly_report", {"start_date": "2026-09-16"})
    assert weekly["ok"] is True
    assert weekly["summary"]["total_tasks"] >= 5
    assert weekly["bottlenecks"] is not None

    empty = execute_tool("u-999", "get_daily_report", {"date": "2026-09-16"})
    assert empty["ok"] is True
    assert empty["summary"]["completed"] == 0
    assert empty["summary"]["partial"] == 0
    assert empty["summary"]["missed"] == 0
    assert empty["goal_progress"] == []
    assert empty["habit_progress"] == []


def test_report_tools_and_analysis_return_real_data(tmp_path, monkeypatch):
    db_path = tmp_path / "agent.db"
    monkeypatch.setattr(database, "DATABASE_PATH", str(db_path))
    database.init_database()

    _seed_user_data("u-1")

    goal_result = execute_tool("u-1", "get_goal_progress", {})
    assert goal_result["ok"] is True
    assert goal_result["goals"][0]["name"] == "Russian B2"

    perf = execute_tool("u-1", "get_performance_analysis", {"days": 7})
    assert perf["ok"] is True
    assert "windows" in perf
    assert perf["windows"]

    bottleneck = execute_tool("u-1", "get_bottlenecks", {"days": 7})
    assert bottleneck["ok"] is True
    assert isinstance(bottleneck["bottlenecks"], list)


def test_report_tools_fail_honestly_when_data_missing(tmp_path, monkeypatch):
    db_path = tmp_path / "agent.db"
    monkeypatch.setattr(database, "DATABASE_PATH", str(db_path))
    database.init_database()

    bad = execute_tool("u-1", "get_daily_report", {"date": "not-a-date"})
    assert bad["ok"] is False
    assert "date" in bad["error"].lower()
