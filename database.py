import sqlite3

from config import DATABASE_PATH

CURRENT_SCHEMA_VERSION = 3


MIGRATIONS = {}


def get_db():
    db = sqlite3.connect(DATABASE_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def _ensure_schema_migration_table(db):
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def get_schema_version():
    db = get_db()
    try:
        row = db.execute(
            "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
        ).fetchone()
        return int(row["version"]) if row else 0
    except Exception:
        return 0
    finally:
        db.close()


def add_column_if_missing(db, table, column, definition):
    columns = [
        row["name"]
        for row in db.execute(f"PRAGMA table_info({table})").fetchall()
    ]
    if column not in columns:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _record_schema_version(db, version):
    db.execute(
        "INSERT OR IGNORE INTO schema_migrations (version) VALUES (?)",
        (version,),
    )


def _migrate_v1(db):
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            memory TEXT NOT NULL,
            category TEXT DEFAULT 'important_context',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT DEFAULT 'PLANNED',
            priority TEXT DEFAULT 'MEDIUM',
            due_date TEXT,
            category TEXT DEFAULT 'GENERAL',
            estimated_minutes INTEGER,
            actual_minutes INTEGER,
            notes TEXT,
            scheduled_start TEXT,
            scheduled_end TEXT,
            reschedule_count INTEGER DEFAULT 0,
            recovery_deadline TEXT,
            recurring_task_id INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS task_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            notification_type TEXT NOT NULL,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(task_id, notification_type)
        )
        """
    )

    db.execute(
        """
        CREATE TRIGGER IF NOT EXISTS cleanup_task_reminders
        AFTER DELETE ON tasks
        BEGIN
            DELETE FROM reminders WHERE task_id = OLD.id;
            DELETE FROM task_notifications WHERE task_id = OLD.id;
        END;
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            date TEXT NOT NULL,
            planned_minutes INTEGER DEFAULT 0,
            completed_minutes INTEGER DEFAULT 0,
            tasks_completed INTEGER DEFAULT 0,
            tasks_missed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, date)
        )
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            category TEXT DEFAULT 'GENERAL',
            priority TEXT DEFAULT 'MEDIUM',
            status TEXT DEFAULT 'ACTIVE',
            description TEXT,
            target TEXT,
            current_progress REAL DEFAULT 0,
            target_value REAL,
            unit TEXT,
            deadline TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            name TEXT,
            timezone TEXT DEFAULT 'Asia/Tashkent',
            default_reminder_minutes INTEGER DEFAULT 10,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            task_id INTEGER,
            message TEXT,
            remind_at TEXT NOT NULL,
            status TEXT DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            days TEXT NOT NULL,
            notes TEXT,
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS recurring_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            days TEXT NOT NULL,
            time TEXT,
            estimated_minutes INTEGER,
            category TEXT DEFAULT 'GENERAL',
            priority TEXT DEFAULT 'MEDIUM',
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            unit TEXT,
            target REAL,
            frequency TEXT DEFAULT 'DAILY',
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS habit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            value REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(habit_id, date)
        )
        """
    )

    for table, column, definition in [
        ("tasks", "category", "TEXT DEFAULT 'GENERAL'"),
        ("tasks", "estimated_minutes", "INTEGER"),
        ("tasks", "actual_minutes", "INTEGER"),
        ("tasks", "notes", "TEXT"),
        ("tasks", "updated_at", "TIMESTAMP"),
        ("tasks", "scheduled_start", "TEXT"),
        ("tasks", "scheduled_end", "TEXT"),
        ("tasks", "reschedule_count", "INTEGER DEFAULT 0"),
        ("tasks", "recovery_deadline", "TEXT"),
        ("tasks", "recurring_task_id", "INTEGER"),
        ("goals", "description", "TEXT"),
        ("goals", "target", "TEXT"),
        ("goals", "current_progress", "REAL DEFAULT 0"),
        ("goals", "target_value", "REAL"),
        ("goals", "unit", "TEXT"),
        ("goals", "deadline", "TEXT"),
        ("memories", "category", "TEXT DEFAULT 'important_context'"),
    ]:
        add_column_if_missing(db, table, column, definition)

    db.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks(user_id, status)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_due_date ON tasks(user_id, due_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_reminders_user_status ON reminders(user_id, status)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_schedule_user_active ON schedule_events(user_id, active)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_recurring_user_active ON recurring_tasks(user_id, active)")


def _migrate_v2(db):
    db.execute("CREATE INDEX IF NOT EXISTS idx_task_notifications_task ON task_notifications(task_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_reminders_task_id ON reminders(task_id)")


def _migrate_v3(db):
    add_column_if_missing(db, "users", "telegram_chat_id", "INTEGER")
    db.execute("CREATE INDEX IF NOT EXISTS idx_users_telegram_chat_id ON users(telegram_chat_id)")


MIGRATIONS = {
    1: _migrate_v1,
    2: _migrate_v2,
    3: _migrate_v3,
}


def init_database():
    db = get_db()
    try:
        _ensure_schema_migration_table(db)
        current_version = get_schema_version()
        for version in sorted(MIGRATIONS):
            if version <= current_version:
                continue
            MIGRATIONS[version](db)
            _record_schema_version(db, version)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
