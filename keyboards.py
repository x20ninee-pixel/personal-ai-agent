from telegram import InlineKeyboardButton, InlineKeyboardMarkup


CALLBACK_PREFIX = "t"
MAX_CALLBACK_DATA = 64


def _callback(action, task_id, option=None):
    parts = [CALLBACK_PREFIX, action, str(task_id)]
    if option is not None:
        parts.append(option)
    data = ":".join(parts)
    if len(data.encode("utf-8")) > MAX_CALLBACK_DATA:
        raise ValueError("Callback data exceeds Telegram's 64-byte limit")
    return data


def build_task_keyboard(task_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Done", callback_data=_callback("done", task_id)),
            InlineKeyboardButton("⏸ Partial", callback_data=_callback("partial", task_id)),
        ],
        [
            InlineKeyboardButton("🔄 Reschedule", callback_data=_callback("rmenu", task_id)),
            InlineKeyboardButton("❌ Skip", callback_data=_callback("skip", task_id)),
        ],
    ])


def build_reschedule_keyboard(task_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📅 Today", callback_data=_callback("resched", task_id, "today")),
            InlineKeyboardButton("➡️ Tomorrow", callback_data=_callback("resched", task_id, "tomorrow")),
        ],
        [
            InlineKeyboardButton("⚡ Short", callback_data=_callback("resched", task_id, "short")),
            InlineKeyboardButton("❌ Cancel", callback_data=_callback("resched", task_id, "cancel")),
        ],
    ])


def parse_callback_data(data):
    if not data or not isinstance(data, str):
        raise ValueError("Empty callback data")

    parts = data.split(":")
    if len(parts) not in (3, 4) or parts[0] != CALLBACK_PREFIX:
        raise ValueError("Invalid callback data")

    try:
        task_id = int(parts[2])
    except (TypeError, ValueError):
        raise ValueError("Invalid task id") from None

    action = parts[1]
    allowed_actions = {"done", "partial", "skip", "cancel", "delete", "rmenu", "resched"}
    if action not in allowed_actions:
        raise ValueError("Unknown action")

    option = None
    if action == "resched":
        if len(parts) != 4 or parts[3] not in {"today", "tomorrow", "short", "cancel"}:
            raise ValueError("Unknown reschedule option")
        option = parts[3]
    elif len(parts) != 3:
        raise ValueError("Unexpected callback option")

    return action, task_id, option
