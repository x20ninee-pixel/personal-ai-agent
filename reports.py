from datetime import date, datetime, timedelta

from database import get_db
from goals import calculate_progress, get_goals
from habits import get_all_habit_progress
from tasks import parse_task_datetime


def _coerce_date(value, default=None):
    if value in (None, ""):
        if default is not None:
            return default
        raise ValueError("date is required")

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        try:
            return datetime.strptime(str(value), "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError(f"Invalid date: {value}") from exc


def _task_summary(tasks):
    summary = {
        "total": 0,
        "total_tasks": 0,
        "completed": 0,
        "partial": 0,
        "skipped": 0,
        "missed": 0,
        "rescheduled": 0,
    }
    for task in tasks:
        summary["total"] += 1
        summary["total_tasks"] += 1
        status = str(task["status"] if "status" in task.keys() else "")
        status = status.upper()
        if status == "COMPLETED":
            summary["completed"] += 1
        elif status == "PARTIAL":
            summary["partial"] += 1
        elif status == "SKIPPED":
            summary["skipped"] += 1
        elif status == "MISSED":
            summary["missed"] += 1
        reschedule_count = task["reschedule_count"] if "reschedule_count" in task.keys() else 0
        if int(reschedule_count or 0) > 0:
            summary["rescheduled"] += 1
    return summary


def get_daily_report(user_id, date_value=None):
    target_date = _coerce_date(date_value, default=datetime.now().date())

    db = get_db()
    rows = db.execute(
        """
        SELECT * FROM tasks
        WHERE user_id = ?
        AND due_date IS NOT NULL
        AND date(due_date) = ?
        ORDER BY due_date ASC
        """,
        (user_id, target_date.isoformat()),
    ).fetchall()
    db.close()

    summary = _task_summary(rows)
    goals = get_goals(user_id, status="ACTIVE")
    goal_progress = []
    for goal in goals:
        goal_progress.append(
            {
                "id": goal["id"],
                "name": goal["name"],
                "category": goal["category"],
                "target_value": goal["target_value"],
                "current_progress": goal["current_progress"],
                "unit": goal["unit"],
                "progress": calculate_progress(goal),
            }
        )

    habit_progress = []
    for habit in get_all_habit_progress(user_id, target_date.isoformat()):
        habit_progress.append({
            "id": habit.get("id"),
            "name": habit.get("habit") or habit.get("name"),
            "habit": habit.get("habit") or habit.get("name"),
            "unit": habit.get("unit"),
            "target": habit.get("target"),
            "current": habit.get("current"),
            "percent": habit.get("percent"),
            "date": habit.get("date"),
        })

    return {
        "ok": True,
        "date": target_date.isoformat(),
        "summary": summary,
        "tasks": [dict(r) for r in rows],
        "goal_progress": goal_progress,
        "habit_progress": habit_progress,
    }


def get_goal_progress(user_id):
    goals = get_goals(user_id, status="ACTIVE")
    data = []
    for goal in goals:
        data.append(
            {
                "id": goal["id"],
                "name": goal["name"],
                "category": goal["category"],
                "status": goal["status"],
                "current_progress": goal["current_progress"],
                "target_value": goal["target_value"],
                "unit": goal["unit"],
                "progress": calculate_progress(goal),
            }
        )
    return {"ok": True, "goals": data}


def get_performance_analysis(user_id, days=7):
    if days is None or int(days) <= 0:
        days = 7

    days = int(days)
    start_day = datetime.now().date() - timedelta(days=days - 1)
    db = get_db()
    rows = db.execute(
        """
        SELECT * FROM tasks
        WHERE user_id = ?
        AND due_date IS NOT NULL
        AND date(due_date) >= ?
        AND date(due_date) <= ?
        ORDER BY due_date ASC
        """,
        (user_id, start_day.isoformat(), datetime.now().date().isoformat()),
    ).fetchall()
    db.close()

    windows = {
        "morning": {"total": 0, "completed": 0, "partial": 0, "missed": 0},
        "afternoon": {"total": 0, "completed": 0, "partial": 0, "missed": 0},
        "evening": {"total": 0, "completed": 0, "partial": 0, "missed": 0},
    }

    for row in rows:
        try:
            dt = parse_task_datetime(row["due_date"], user_id=user_id)
        except Exception:
            continue
        if dt is None:
            continue
        hour = dt.hour
        if 5 <= hour < 12:
            bucket = "morning"
        elif 12 <= hour < 17:
            bucket = "afternoon"
        else:
            bucket = "evening"
        bucket_data = windows[bucket]
        bucket_data["total"] += 1
        status = (row["status"] or "").upper()
        if status == "COMPLETED":
            bucket_data["completed"] += 1
        elif status == "PARTIAL":
            bucket_data["partial"] += 1
        elif status == "MISSED":
            bucket_data["missed"] += 1

    output = []
    for name, bucket_data in windows.items():
        total = bucket_data["total"]
        if total == 0:
            output.append({
                "window": name,
                "total": 0,
                "completed": 0,
                "partial": 0,
                "missed": 0,
                "completion_rate": 0,
                "partial_rate": 0,
                "missed_rate": 0,
                "note": "Not enough data yet.",
            })
            continue
        output.append({
            "window": name,
            "total": total,
            "completed": bucket_data["completed"],
            "partial": bucket_data["partial"],
            "missed": bucket_data["missed"],
            "completion_rate": round(bucket_data["completed"] / total, 3),
            "partial_rate": round(bucket_data["partial"] / total, 3),
            "missed_rate": round(bucket_data["missed"] / total, 3),
            "note": None,
        })

    return {"ok": True, "days": days, "windows": output}


def get_bottlenecks(user_id, days=7):
    if days is None or int(days) <= 0:
        days = 7
    days = int(days)

    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days - 1)

    db = get_db()
    rows = db.execute(
        """
        SELECT category, status, reschedule_count
        FROM tasks
        WHERE user_id = ?
        AND due_date IS NOT NULL
        AND date(due_date) >= ?
        AND date(due_date) <= ?
        """,
        (user_id, start_date.isoformat(), end_date.isoformat()),
    ).fetchall()
    db.close()

    category_data = {}
    for row in rows:
        category = row["category"] or "GENERAL"
        category_data.setdefault(category, {"missed": 0, "rescheduled": 0})
        status = (row["status"] or "").upper()
        if status in {"MISSED", "SKIPPED"}:
            category_data[category]["missed"] += 1
        if (row["reschedule_count"] or 0) > 0:
            category_data[category]["rescheduled"] += 1

    bottlenecks = []
    for category, values in sorted(category_data.items(), key=lambda item: (item[1]["missed"], item[1]["rescheduled"]), reverse=True):
        missed = values["missed"]
        rescheduled = values["rescheduled"]
        if missed == 0 and rescheduled == 0:
            continue
        note = []
        if missed:
            note.append(f"{category} was missed {missed} times.")
        if rescheduled:
            note.append(f"{category} was rescheduled {rescheduled} times.")
        bottlenecks.append({
            "category": category,
            "missed": missed,
            "rescheduled": rescheduled,
            "note": " ".join(note),
        })

    return {"ok": True, "days": days, "bottlenecks": bottlenecks}


