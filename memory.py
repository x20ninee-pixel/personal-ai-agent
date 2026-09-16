from database import get_db


VALID_CATEGORIES = [
    "preference",
    "schedule",
    "goal",
    "routine",
    "important_context",
]


def save_memory(user_id, memory, category="important_context"):

    if category not in VALID_CATEGORIES:
        category = "important_context"

    db = get_db()

    db.execute(
        """
        INSERT INTO memories (user_id, memory, category)
        VALUES (?, ?, ?)
        """,
        (user_id, memory, category)
    )

    db.commit()
    db.close()


def get_memories(user_id, limit=20):
    """Plain text list -- kept for backward compatibility."""

    return [
        row["memory"]
        for row in list_memories(user_id, limit)
    ]


def list_memories(user_id, limit=20):
    """Full rows (with id + category) so a memory can be
    identified and deleted individually."""

    db = get_db()

    rows = db.execute(
        """
        SELECT id, memory, category
        FROM memories
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (user_id, limit)
    ).fetchall()

    db.close()

    return rows


def delete_memory(user_id, memory_id):
    db = get_db()

    cursor = db.execute(
        """
        DELETE FROM memories
        WHERE user_id = ? AND id = ?
        """,
        (user_id, memory_id)
    )

    deleted = cursor.rowcount > 0

    db.commit()
    db.close()

    return deleted
