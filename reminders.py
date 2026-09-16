import asyncio
from datetime import datetime

from database import get_db
from config import TZ
from logger import get_logger


log = get_logger(__name__)


# =========================================================
# STANDALONE REMINDERS (create_reminder / cancel_reminder)
# =========================================================

def create_reminder(user_id, remind_at, message=None, task_id=None):
    """
    remind_at: ISO datetime string, timezone-aware or naive
    (naive is assumed to already be in the app timezone).
    """

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


async def check_standalone_reminders(application, now):
    """
    Fires any PENDING reminder whose remind_at has arrived.
    Called from the main reminder_engine loop so there is a
    single polling loop, not two competing ones.
    """

    db = get_db()

    due = db.execute(
        """
        SELECT * FROM reminders
        WHERE status = 'PENDING'
        AND remind_at <= ?
        """,
        (now.isoformat(),),
    ).fetchall()

    db.close()

    for reminder in due:

        try:

            text = reminder["message"] or "🔔 Eslatma"

            await application.bot.send_message(
                chat_id=int(reminder["user_id"]),
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


# =========================================================
# NOTIFICATION CHECK
# =========================================================

def notification_sent(
    task_id,
    notification_type
):

    db = get_db()

    row = db.execute(
        """
        SELECT id
        FROM task_notifications
        WHERE task_id = ?
        AND notification_type = ?
        """,
        (
            task_id,
            notification_type,
        ),
    ).fetchone()

    db.close()

    return row is not None


# =========================================================
# MARK NOTIFICATION
# =========================================================

def mark_notification(
    task_id,
    notification_type
):

    db = get_db()

    db.execute(
        """
        INSERT OR IGNORE INTO task_notifications (
            task_id,
            notification_type
        )
        VALUES (?, ?)
        """,
        (
            task_id,
            notification_type,
        ),
    )

    db.commit()
    db.close()


# =========================================================
# GET DATETIME
# =========================================================

def parse_datetime(value):

    if not value:
        return None

    try:

        dt = datetime.fromisoformat(value)

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=TZ
            )

        return dt

    except Exception:

        return None


# =========================================================
# REMINDER ENGINE
# =========================================================

async def reminder_engine(application):

    log.info("Reminder engine started")

    while True:

        try:

            now = datetime.now(TZ)

            await check_standalone_reminders(application, now)

            db = get_db()

            tasks = db.execute(
                """
                SELECT
                    id,
                    user_id,
                    title,
                    status,
                    scheduled_start,
                    scheduled_end
                FROM tasks
                WHERE scheduled_start IS NOT NULL
                AND status NOT IN (
                    'COMPLETED',
                    'CANCELLED',
                    'MISSED'
                )
                """
            ).fetchall()

            db.close()

            for task in tasks:

                task_id = task["id"]
                user_id = task["user_id"]
                title = task["title"]

                start = parse_datetime(
                    task["scheduled_start"]
                )

                end = parse_datetime(
                    task["scheduled_end"]
                )

                if not start or not end:
                    continue

                # =================================================
                # 10 MINUTES BEFORE
                # =================================================

                seconds_until_start = (
                    start - now
                ).total_seconds()

                if (
                    0
                    < seconds_until_start
                    <= 600
                ):

                    if not notification_sent(
                        task_id,
                        "10_MINUTES"
                    ):

                        try:

                            await application.bot.send_message(
                                chat_id=int(user_id),
                                text=(
                                    "🔔 10 DAQIQA QOLDI\n\n"
                                    f"📌 {title}\n"
                                    f"🕐 Boshlanish: "
                                    f"{start.strftime('%H:%M')}\n\n"
                                    "Tayyorgarlikni boshlang."
                                )
                            )

                            mark_notification(
                                task_id,
                                "10_MINUTES"
                            )

                            log.info(
                                "Sent 10-minute reminder: %s",
                                title,
                            )

                        except Exception:

                            log.error(
                                "10-minute reminder failed "
                                "for task %s",
                                task_id,
                                exc_info=True,
                            )

                # =================================================
                # START NOW
                # =================================================

                if (
                    -60
                    <= seconds_until_start
                    <= 0
                ):

                    if not notification_sent(
                        task_id,
                        "START"
                    ):

                        try:

                            await application.bot.send_message(
                                chat_id=int(user_id),
                                text=(
                                    "🔥 START NOW\n\n"
                                    f"📌 {title}\n"
                                    f"🕐 {start.strftime('%H:%M')}\n\n"
                                    "Ishni boshlang."
                                )
                            )

                            mark_notification(
                                task_id,
                                "START"
                            )

                            log.info(
                                "Sent start reminder: %s",
                                title,
                            )

                        except Exception:

                            log.error(
                                "Start reminder failed "
                                "for task %s",
                                task_id,
                                exc_info=True,
                            )

                # =================================================
                # TASK FINISHED -> MISSED CHECK
                # =================================================

                seconds_after_end = (
                    now - end
                ).total_seconds()

                if seconds_after_end > 60:

                    db = get_db()

                    current = db.execute(
                        """
                        SELECT status
                        FROM tasks
                        WHERE id = ?
                        """,
                        (task_id,),
                    ).fetchone()

                    db.close()

                    if not current:
                        continue

                    current_status = current["status"]

                    if current_status in (
                        "PLANNED",
                        "IN_PROGRESS",
                    ):

                        db = get_db()

                        db.execute(
                            """
                            UPDATE tasks
                            SET status = 'MISSED',
                                updated_at =
                                    CURRENT_TIMESTAMP
                            WHERE id = ?
                            """,
                            (task_id,),
                        )

                        db.commit()
                        db.close()

                        if not notification_sent(
                            task_id,
                            "MISSED"
                        ):

                            try:

                                await application.bot.send_message(
                                    chat_id=int(user_id),
                                    text=(
                                        "🔴 TASK MISSED\n\n"
                                        f"📌 {title}\n"
                                        f"🕐 Rejalashtirilgan: "
                                        f"{start.strftime('%H:%M')}"
                                        f"–"
                                        f"{end.strftime('%H:%M')}\n\n"
                                        "Nima bo'ldi?\n\n"
                                        "1️⃣ Vaqt yetmadi\n"
                                        "2️⃣ Energiya yo'q edi\n"
                                        "3️⃣ Muhimroq ish chiqdi\n"
                                        "4️⃣ Keyinroq qilaman\n"
                                        "5️⃣ Boshqa sabab"
                                    )
                                )

                                mark_notification(
                                    task_id,
                                    "MISSED"
                                )

                                log.info(
                                    "Marked task missed: %s",
                                    title,
                                )

                            except Exception:

                                log.error(
                                    "Missed notification "
                                    "failed for task %s",
                                    task_id,
                                    exc_info=True,
                                )

        except Exception:

            log.error(
                "Reminder engine loop error",
                exc_info=True,
            )

        await asyncio.sleep(30)