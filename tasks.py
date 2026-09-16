from datetime import datetime

from database import get_db
from timezone_service import now_for_user, parse_user_datetime


# =========================================================
# CONSTANTS
# =========================================================

TASK_STATUSES = [
    "PLANNED",
    "IN_PROGRESS",
    "COMPLETED",
    "PARTIAL",
    "POSTPONED",
    "SKIPPED",
    "MISSED",
    "CANCELLED",
]


PRIORITIES = [
    "LOW",
    "MEDIUM",
    "HIGH",
    "CRITICAL",
]


# =========================================================
# CREATE TASK
# =========================================================

def create_task(
    user_id,
    title,
    priority="MEDIUM",
    due_date=None,
    category="GENERAL",
    estimated_minutes=None,
):

    db = get_db()

    cursor = db.execute(
        """
        INSERT INTO tasks (
            user_id,
            title,
            priority,
            due_date,
            category,
            estimated_minutes
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            title,
            priority,
            due_date,
            category,
            estimated_minutes,
        ),
    )

    task_id = cursor.lastrowid

    db.commit()
    db.close()

    return task_id


# =========================================================
# GET TASKS
# =========================================================

def get_tasks(user_id):

    db = get_db()

    rows = db.execute(
        """
        SELECT *
        FROM tasks

        WHERE user_id = ?

        ORDER BY
            CASE status

                WHEN 'IN_PROGRESS' THEN 1

                WHEN 'PLANNED' THEN 2

                WHEN 'PARTIAL' THEN 3

                WHEN 'POSTPONED' THEN 4

                WHEN 'MISSED' THEN 5

                WHEN 'SKIPPED' THEN 6

                WHEN 'COMPLETED' THEN 7

                ELSE 8

            END,

            due_date ASC,

            id DESC
        """,
        (user_id,),
    ).fetchall()

    db.close()

    return rows


# =========================================================
# GET SINGLE TASK
# =========================================================

def get_task(
    user_id,
    task_id,
):

    db = get_db()

    row = db.execute(
        """
        SELECT *
        FROM tasks

        WHERE user_id = ?
        AND id = ?
        """,
        (
            user_id,
            task_id,
        ),
    ).fetchone()

    db.close()

    return row


# =========================================================
# PARSE DATETIME
# =========================================================

def parse_task_datetime(value, user_id=None):

    if user_id is not None:
        return parse_user_datetime(user_id, value)

    if not value:
        return None

    try:
        value = value.strip()
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=now_for_user("system").tzinfo)
        return dt.astimezone(now_for_user("system").tzinfo)
    except ValueError:
        pass

    formats = [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=now_for_user("system").tzinfo)
        except ValueError:
            continue

    return None


# =========================================================
# GET OVERDUE TASKS
# =========================================================

def get_overdue_tasks(user_id):

    db = get_db()

    rows = db.execute(
        """
        SELECT *
        FROM tasks

        WHERE user_id = ?

        AND due_date IS NOT NULL

        AND status NOT IN (
            'COMPLETED',
            'CANCELLED'
        )

        ORDER BY
            CASE priority

                WHEN 'CRITICAL' THEN 1

                WHEN 'HIGH' THEN 2

                WHEN 'MEDIUM' THEN 3

                WHEN 'LOW' THEN 4

                ELSE 5

            END,

            due_date ASC
        """,
        (user_id,),
    ).fetchall()

    db.close()


    # =====================================================
    # PYTHON TIMEZONE CHECK
    # =====================================================

    now = now_for_user(user_id)

    overdue = []

    for task in rows:

        deadline = parse_task_datetime(
            task["due_date"], user_id=user_id
        )

        if not deadline:
            continue

        if deadline < now:

            overdue.append(task)

    return overdue


# =========================================================
# UPDATE STATUS
# =========================================================

def update_task_status(
    user_id,
    task_id,
    status,
):

    if status not in TASK_STATUSES:

        raise ValueError(
            f"Invalid task status: {status}"
        )

    db = get_db()

    db.execute(
        """
        UPDATE tasks

        SET status = ?,

            updated_at =
                CURRENT_TIMESTAMP

        WHERE user_id = ?
        AND id = ?
        """,
        (
            status,
            user_id,
            task_id,
        ),
    )

    db.commit()
    db.close()


# =========================================================
# UPDATE ORIGINAL DEADLINE
# =========================================================

def update_task_time(
    user_id,
    task_id,
    due_date,
):

    db = get_db()

    db.execute(
        """
        UPDATE tasks

        SET due_date = ?,

            updated_at =
                CURRENT_TIMESTAMP

        WHERE user_id = ?
        AND id = ?
        """,
        (
            due_date,
            user_id,
            task_id,
        ),
    )

    db.commit()
    db.close()


def update_task_fields(user_id, task_id, **changes):
    """Update allowed task fields for one owned task."""

    task = get_task(user_id, task_id)

    if task is None:
        raise KeyError(f"Task {task_id} not found")

    allowed_fields = {
        "title",
        "priority",
        "notes",
    }

    updates = {}

    for key in allowed_fields:
        if key in changes and changes[key] is not None:
            updates[key] = changes[key]

    if not updates:
        return task

    db = get_db()

    fields = []
    values = []

    for key in ("title", "priority", "notes"):
        if key in updates:
            fields.append(f"{key} = ?")
            values.append(updates[key])

    fields.append("updated_at = CURRENT_TIMESTAMP")
    values.extend([user_id, task_id])

    db.execute(
        f"UPDATE tasks SET {', '.join(fields)} WHERE user_id = ? AND id = ?",
        values,
    )

    db.commit()
    db.close()

    return get_task(user_id, task_id)


# =========================================================
# UPDATE RECOVERY DEADLINE
# =========================================================

def update_recovery_deadline(
    user_id,
    task_id,
    recovery_deadline,
):

    db = get_db()

    db.execute(
        """
        UPDATE tasks

        SET recovery_deadline = ?,

            updated_at =
                CURRENT_TIMESTAMP

        WHERE user_id = ?
        AND id = ?
        """,
        (
            recovery_deadline,
            user_id,
            task_id,
        ),
    )

    db.commit()
    db.close()


# =========================================================
# UPDATE SCHEDULE
# =========================================================

def update_task_schedule(
    user_id,
    task_id,
    scheduled_start,
    scheduled_end,
):

    db = get_db()

    db.execute(
        """
        UPDATE tasks

        SET scheduled_start = ?,

            scheduled_end = ?,

            updated_at =
                CURRENT_TIMESTAMP,

            reschedule_count =
                COALESCE(
                    reschedule_count,
                    0
                ) + 1

        WHERE user_id = ?
        AND id = ?
        """,
        (
            scheduled_start,
            scheduled_end,
            user_id,
            task_id,
        ),
    )

    db.commit()
    db.close()


# =========================================================
# CLEAR SCHEDULE
# =========================================================

def clear_task_schedule(
    user_id,
    task_id,
):

    db = get_db()

    db.execute(
        """
        UPDATE tasks

        SET scheduled_start = NULL,

            scheduled_end = NULL,

            updated_at =
                CURRENT_TIMESTAMP

        WHERE user_id = ?
        AND id = ?
        """,
        (
            user_id,
            task_id,
        ),
    )

    db.commit()
    db.close()


# =========================================================
# DELETE TASK
# =========================================================

def delete_task(
    user_id,
    task_id,
):

    db = get_db()

    db.execute(
        """
        DELETE FROM task_notifications

        WHERE task_id = ?
        """,
        (task_id,),
    )

    db.execute(
        """
        DELETE FROM tasks

        WHERE user_id = ?
        AND id = ?
        """,
        (
            user_id,
            task_id,
        ),
    )

    db.commit()
    db.close()