import asyncio

import database
import reminders
from tasks import create_task, update_task_schedule, update_task_status


def test_init_database_is_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "agent.db"
    monkeypatch.setattr(database, "DATABASE_PATH", str(db_path))

    database.init_database()
    database.init_database()

    db = database.get_db()
    migrations = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    version = database.get_schema_version()
    db.close()

    assert migrations is not None
    assert version >= 2


def test_database_is_versioned_and_keeps_existing_data(tmp_path, monkeypatch):
    db_path = tmp_path / "agent.db"
    monkeypatch.setattr(database, "DATABASE_PATH", str(db_path))

    db = database.get_db()
    db.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY, user_id TEXT)")
    db.execute("INSERT INTO test_table (user_id) VALUES ('user-9')")
    db.commit()
    db.close()

    database.init_database()

    db = database.get_db()
    row = db.execute("SELECT user_id FROM test_table WHERE user_id = 'user-9'").fetchone()
    db.close()

    assert row is not None
    assert database.get_schema_version() >= 2


def test_task_notification_is_persisted_once(tmp_path, monkeypatch):
    db_path = tmp_path / "agent.db"
    monkeypatch.setattr(database, "DATABASE_PATH", str(db_path))
    database.init_database()

    task_id = create_task("u-1", "Test reminder task")
    reminders.mark_notification(task_id, "10_MINUTES")
    reminders.mark_notification(task_id, "10_MINUTES")

    db = database.get_db()
    count = db.execute(
        "SELECT COUNT(*) FROM task_notifications WHERE task_id = ? AND notification_type = '10_MINUTES'",
        (task_id,),
    ).fetchone()[0]
    db.close()

    assert count == 1


def test_completed_task_has_no_future_notifications(tmp_path, monkeypatch):
    db_path = tmp_path / "agent.db"
    monkeypatch.setattr(database, "DATABASE_PATH", str(db_path))
    database.init_database()

    task_id = create_task("u-1", "Done task")
    reminders.mark_notification(task_id, "10_MINUTES")
    reminders.mark_notification(task_id, "START")

    reminders.clear_task_notifications(task_id)

    db = database.get_db()
    remaining = db.execute(
        "SELECT COUNT(*) FROM task_notifications WHERE task_id = ?",
        (task_id,),
    ).fetchone()[0]
    db.close()

    assert remaining == 0


def test_reschedule_invalidates_old_task_notification_state(tmp_path, monkeypatch):
    db_path = tmp_path / "agent.db"
    monkeypatch.setattr(database, "DATABASE_PATH", str(db_path))
    database.init_database()

    task_id = create_task("u-1", "reschedule test")
    reminders.mark_notification(task_id, "10_MINUTES")
    reminders.mark_notification(task_id, "START")
    update_task_schedule("u-1", task_id, "2026-09-16T11:50:00+00:00", "2026-09-16T12:00:00+00:00")

    db = database.get_db()
    count = db.execute(
        "SELECT COUNT(*) FROM task_notifications WHERE task_id = ?",
        (task_id,),
    ).fetchone()[0]
    db.close()

    assert count == 0


def test_delete_task_invalidates_reminder_rows(tmp_path, monkeypatch):
    db_path = tmp_path / "agent.db"
    monkeypatch.setattr(database, "DATABASE_PATH", str(db_path))
    database.init_database()

    task_id = create_task("u-1", "delete test")
    reminder_id = reminders.create_reminder("u-1", "2026-09-16T12:00:00+00:00", "hello", task_id)
    reminders.mark_notification(task_id, "START")

    db = database.get_db()
    db.execute(
        "UPDATE reminders SET status = 'PENDING' WHERE id = ?",
        (reminder_id,),
    )
    db.commit()
    db.close()

    db = database.get_db()
    row = db.execute("SELECT COUNT(*) FROM reminders WHERE task_id = ? AND status = 'PENDING'", (task_id,)).fetchone()[0]
    db.close()
    assert row == 1

    db = database.get_db()
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    db.close()

    db = database.get_db()
    remaining = db.execute("SELECT COUNT(*) FROM reminders WHERE task_id = ? AND status = 'PENDING'", (task_id,)).fetchone()[0]
    db.close()
    assert remaining == 0


def test_reminder_engine_loop_survives_one_error(monkeypatch):
    class FakeBot:
        async def send_message(self, **kwargs):
            raise RuntimeError("boom")

    class FakeApp:
        def __init__(self):
            self.bot = FakeBot()

    app = FakeApp()
    task_id = create_task("u-1", "Reminder test")
    db = database.get_db()
    db.execute(
        "UPDATE tasks SET scheduled_start = ?, scheduled_end = ? WHERE id = ?",
        ("2026-09-16 11:50", "2026-09-16 12:00", task_id),
    )
    db.commit()
    db.close()

    async def run_once():
        await reminders.process_task_reminders(app, now=database.get_db().execute("SELECT datetime('now')").fetchone()[0])

    try:
        asyncio.run(run_once())
    except Exception:
        raise AssertionError("reminder processing should isolate task-level exceptions")
