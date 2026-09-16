import asyncio

import database
import reminders
from tasks import create_task
from users import get_or_create_user


class FakeBot:
    def __init__(self):
        self.calls = []

    async def send_message(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True}


class FakeApp:
    def __init__(self):
        self.bot = FakeBot()


def _make_user(user_id, telegram_chat_id=None):
    get_or_create_user(user_id, name="Tester", telegram_chat_id=telegram_chat_id)


def test_get_or_create_user_persists_telegram_chat_id(tmp_path, monkeypatch):
    db_path = tmp_path / "agent.db"
    monkeypatch.setattr(database, "DATABASE_PATH", str(db_path))
    database.init_database()

    user = get_or_create_user("u-1", name="Alice", telegram_chat_id=123456)

    assert user["user_id"] == "u-1"
    assert user["telegram_chat_id"] == 123456


def test_process_task_reminders_uses_user_telegram_chat_id(tmp_path, monkeypatch):
    db_path = tmp_path / "agent.db"
    monkeypatch.setattr(database, "DATABASE_PATH", str(db_path))
    database.init_database()
    _make_user("u-1", 987654321)

    task_id = create_task("u-1", "Excel lesson")
    db = database.get_db()
    now = "2026-09-16 09:00:00"
    db.execute(
        "UPDATE tasks SET scheduled_start = ?, scheduled_end = ? WHERE id = ?",
        (f"{now}", "2026-09-16 10:20:00", task_id),
    )
    db.commit()
    db.close()

    app = FakeApp()

    async def run():
        await reminders.process_task_reminders(app, now=now)

    asyncio.run(run())

    assert app.bot.calls
    assert app.bot.calls[0]["chat_id"] == 987654321


def test_process_task_reminders_skips_missing_telegram_chat_id(tmp_path, monkeypatch):
    db_path = tmp_path / "agent.db"
    monkeypatch.setattr(database, "DATABASE_PATH", str(db_path))
    database.init_database()
    _make_user("u-1", None)

    task_id = create_task("u-1", "Russian lesson")
    db = database.get_db()
    db.execute(
        "UPDATE tasks SET scheduled_start = ?, scheduled_end = ? WHERE id = ?",
        ("2026-09-16 09:00:00", "2026-09-16 09:45:00", task_id),
    )
    db.commit()
    db.close()

    app = FakeApp()

    async def run():
        await reminders.process_task_reminders(app, now="2026-09-16 09:00:00")

    asyncio.run(run())

    assert app.bot.calls == []


def test_task_reminders_are_user_scoped(tmp_path, monkeypatch):
    db_path = tmp_path / "agent.db"
    monkeypatch.setattr(database, "DATABASE_PATH", str(db_path))
    database.init_database()
    _make_user("u-1", 111)
    _make_user("u-2", 222)

    task_id_1 = create_task("u-1", "User one task")
    task_id_2 = create_task("u-2", "User two task")
    db = database.get_db()
    db.execute(
        "UPDATE tasks SET scheduled_start = ?, scheduled_end = ? WHERE id = ?",
        ("2026-09-16 09:00:00", "2026-09-16 09:45:00", task_id_1),
    )
    db.execute(
        "UPDATE tasks SET scheduled_start = ?, scheduled_end = ? WHERE id = ?",
        ("2026-09-16 09:00:00", "2026-09-16 09:45:00", task_id_2),
    )
    db.commit()
    db.close()

    app = FakeApp()

    async def run():
        await reminders.process_task_reminders(app, now="2026-09-16 09:00:00")

    asyncio.run(run())

    assert [call["chat_id"] for call in app.bot.calls] == [111, 222]


def test_check_standalone_reminder_uses_telegram_chat_id(tmp_path, monkeypatch):
    db_path = tmp_path / "agent.db"
    monkeypatch.setattr(database, "DATABASE_PATH", str(db_path))
    database.init_database()
    _make_user("u-1", 44444)

    reminder_id = reminders.create_reminder("u-1", "2026-09-16 09:00:00", "hello")
    db = database.get_db()
    db.execute("UPDATE reminders SET status = 'PENDING' WHERE id = ?", (reminder_id,))
    db.commit()
    db.close()

    app = FakeApp()

    async def run():
        await reminders.check_standalone_reminders(app, now="2026-09-16 09:00:00")

    asyncio.run(run())

    assert app.bot.calls[0]["chat_id"] == 44444
