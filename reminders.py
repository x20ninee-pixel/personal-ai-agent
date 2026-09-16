import asyncio
from datetime import datetime

from config import TZ
from database import get_db
from logger import get_logger
from timezone_service import now_for_user, parse_user_datetime
from users import get_user_telegram_chat_id


log = get_logger(__name__)


def invalidate_task_reminders(task_id):
    db = get_db()
    try:
        db.execute(
            "DELETE FROM task_notifications WHERE task_id = ?",
            (task_id,),
        )
        db.execute(
            "UPDATE reminders SET status = 'CANCELLED' WHERE task_id = ? AND status = 'PENDING'",
            (task_id,),
        )
        db.commit()
    finally:
        db.close()


def parse_datetime(value, user_id=None):
    if not value:
        return None
    if user_id is not None:
        return parse_user_datetime(user_id, value)
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        return dt
    except Exception:
        return None


def create_reminder(user_id, remind_at, message=None, task_id=None):
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO reminders (user_id, task_id, message, remind_at)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, task_id, message, remind_at),
    )
    reminder_id = cursor.lastrowid
    db.commit()
    db.close()
    return reminder_id


def cancel_reminder(user_id, reminder_id):
    db = get_db()
    cursor = db.execute(
        """
        UPDATE reminders
        SET status = 'CANCELLED'
        WHERE user_id = ? AND id = ? AND status = 'PENDING'
        """,
        (user_id, reminder_id),
    )
    cancelled = cursor.rowcount > 0
    db.commit()
    db.close()
    return cancelled


def list_reminders(user_id, status="PENDING"):
    db = get_db()
    rows = db.execute(
        """
        SELECT * FROM reminders
        WHERE user_id = ? AND status = ?
        ORDER BY remind_at ASC
        """,
        (user_id, status),
    ).fetchall()
    db.close()
    return rows


def notification_sent(task_id, notification_type):
    db = get_db()
    row = db.execute(
        """
        SELECT id FROM task_notifications
        WHERE task_id = ? AND notification_type = ?
        """,
        (task_id, notification_type),
    ).fetchone()
    db.close()
    return row is not None


def mark_notification(task_id, notification_type):
    db = get_db()
    db.execute(
        """
        INSERT OR IGNORE INTO task_notifications (task_id, notification_type)
        VALUES (?, ?)
        """,
        (task_id, notification_type),
    )
    db.commit()
    db.close()


def clear_task_notifications(task_id):
    db = get_db()
    try:
        db.execute("DELETE FROM task_notifications WHERE task_id = ?", (task_id,))
        db.commit()
    finally:
        db.close()


async def check_standalone_reminders(application, now=None):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM reminders WHERE status = 'PENDING' ORDER BY remind_at ASC"
    ).fetchall()
    db.close()

    for reminder in rows:
        try:
            user_id = str(reminder["user_id"])
            chat_id = get_user_telegram_chat_id(user_id)
            if chat_id is None:
                continue
            reminder_time = parse_datetime(reminder["remind_at"], user_id=user_id)
            if reminder_time is None:
                continue
            now_for_row = parse_datetime(now, user_id=user_id) if now is not None else now_for_user(user_id)
            if reminder_time > now_for_row:
                continue

            text = reminder["message"] or "🔔 Eslatma"
            await application.bot.send_message(
                chat_id=chat_id,
                text=f"🔔 ESLATMA\n\n{text}",
            )

            db = get_db()
            db.execute(
                "UPDATE reminders SET status = 'SENT' WHERE id = ?",
                (reminder["id"],),
            )
            db.commit()
            db.close()
            log.info("Sent standalone reminder id=%s", reminder["id"])
        except Exception:
            log.error(
                "Standalone reminder failed id=%s",
                reminder["id"],
                exc_info=True,
            )


async def process_task_reminders(application, now=None):
    db = get_db()
    tasks = db.execute(
        """
        SELECT id, user_id, title, status, scheduled_start, scheduled_end
        FROM tasks
        WHERE scheduled_start IS NOT NULL
        AND status NOT IN ('COMPLETED', 'CANCELLED', 'MISSED', 'SKIPPED')
        ORDER BY scheduled_start ASC
        """
    ).fetchall()
    db.close()

    for task in tasks:
        task_id = task["id"]
        user_id = str(task["user_id"])
        chat_id = get_user_telegram_chat_id(user_id)
        title = task["title"]
        try:
            if chat_id is None:
                continue
            task_now = parse_datetime(now, user_id=user_id) if now is not None else now_for_user(user_id)
            start = parse_datetime(task["scheduled_start"], user_id=user_id)
            end = parse_datetime(task["scheduled_end"], user_id=user_id)
            if not start or not end:
                continue

            seconds_until_start = (start - task_now).total_seconds()

            if 0 < seconds_until_start <= 600 and not notification_sent(task_id, "10_MINUTES"):
                await application.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "🔔 10 DAQIQA QOLDI\n\n"
                        f"📌 {title}\n"
                        f"🕐 Boshlanish: {start.strftime('%H:%M')}\n\n"
                        "Tayyorgarlikni boshlang."
                    ),
                )
                mark_notification(task_id, "10_MINUTES")
                log.info("Sent 10-minute reminder: %s", title)

            if -60 <= seconds_until_start <= 0 and not notification_sent(task_id, "START"):
                await application.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "🔥 START NOW\n\n"
                        f"📌 {title}\n"
                        f"🕐 {start.strftime('%H:%M')}\n\n"
                        "Ishni boshlang."
                    ),
                )
                mark_notification(task_id, "START")
                log.info("Sent start reminder: %s", title)

            seconds_after_end = (task_now - end).total_seconds()
            if seconds_after_end > 60:
                current = get_db().execute(
                    "SELECT status FROM tasks WHERE id = ?",
                    (task_id,),
                ).fetchone()
                if current is not None and current["status"] in ("PLANNED", "IN_PROGRESS"):
                    db2 = get_db()
                    db2.execute(
                        "UPDATE tasks SET status = 'MISSED', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (task_id,),
                    )
                    db2.commit()
                    db2.close()
                    if not notification_sent(task_id, "MISSED"):
                        await application.bot.send_message(
                            chat_id=chat_id,
                            text=(
                                "🔴 TASK MISSED\n\n"
                                f"📌 {title}\n"
                                f"🕐 Rejalashtirilgan: {start.strftime('%H:%M')} - {end.strftime('%H:%M')}\n\n"
                                "Nima bo'ldi?"
                            ),
                        )
                        mark_notification(task_id, "MISSED")
                        log.info("Marked task missed: %s", title)

        except Exception:
            log.error(
                "Task reminder failed for task %s user=%s",
                task_id,
                user_id,
                exc_info=True,
            )


async def reminder_engine(application):
    log.info("Reminder engine started")
    while True:
        try:
            await check_standalone_reminders(application)
            await process_task_reminders(application)
        except Exception:
            log.error("Reminder engine loop error", exc_info=True)
        await asyncio.sleep(30)
