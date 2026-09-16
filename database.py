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

            progress REAL DEFAULT 0,

            status TEXT DEFAULT 'ACTIVE',

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP,

            updated_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


    db.commit()

    db.close()

    print(
        "✅ Database initialized"
    )