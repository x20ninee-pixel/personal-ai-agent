import sqlite3

from database import get_db

from zoneinfo import ZoneInfo


def get_or_create_user(user_id, name=None, telegram_chat_id=None):
    """
    Fetch the user's profile row, creating a default one on
    first contact (e.g. on /start or the first message ever).

    Internal domain user_id and Telegram chat_id are separate
    concepts and must be stored independently.
    """

    db = get_db()

    row = db.execute(
        "SELECT * FROM users WHERE user_id = ?",
        (user_id,),
    ).fetchone()

    if row:
        if telegram_chat_id is not None and row["telegram_chat_id"] != telegram_chat_id:
            db.execute(
                "UPDATE users SET telegram_chat_id = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                (telegram_chat_id, user_id),
            )
            db.commit()
            row = db.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        db.close()
        return row

    db.execute(
        """
        INSERT INTO users (user_id, name, telegram_chat_id)
        VALUES (?, ?, ?)
        """,
        (user_id, name, telegram_chat_id),
    )

    db.commit()

    row = db.execute(
        "SELECT * FROM users WHERE user_id = ?",
        (user_id,),
    ).fetchone()

    db.close()

    return row


def get_user_telegram_chat_id(user_id):
    db = get_db()
    try:
        row = db.execute(
            "SELECT telegram_chat_id FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        db.close()
        return None
    db.close()
    if row is None:
        return None
    value = row["telegram_chat_id"]
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_user_timezone(user_id):
    db = get_db()

    row = db.execute(
        "SELECT timezone FROM users WHERE user_id = ?",
        (user_id,),
    ).fetchone()

    db.close()

    if row and row["timezone"]:
        return row["timezone"]

    return "Asia/Tashkent"


def get_user_tzinfo(user_id):
    """
    Returns a ZoneInfo for the user, falling back to the
    default timezone if the user hasn't set one or hasn't
    been created yet. Callers use this instead of the
    single hardcoded config.TZ so scheduling is correct
    for any user, not just the original single-user setup.
    """

    try:
        return ZoneInfo(get_user_timezone(user_id))
    except Exception:
        from config import TZ
        return TZ


def update_user_profile(
    user_id,
    name=None,
    timezone=None,
    default_reminder_minutes=None,
    telegram_chat_id=None,
):
    fields = []
    values = []

    if name is not None:
        fields.append("name = ?")
        values.append(name)

    if timezone is not None:
        fields.append("timezone = ?")
        values.append(timezone)

    if default_reminder_minutes is not None:
        fields.append("default_reminder_minutes = ?")
        values.append(default_reminder_minutes)

    if telegram_chat_id is not None:
        fields.append("telegram_chat_id = ?")
        values.append(int(telegram_chat_id))

    if not fields:
        return

    fields.append("updated_at = CURRENT_TIMESTAMP")

    values.append(user_id)

    db = get_db()

    db.execute(
        f"UPDATE users SET {', '.join(fields)} WHERE user_id = ?",
        values,
    )

    db.commit()
    db.close()
