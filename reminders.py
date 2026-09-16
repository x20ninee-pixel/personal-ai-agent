import asyncio
from datetime import datetime

from database import get_db
from config import TZ


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

    print("🔔 Reminder Engine tayyor!")

    while True:

        try:

            now = datetime.now(TZ)

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

                            print(
                                f"🔔 10 min: {title}"
                            )

                        except Exception as e:

                            print(
                                "10-minute reminder error:",
                                e
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

                            print(
                                f"🔥 START: {title}"
                            )

                        except Exception as e:

                            print(
                                "Start reminder error:",
                                e
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

                                print(
                                    f"🔴 MISSED: {title}"
                                )

                            except Exception as e:

                                print(
                                    "Missed notification error:",
                                    e
                                )

        except Exception as e:

            print(
                "Reminder Engine error:",
                e
            )

        await asyncio.sleep(30)