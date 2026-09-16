from datetime import datetime
from zoneinfo import ZoneInfo

from config import TZ
from database import get_db


def _normalize_timezone(name):
    candidate = (name or str(TZ)).strip()
    if not candidate:
        return TZ
    try:
        return ZoneInfo(candidate)
    except Exception:
        return TZ


def get_user_timezone(user_id):
    if not user_id:
        return str(TZ)

    try:
        db = get_db()
        row = db.execute(
            "SELECT timezone FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        db.close()
    except Exception:
        return str(TZ)

    tz_name = row["timezone"] if row and row["timezone"] else None
    if not tz_name:
        return str(TZ)

    try:
        ZoneInfo(tz_name)
        return tz_name
    except Exception:
        return str(TZ)


def get_user_tzinfo(user_id):
    return _normalize_timezone(get_user_timezone(user_id))


def now_for_user(user_id):
    return datetime.now(get_user_tzinfo(user_id))


def parse_user_datetime(user_id, value):
    if value is None or value == "":
        return None

    tz = get_user_tzinfo(user_id)

    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            return dt.replace(tzinfo=tz)
        return dt.astimezone(tz)

    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None

    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)

    return dt.astimezone(tz)


def format_user_datetime(user_id, value):
    dt = parse_user_datetime(user_id, value)
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%d %H:%M %Z")


def _coerce_dt(value, fallback_tz=None):
    tz = fallback_tz or TZ

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=tz)
        return value.astimezone(tz)

    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None

    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)

    return dt.astimezone(tz)


def events_overlap(start1, end1, start2, end2):
    a1 = _coerce_dt(start1, TZ)
    a2 = _coerce_dt(end1, TZ)
    b1 = _coerce_dt(start2, TZ)
    b2 = _coerce_dt(end2, TZ)

    if a1 is None or a2 is None or b1 is None or b2 is None:
        return False

    if a2 <= a1 or b2 <= b1:
        return False

    return a1 < b2 and b1 < a2