def get_weekly_report(user_id, start_date=None):
    if start_date is None:
        start_date = datetime.now().date().isoformat()

    try:
        start = _coerce_date(start_date)
    except ValueError:
        raise ValueError(f"Invalid date: {start_date}")

    end = start + timedelta(days=6)

    db = get_db()
    rows = db.execute(
        """
        SELECT * FROM tasks
        WHERE user_id = ?
        AND due_date IS NOT NULL
        AND date(due_date) >= ?
        AND date(due_date) <= ?
        ORDER BY due_date ASC
        """,
        (user_id, start.isoformat(), end.isoformat()),
    ).fetchall()
    db.close()

    summary = _task_summary(rows)
    summary["start_date"] = start.isoformat()
    summary["end_date"] = end.isoformat()

    habit_progress = []
    for habit in get_all_habit_progress(user_id, end.isoformat()):
        habit_progress.append({
            "id": habit.get("id"),
            "name": habit.get("habit") or habit.get("name"),
            "habit": habit.get("habit") or habit.get("name"),
            "unit": habit.get("unit"),
            "target": habit.get("target"),
            "current": habit.get("current"),
            "percent": habit.get("percent"),
            "date": habit.get("date"),
        })

    return {
        "ok": True,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "summary": summary,
        "tasks": [dict(r) for r in rows],
        "goal_progress": get_goal_progress(user_id)["goals"],
        "habit_progress": habit_progress,
        "performance": get_performance_analysis(user_id, days=7)["windows"],
        "bottlenecks": get_bottlenecks(user_id, days=7)["bottlenecks"],
    }
