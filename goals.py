from database import get_db


GOAL_STATUSES = [
    "ACTIVE",
    "COMPLETED",
    "PAUSED",
    "CANCELLED",
]

PRIORITIES = [
    "LOW",
    "MEDIUM",
    "HIGH",
    "CRITICAL",
]


def create_goal(
    user_id,
    name,
    category="GENERAL",
    description=None,
    target=None,
    target_value=None,
    unit=None,
    deadline=None,
    priority="MEDIUM",
):
    db = get_db()

    cursor = db.execute(
        """
        INSERT INTO goals (
            user_id,
            name,
            category,
            description,
            target,
            target_value,
            unit,
            deadline,
            priority
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            name,
            category,
            description,
            target,
            target_value,
            unit,
            deadline,
            priority,
        ),
    )

    goal_id = cursor.lastrowid

    db.commit()
    db.close()

    return goal_id


def get_goals(user_id, status="ACTIVE"):
    db = get_db()

    rows = db.execute(
        """
        SELECT *
        FROM goals
        WHERE user_id = ?
        AND status = ?
        ORDER BY priority DESC, deadline ASC
        """,
        (user_id, status),
    ).fetchall()

    db.close()

    return rows


def get_goal(user_id, goal_id):
    db = get_db()

    row = db.execute(
        """
        SELECT *
        FROM goals
        WHERE user_id = ?
        AND id = ?
        """,
        (user_id, goal_id),
    ).fetchone()

    db.close()

    return row


def update_goal_progress(
    user_id,
    goal_id,
    current_progress,
):
    db = get_db()

    db.execute(
        """
        UPDATE goals
        SET current_progress = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
        AND id = ?
        """,
        (
            current_progress,
            user_id,
            goal_id,
        ),
    )

    db.commit()
    db.close()


def update_goal_status(
    user_id,
    goal_id,
    status,
):
    if status not in GOAL_STATUSES:
        raise ValueError(
            f"Invalid goal status: {status}"
        )

    db = get_db()

    db.execute(
        """
        UPDATE goals
        SET status = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
        AND id = ?
        """,
        (
            status,
            user_id,
            goal_id,
        ),
    )

    db.commit()
    db.close()


def calculate_progress(goal):
    target_value = goal["target_value"]
    current_progress = goal["current_progress"]

    if not target_value or target_value <= 0:
        return 0

    percentage = (
        current_progress / target_value
    ) * 100

    return min(
        round(percentage, 1),
        100,
    )


def format_goal(goal):
    progress = calculate_progress(goal)

    unit = goal["unit"] or ""

    deadline = goal["deadline"] or "No deadline"

    return (
        f"🎯 {goal['name']}\n"
        f"📂 {goal['category']}\n"
        f"📊 {goal['current_progress']} "
        f"/ {goal['target_value']} {unit}\n"
        f"📈 Progress: {progress}%\n"
        f"📅 Deadline: {deadline}\n"
        f"⚡ Priority: {goal['priority']}\n"
        f"🔵 Status: {goal['status']}"
    )