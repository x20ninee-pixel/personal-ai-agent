import sqlite3

from config import DATABASE_PATH


def get_db():
    db = sqlite3.connect(
        DATABASE_PATH
    )

    db.row_factory = sqlite3.Row

    return db


def add_column_if_missing(
    db,
    table,
    column,
    definition,
):
    columns = [
        row["name"]
        for row in db.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()
    ]

    if column not in columns:

        db.execute(
            f"""
            ALTER TABLE {table}
            ADD COLUMN {column} {definition}
            """
        )


def init_database():

    db = get_db()

    # =====================================================
    # MEMORIES
    # =====================================================

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            memory TEXT NOT NULL,
            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


    # =====================================================
    # TASKS
    # =====================================================

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

            updated_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP,

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


    # =====================================================
    # TASK MIGRATIONS
    # =====================================================

    add_column_if_missing(
        db,
        "tasks",
        "category",
        "TEXT DEFAULT 'GENERAL'"
    )

    add_column_if_missing(
        db,
        "tasks",
        "estimated_minutes",
        "INTEGER"
    )

    add_column_if_missing(
        db,
        "tasks",
        "actual_minutes",
        "INTEGER"
    )

    add_column_if_missing(
        db,
        "tasks",
        "notes",
        "TEXT"
    )

    add_column_if_missing(
        db,
        "tasks",
        "updated_at",
        "TIMESTAMP"
    )

    add_column_if_missing(
        db,
        "tasks",
        "scheduled_start",
        "TEXT"
    )

    add_column_if_missing(
        db,
        "tasks",
        "scheduled_end",
        "TEXT"
    )

    add_column_if_missing(
        db,
        "tasks",
        "reschedule_count",
        "INTEGER DEFAULT 0"
    )

    # NEW
    add_column_if_missing(
        db,
        "tasks",
        "recovery_deadline",
        "TEXT"
    )


    # =====================================================
    # TASK NOTIFICATIONS
    # =====================================================

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS task_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            task_id INTEGER NOT NULL,

            notification_type TEXT NOT NULL,

            sent_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(
                task_id,
                notification_type
            )
        )
        """
    )


    # =====================================================
    # DAILY STATS
    # =====================================================

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

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(
                user_id,
                date
            )
        )
        """
    )


    # =====================================================
    # GOALS
    # =====================================================

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id TEXT NOT NULL,

            name TEXT NOT NULL,

            category TEXT DEFAULT 'GENERAL',

            priority TEXT DEFAULT 'MEDIUM',

            status TEXT DEFAULT 'ACTIVE',

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP,

            updated_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


    # =====================================================
    # GOAL MIGRATIONS
    #
    # These columns are written and read by goals.py but
    # were missing from the original CREATE TABLE above,
    # which made create_goal()/format_goal() crash on any
    # freshly-initialized database. Adding them here via
    # add_column_if_missing (same safe pattern used for
    # tasks) fixes new installs without touching existing
    # rows on databases that already had them.
    # =====================================================

    add_column_if_missing(
        db,
        "goals",
        "description",
        "TEXT"
    )

    add_column_if_missing(
        db,
        "goals",
        "target",
        "TEXT"
    )

    add_column_if_missing(
        db,
        "goals",
        "current_progress",
        "REAL DEFAULT 0"
    )

    add_column_if_missing(
        db,
        "goals",
        "target_value",
        "REAL"
    )

    add_column_if_missing(
        db,
        "goals",
        "unit",
        "TEXT"
    )

    add_column_if_missing(
        db,
        "goals",
        "deadline",
        "TEXT"
    )


    # =====================================================
    # MEMORY MIGRATIONS
    #
    # category: preference | schedule | goal | routine |
    #           important_context
    # =====================================================

    add_column_if_missing(
        db,
        "memories",
        "category",
        "TEXT DEFAULT 'important_context'"
    )


    # =====================================================
    # USERS
    # =====================================================

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,

            name TEXT,

            timezone TEXT DEFAULT 'Asia/Tashkent',

            default_reminder_minutes
                INTEGER DEFAULT 10,

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP,

            updated_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


    # =====================================================
    # REMINDERS
    #
    # Standalone reminders. Reminders attached to a task
    # are represented by task.scheduled_start (handled by
    # the existing task reminder logic in reminders.py);
    # this table is for explicit "remind me at X" requests
    # and for a configurable per-task lead time.
    # =====================================================

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id TEXT NOT NULL,

            task_id INTEGER,

            message TEXT,

            remind_at TEXT NOT NULL,

            status TEXT DEFAULT 'PENDING',

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


    # =====================================================
    # SCHEDULE EVENTS (fixed events: institute, classes...)
    # =====================================================

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

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


    # =====================================================
    # RECURRING TASK TEMPLATES
    #
    # A template row here generates one real "tasks" row
    # per matching day (see recurring.py). This keeps
    # recurrence explicit and prevents uncontrolled
    # duplicate generation.
    # =====================================================

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

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    add_column_if_missing(
        db,
        "tasks",
        "recurring_task_id",
        "INTEGER"
    )


    # =====================================================
    # HABITS
    # =====================================================

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

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP
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

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(habit_id, date)
        )
        """
    )


    db.commit()

    db.close()

    print(
        "✅ Database initialized"
    )