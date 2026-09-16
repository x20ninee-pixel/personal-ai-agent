from datetime import datetime, timedelta

from database import get_db
from config import TZ
from tasks import update_task_schedule


# =========================================================
# TODAY TASKS
# =========================================================

def get_today_tasks(user_id):

    today = datetime.now(TZ).date().isoformat()

    db = get_db()

    rows = db.execute(
        """
        SELECT *
        FROM tasks
        WHERE user_id = ?
        AND status NOT IN (
            'COMPLETED',
            'CANCELLED'
        )
        AND (
            due_date IS NULL
            OR date(due_date) = ?
            OR date(due_date) < ?
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
        (
            user_id,
            today,
            today,
        ),
    ).fetchall()

    db.close()

    return rows


# =========================================================
# TASK DURATION
# =========================================================

def get_task_minutes(task):

    if task["estimated_minutes"]:
        return int(task["estimated_minutes"])

    title = task["title"].lower()

    if "excel" in title:
        return 80

    if "gym" in title:
        return 70

    if "russian" in title:
        return 60

    if "lecture" in title:
        return 60

    if "walk" in title:
        return 60

    if "reminder" in title:
        return 30

    return 30


# =========================================================
# DATETIME PARSER
# =========================================================

def parse_datetime(value):

    if not value:
        return None

    try:

        dt = datetime.fromisoformat(value)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)

        return dt

    except Exception:

        return None


# =========================================================
# DEADLINE
# =========================================================

def get_deadline(task):

    return parse_datetime(
        task["due_date"]
    )


# =========================================================
# DEADLINE STATUS
# =========================================================

def get_deadline_status(
    task,
    scheduled_start,
    scheduled_end,
):

    deadline = get_deadline(task)

    if not deadline:
        return None

    now = datetime.now(TZ)

    # =====================================================
    # DEADLINE ALREADY PASSED
    # =====================================================

    if deadline < now:

        return "🔴 OVERDUE"

    # =====================================================
    # SCHEDULE ENDS AFTER DEADLINE
    # =====================================================

    if scheduled_end > deadline:

        return "🔴 DEADLINE CONFLICT"

    # =====================================================
    # LESS THAN 30 MIN BUFFER
    # =====================================================

    remaining = (
        deadline - scheduled_end
    ).total_seconds() / 60

    if remaining < 30:

        return "🟡 TIGHT DEADLINE"

    # =====================================================
    # SAFE
    # =====================================================

    return None


# =========================================================
# PRIORITY SCORE
# =========================================================

def priority_score(task):

    scores = {
        "CRITICAL": 100,
        "HIGH": 80,
        "MEDIUM": 50,
        "LOW": 20,
    }

    score = scores.get(
        task["priority"],
        50
    )

    deadline = get_deadline(task)

    if deadline:

        now = datetime.now(TZ)

        seconds_left = (
            deadline - now
        ).total_seconds()

        # Already overdue
        if seconds_left <= 0:

            score += 60

        # Less than 30 minutes
        elif seconds_left <= 1800:

            score += 50

        # Less than 2 hours
        elif seconds_left <= 7200:

            score += 30

        # Less than 6 hours
        elif seconds_left <= 21600:

            score += 15

        # Less than 24 hours
        elif seconds_left <= 86400:

            score += 5

    return score


# =========================================================
# RESET NOTIFICATIONS
# =========================================================

def reset_notifications(task_id):

    db = get_db()

    db.execute(
        """
        DELETE FROM task_notifications
        WHERE task_id = ?
        """,
        (task_id,),
    )

    db.commit()
    db.close()


# =========================================================
# SCHEDULE
# =========================================================

def schedule_tasks(
    user_id,
    tasks
):

    now = datetime.now(TZ)

    current_time = (
        now + timedelta(minutes=5)
    ).replace(
        second=0,
        microsecond=0
    )

    scheduled = []

    for task in tasks:

        duration = get_task_minutes(task)

        start = current_time

        end = (
            start
            + timedelta(
                minutes=duration
            )
        )

        deadline_status = get_deadline_status(
            task,
            start,
            end,
        )

        update_task_schedule(
            user_id,
            task["id"],
            start.isoformat(),
            end.isoformat(),
        )

        reset_notifications(
            task["id"]
        )

        scheduled.append({
            "task": task,
            "start": start,
            "end": end,
            "duration": duration,
            "deadline_status": deadline_status,
        })

        current_time = end

        if duration >= 60:

            current_time += timedelta(
                minutes=10
            )

    return scheduled


# =========================================================
# ADAPTIVE RESCHEDULE
# =========================================================

def build_reschedule_message(user_id):

    tasks = get_today_tasks(user_id)

    if not tasks:

        return (
            "🔄 ADAPTIVE RESCHEDULE\n\n"
            "Bugun task yo'q."
        )

    tasks = sorted(
        tasks,
        key=priority_score,
        reverse=True
    )

    scheduled = schedule_tasks(
        user_id,
        tasks
    )

    message = (
        "🔄 ADAPTIVE RESCHEDULE\n\n"
        f"⏰ Hozir: "
        f"{datetime.now(TZ).strftime('%H:%M')}\n\n"
        "📅 YANGI SCHEDULE:\n\n"
    )

    total_minutes = 0

    for index, item in enumerate(
        scheduled,
        1
    ):

        task = item["task"]

        start = item["start"]
        end = item["end"]

        duration = item["duration"]

        total_minutes += duration

        message += (
            f"{index}. {task['title']}\n"
            f"   🕐 "
            f"{start.strftime('%H:%M')}"
            f"–"
            f"{end.strftime('%H:%M')}\n"
            f"   ⏱️ {duration} min\n"
            f"   ⚡ {task['priority']}\n"
        )

        if task["due_date"]:

            deadline = get_deadline(task)

            message += (
                f"   ⏳ Deadline: "
                f"{deadline.strftime('%H:%M')}\n"
            )

        if item["deadline_status"]:

            message += (
                f"   {item['deadline_status']}\n"
            )

        message += "\n"

        if duration >= 60:

            message += (
                "   ☕ 10 min break\n\n"
            )

    hours = total_minutes // 60
    minutes = total_minutes % 60

    message += (
        "━━━━━━━━━━━━━━\n"
        f"📊 Total focused work: "
        f"{hours}h {minutes}min\n\n"
        "💾 Schedule saved.\n"
        "🔔 Reminderlar yangilandi."
    )

    return message


# =========================================================
# SMART PLAN
# =========================================================

def build_smart_plan(user_id):

    tasks = get_today_tasks(user_id)

    if not tasks:

        return (
            "🧠 SMART DAILY PLAN\n\n"
            "Bugun task yo'q."
        )

    tasks = sorted(
        tasks,
        key=priority_score,
        reverse=True
    )

    message = (
        "🧠 SMART DAILY PLAN\n\n"
        f"📅 "
        f"{datetime.now(TZ).strftime('%d.%m.%Y')}\n"
        f"⏰ Hozir: "
        f"{datetime.now(TZ).strftime('%H:%M')}\n\n"
    )

    total = 0

    for index, task in enumerate(
        tasks,
        1
    ):

        duration = get_task_minutes(task)

        total += duration

        message += (
            f"{index}. {task['title']}\n"
            f"   ⏱️ {duration} min\n"
            f"   ⚡ {task['priority']}\n"
        )

        if task["scheduled_start"]:

            start = parse_datetime(
                task["scheduled_start"]
            )

            end = parse_datetime(
                task["scheduled_end"]
            )

            message += (
                f"   🕐 "
                f"{start.strftime('%H:%M')}"
                f"–"
                f"{end.strftime('%H:%M')}\n"
            )

        message += "\n"

    hours = total // 60
    minutes = total % 60

    message += (
        "━━━━━━━━━━━━━━\n"
        f"⏱️ Workload: "
        f"{hours}h {minutes}min"
    )

    return message


# =========================================================
# TODAY
# =========================================================

def build_today_message(user_id):

    tasks = get_today_tasks(user_id)

    if not tasks:

        return (
            "📅 BUGUN\n\n"
            "Bugun task yo'q."
        )

    message = "📅 BUGUN\n\n"

    for task in tasks:

        icons = {
            "PLANNED": "⚪",
            "IN_PROGRESS": "🔵",
            "PARTIAL": "🟡",
            "COMPLETED": "🟢",
            "SKIPPED": "⏭️",
            "MISSED": "🔴",
        }

        icon = icons.get(
            task["status"],
            "⚪"
        )

        message += (
            f"{icon} #{task['id']} "
            f"{task['title']}\n"
            f"   Status: {task['status']}\n"
        )

        if task["scheduled_start"]:

            start = parse_datetime(
                task["scheduled_start"]
            )

            end = parse_datetime(
                task["scheduled_end"]
            )

            message += (
                f"   🕐 "
                f"{start.strftime('%H:%M')}"
                f"–"
                f"{end.strftime('%H:%M')}\n"
            )

        if task["due_date"]:

            deadline = get_deadline(task)

            message += (
                f"   ⏳ Deadline: "
                f"{deadline.strftime('%H:%M')}\n"
            )

        message += "\n"

    return message


# =========================================================
# STATS
# =========================================================

def get_today_stats(user_id):

    today = datetime.now(TZ).date().isoformat()

    db = get_db()

    planned = db.execute(
        """
        SELECT COUNT(*)
        FROM tasks
        WHERE user_id = ?
        AND (
            due_date IS NULL
            OR date(due_date) = ?
        )
        """,
        (
            user_id,
            today,
        ),
    ).fetchone()[0]

    completed = db.execute(
        """
        SELECT COUNT(*)
        FROM tasks
        WHERE user_id = ?
        AND status = 'COMPLETED'
        AND date(updated_at) = ?
        """,
        (
            user_id,
            today,
        ),
    ).fetchone()[0]

    db.close()

    rate = 0

    if planned:

        rate = round(
            completed / planned * 100,
            1
        )

    return {
        "planned": planned,
        "completed": completed,
        "completion_rate": rate,
    }