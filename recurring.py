from datetime import datetime

from database import get_db
from config import TZ
from schedule import WEEKDAY_CODES


def create_recurring_task(
    user_id,
    title,
    days,
    time=None,
    estimated_minutes=None,
    category="GENERAL",
    priority="MEDIUM",
):
    """
    days: comma-separated weekday codes ("MON,WED,FRI") or
    "DAILY".
    """

    db = get_db()

    cursor = db.execute(
        """
        INSERT INTO recurring_tasks
            (user_id, title, days, time, estimated_minutes,
             category, priority)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id, title, days, time, estimated_minutes,
            category, priority,
        ),
    )

    template_id = cursor.lastrowid

    db.commit()
    db.close()

    return template_id


def get_recurring_tasks(user_id, active_only=True):
    db = get_db()

    query = "SELECT * FROM recurring_tasks WHERE user_id = ?"
    params = [user_id]

    if active_only:
        query += " AND active = 1"

    rows = db.execute(query, params).fetchall()

    db.close()

    return rows


def ensure_recurring_tasks_for_today(user_id):
    """
    For every active recurring-task template that matches
    today's weekday, make sure a real "tasks" row exists for
    today. Idempotent: checks recurring_task_id + due date
    before inserting, so calling this repeatedly (e.g. every
    time today's tasks are fetched) never creates duplicates.
    """

    now = datetime.now(TZ)

    weekday_code = WEEKDAY_CODES[now.weekday()]
    today = now.date().isoformat()

    templates = get_recurring_tasks(user_id)

    db = get_db()

    created_ids = []

    for template in templates:

        days = (template["days"] or "").upper()

        if not (days == "DAILY" or weekday_code in days.split(",")):
            continue

        existing = db.execute(
            """
            SELECT id FROM tasks
            WHERE recurring_task_id = ?
            AND date(due_date) = ?
            """,
            (template["id"], today),
        ).fetchone()

        if existing:
            continue

        due_date = today

        if template["time"]:
            due_date = f"{today} {template['time']}"

        cursor = db.execute(
            """
            INSERT INTO tasks
                (user_id, title, priority, due_date, category,
                 estimated_minutes, recurring_task_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                template["title"],
                template["priority"],
                due_date,
                template["category"],
                template["estimated_minutes"],
                template["id"],
            ),
        )

        created_ids.append(cursor.lastrowid)

    db.commit()
    db.close()

    return created_ids
