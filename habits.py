from datetime import datetime

from database import get_db
from config import TZ


def create_habit(user_id, name, target=None, unit=None, frequency="DAILY"):
    db = get_db()

    cursor = db.execute(
        """
        INSERT INTO habits (user_id, name, target, unit, frequency)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, name, target, unit, frequency),
    )

    habit_id = cursor.lastrowid

    db.commit()
    db.close()

    return habit_id


def get_habits(user_id, active_only=True):
    db = get_db()

    query = "SELECT * FROM habits WHERE user_id = ?"
    params = [user_id]

    if active_only:
        query += " AND active = 1"

    rows = db.execute(query, params).fetchall()

    db.close()

    return rows


def find_habit_by_name(user_id, name):
    db = get_db()

    row = db.execute(
        """
        SELECT * FROM habits
        WHERE user_id = ? AND active = 1
        AND LOWER(name) = LOWER(?)
        """,
        (user_id, name),
    ).fetchone()

    db.close()

    return row


def log_habit(habit_id, value, date=None):
    """
    Logs (or updates, if already logged today) a habit's
    value for a given date. INSERT OR REPLACE keeps this
    idempotent — logging "8000 steps" twice in one day
    updates the value rather than creating duplicates.
    """

    if date is None:
        date = datetime.now(TZ).date().isoformat()

    db = get_db()

    db.execute(
        """
        INSERT INTO habit_logs (habit_id, date, value)
        VALUES (?, ?, ?)
        ON CONFLICT(habit_id, date)
        DO UPDATE SET value = excluded.value
        """,
        (habit_id, date, value),
    )

    db.commit()
    db.close()


def get_habit_progress(habit_id, date=None):
    if date is None:
        date = datetime.now(TZ).date().isoformat()

    db = get_db()

    habit = db.execute(
        "SELECT * FROM habits WHERE id = ?",
        (habit_id,),
    ).fetchone()

    log = db.execute(
        """
        SELECT value FROM habit_logs
        WHERE habit_id = ? AND date = ?
        """,
        (habit_id, date),
    ).fetchone()

    db.close()

    if not habit:
        return None

    current = log["value"] if log else 0
    target = habit["target"] or 0

    percent = 0

    if target > 0:
        percent = min(round(current / target * 100, 1), 100)

    return {
        "habit": habit["name"],
        "unit": habit["unit"],
        "target": target,
        "current": current,
        "percent": percent,
        "date": date,
    }


def get_all_habit_progress(user_id, date=None):
    habits = get_habits(user_id)

    return [
        get_habit_progress(h["id"], date)
        for h in habits
    ]
