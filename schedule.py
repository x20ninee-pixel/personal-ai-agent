from datetime import datetime, time

from database import get_db
from timezone_service import get_user_tzinfo


WEEKDAY_CODES = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


def _to_datetime(value, tzinfo=None):
    if isinstance(value, datetime):
        if value.tzinfo is None and tzinfo is not None:
            return value.replace(tzinfo=tzinfo)
        return value.astimezone(tzinfo) if tzinfo is not None else value

    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None

    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            dt = datetime.strptime(text, "%Y-%m-%d %H:%M")
        except ValueError:
            return None

    if dt.tzinfo is None and tzinfo is not None:
        dt = dt.replace(tzinfo=tzinfo)

    if tzinfo is not None and dt.tzinfo is not None:
        return dt.astimezone(tzinfo)

    return dt


def events_overlap(start1, end1, start2, end2):
    a1 = _to_datetime(start1)
    a2 = _to_datetime(end1)
    b1 = _to_datetime(start2)
    b2 = _to_datetime(end2)

    if a1 is None or a2 is None or b1 is None or b2 is None:
        return False

    if a2 <= a1 or b2 <= b1:
        return False

    return a1 < b2 and b1 < a2


def _event_for_date(user_id, event, target_date):
    tz = get_user_tzinfo(user_id)

    try:
        start = datetime.combine(target_date, time.fromisoformat(event["start_time"]), tzinfo=tz)
        end = datetime.combine(target_date, time.fromisoformat(event["end_time"]), tzinfo=tz)
    except Exception:
        return None

    if end <= start:
        end = end + __import__("datetime").timedelta(days=1)

    return start, end


def get_events_for_date(user_id, target_date):
    events = get_schedule_events(user_id)
    weekday_code = WEEKDAY_CODES[target_date.weekday()]
    matches = []

    for event in events:
        if event.get("active") not in (None, 1, True):
            continue

        days = (event.get("days") or "").upper()
        if days == "DAILY" or weekday_code in days.split(","):
            window = _event_for_date(user_id, event, target_date)
            if window is not None:
                matches.append((event, window[0], window[1]))

    return matches


def create_schedule_event(
    user_id, title, start_time, end_time, days, notes=None
):
    """
    days: comma-separated weekday codes, e.g. "MON,WED,FRI",
    or "DAILY" for every day.
    start_time / end_time: "HH:MM" strings (the event repeats
    at this time on each matching day).
    """

    db = get_db()

    cursor = db.execute(
        """
        INSERT INTO schedule_events
            (user_id, title, start_time, end_time, days, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, title, start_time, end_time, days, notes),
    )

    event_id = cursor.lastrowid

    db.commit()
    db.close()

    return event_id


def get_schedule_events(user_id, active_only=True):
    db = get_db()

    query = "SELECT * FROM schedule_events WHERE user_id = ?"
    params = [user_id]

    if active_only:
        query += " AND active = 1"

    rows = db.execute(query, params).fetchall()

    db.close()

    return rows


def get_events_for_weekday(user_id, weekday_code):
    """weekday_code: one of WEEKDAY_CODES, e.g. 'MON'."""

    events = get_schedule_events(user_id)

    matching = []

    for event in events:
        days = (event["days"] or "").upper()

        if days == "DAILY" or weekday_code in days.split(","):
            matching.append(event)

    return matching


def delete_schedule_event(user_id, event_id):
    db = get_db()

    db.execute(
        """
        DELETE FROM schedule_events
        WHERE user_id = ? AND id = ?
        """,
        (user_id, event_id),
    )

    db.commit()
    db.close()
