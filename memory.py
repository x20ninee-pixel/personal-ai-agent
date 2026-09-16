from database import get_db


def save_memory(user_id, memory):

    db = get_db()

    db.execute(
        """
        INSERT INTO memories (user_id, memory)
        VALUES (?, ?)
        """,
        (user_id, memory)
    )

    db.commit()
    db.close()


def get_memories(user_id, limit=20):

    db = get_db()

    rows = db.execute(
        """
        SELECT memory
        FROM memories
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (user_id, limit)
    ).fetchall()

    db.close()

    return [row[0] for row in rows]
    