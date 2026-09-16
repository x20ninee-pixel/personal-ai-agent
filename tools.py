"""
Tool layer for the personal AI agent.

Design rules (do not violate these):
- Claude only ever sees TOOLS (JSON schemas) and gets back
  whatever execute_tool() returns as a plain dict.
- execute_tool() is the single choke point between the model
  and the database. No tool accepts raw SQL or code.
- Every tool is scoped to the calling user_id -- it is passed
  in by the agent loop, never trusted from the model's input,
  so one user's tool calls can never touch another user's data.
- A tool result always has an "ok" boolean. The agent must
  never claim an action succeeded if ok is False.
"""

from tasks import (
    create_task as _create_task,
    get_tasks,
    get_task,
    get_overdue_tasks as _get_overdue_tasks,
    update_task_status,
    update_task_time,
    update_task_fields,
    delete_task as _delete_task,
    TASK_STATUSES,
)
from planner import get_today_tasks as _get_today_tasks
from reminders import (
    create_reminder as _create_reminder,
    cancel_reminder as _cancel_reminder,
    list_reminders as _list_reminders,
)
from habits import (
    create_habit as _create_habit,
    find_habit_by_name,
    log_habit as _log_habit,
    get_habit_progress as _get_habit_progress,
    get_habits,
)
from schedule import (
    create_schedule_event as _create_schedule_event,
    get_schedule_events,
    delete_schedule_event as _delete_schedule_event,
)
from recurring import (
    create_recurring_task as _create_recurring_task,
    get_recurring_tasks,
)
from memory import (
    save_memory as _save_memory,
    list_memories,
    delete_memory as _delete_memory,
)
from goals import (
    create_goal as _create_goal,
    get_goals,
    update_goal_progress as _update_goal_progress,
    update_goal_status as _update_goal_status,
    format_goal,
)
from users import update_user_profile as _update_user_profile
from logger import get_logger


log = get_logger(__name__)


def _safe_error_message(message):
    text = str(message or "Tool execution failed")
    text = text.replace("\n", " ")

    if any(token in text.lower() for token in ["api_key", "token", "password", "secret", "sqlite3", "sql"]):
        return "Tool execution failed"

    return text[:200]


def _coerce_int(value, field_name):
    if value is None:
        raise ValueError(f"{field_name} is required")

    if isinstance(value, bool):
        raise ValueError(f"Invalid {field_name}")

    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid {field_name}")


def _row_to_dict(row):
    return dict(row) if row is not None else None


def _rows_to_list(rows):
    return [dict(r) for r in rows]


# =========================================================
# TOOL SCHEMAS
# =========================================================

TOOLS = [
    {
        "name": "create_task",
        "description": (
            "Create a new flexible task. Use for anything the "
            "user needs to do that isn't a fixed recurring "
            "commitment (those go through create_recurring_task "
            "or create_schedule_event instead)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "due_date": {
                    "type": "string",
                    "description": (
                        "ISO-ish local datetime, e.g. "
                        "'2026-09-17 10:00'. Omit if no "
                        "specific deadline."
                    ),
                },
                "priority": {
                    "type": "string",
                    "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                },
                "category": {"type": "string"},
                "estimated_minutes": {"type": "integer"},
                "notes": {"type": "string"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "update_task",
        "description": "Update fields on an existing task by id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "title": {"type": "string"},
                "due_date": {"type": "string"},
                "priority": {
                    "type": "string",
                    "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                },
                "notes": {"type": "string"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "complete_task",
        "description": "Mark a task as completed.",
        "input_schema": {
            "type": "object",
            "properties": {"task_id": {"type": "integer"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "cancel_task",
        "description": "Cancel a task (it stays in history as CANCELLED).",
        "input_schema": {
            "type": "object",
            "properties": {"task_id": {"type": "integer"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "delete_task",
        "description": (
            "Permanently delete a task. This is irreversible -- "
            "only call this after the user has explicitly "
            "confirmed they want it deleted, not cancelled."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"task_id": {"type": "integer"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "reschedule_task",
        "description": "Change a task's due date/time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "new_due_date": {"type": "string"},
            },
            "required": ["task_id", "new_due_date"],
        },
    },
    {
        "name": "list_tasks",
        "description": "List the user's tasks, optionally filtered by status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": TASK_STATUSES,
                }
            },
        },
    },
    {
        "name": "get_today_tasks",
        "description": (
            "Get today's tasks (also auto-generates today's "
            "instances of any recurring tasks)."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_overdue_tasks",
        "description": "Get all tasks past their due date that aren't done/cancelled.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "create_reminder",
        "description": (
            "Create a standalone reminder at a specific time "
            "(for requests like 'remind me at 6pm to call mom' "
            "that aren't tied to editing a task's own schedule)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "remind_at": {
                    "type": "string",
                    "description": "Local datetime, e.g. '2026-09-17 18:00'.",
                },
                "message": {"type": "string"},
                "task_id": {"type": "integer"},
            },
            "required": ["remind_at"],
        },
    },
    {
        "name": "cancel_reminder",
        "description": "Cancel a pending standalone reminder.",
        "input_schema": {
            "type": "object",
            "properties": {"reminder_id": {"type": "integer"}},
            "required": ["reminder_id"],
        },
    },
    {
        "name": "list_reminders",
        "description": "List the user's pending reminders.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "create_habit",
        "description": "Create a trackable habit (e.g. walking, gym, reading).",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "target": {"type": "number"},
                "unit": {"type": "string"},
                "frequency": {
                    "type": "string",
                    "enum": ["DAILY", "WEEKLY"],
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "log_habit",
        "description": "Log today's (or a given date's) progress on a habit by name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "value": {"type": "number"},
                "date": {
                    "type": "string",
                    "description": "YYYY-MM-DD, omit for today.",
                },
            },
            "required": ["name", "value"],
        },
    },
    {
        "name": "get_habit_progress",
        "description": "Get progress for one habit (by name) or all habits if name omitted.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        },
    },
    {
        "name": "create_schedule_event",
        "description": (
            "Create a FIXED recurring event (institute, a "
            "class, a standing appointment) that the planner "
            "must never silently move. Not for one-off tasks."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "start_time": {"type": "string", "description": "HH:MM"},
                "end_time": {"type": "string", "description": "HH:MM"},
                "days": {
                    "type": "string",
                    "description": "Comma-separated: MON,WED,FRI or DAILY",
                },
                "notes": {"type": "string"},
            },
            "required": ["title", "start_time", "end_time", "days"],
        },
    },
    {
        "name": "get_schedule",
        "description": "List the user's fixed recurring schedule events.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "delete_schedule_event",
        "description": "Remove a fixed schedule event.",
        "input_schema": {
            "type": "object",
            "properties": {"event_id": {"type": "integer"}},
            "required": ["event_id"],
        },
    },
    {
        "name": "create_recurring_task",
        "description": (
            "Create a recurring FLEXIBLE task template (e.g. "
            "'Excel lesson every day', 'Russian every Mon/Wed/Fri'). "
            "A real task is auto-generated each matching day."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "days": {
                    "type": "string",
                    "description": "Comma-separated: MON,WED,FRI or DAILY",
                },
                "time": {"type": "string", "description": "HH:MM, optional"},
                "estimated_minutes": {"type": "integer"},
                "category": {"type": "string"},
                "priority": {
                    "type": "string",
                    "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                },
            },
            "required": ["title", "days"],
        },
    },
    {
        "name": "list_recurring_tasks",
        "description": "List recurring task templates.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "save_memory",
        "description": (
            "Save a durable fact worth remembering long-term "
            "(a preference, routine, goal, or important "
            "context). Do not save one-off conversational "
            "details."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "memory": {"type": "string"},
                "category": {
                    "type": "string",
                    "enum": [
                        "preference", "schedule", "goal",
                        "routine", "important_context",
                    ],
                },
            },
            "required": ["memory"],
        },
    },
    {
        "name": "list_memories",
        "description": "List saved memories (with ids, so one can be deleted).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "delete_memory",
        "description": "Forget a specific memory by id (use after list_memories to find it).",
        "input_schema": {
            "type": "object",
            "properties": {"memory_id": {"type": "integer"}},
            "required": ["memory_id"],
        },
    },
    {
        "name": "create_goal",
        "description": "Create a long-term goal.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "category": {"type": "string"},
                "priority": {
                    "type": "string",
                    "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                },
                "target_value": {"type": "number"},
                "unit": {"type": "string"},
                "deadline": {"type": "string"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "list_goals",
        "description": "List the user's goals, optionally by status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["ACTIVE", "COMPLETED", "PAUSED", "CANCELLED"],
                }
            },
        },
    },
    {
        "name": "update_goal_progress",
        "description": "Update how much progress has been made on a goal.",
        "input_schema": {
            "type": "object",
            "properties": {
                "goal_id": {"type": "integer"},
                "current_progress": {"type": "number"},
            },
            "required": ["goal_id", "current_progress"],
        },
    },
    {
        "name": "update_goal_status",
        "description": "Change a goal's status (e.g. pause, cancel, complete).",
        "input_schema": {
            "type": "object",
            "properties": {
                "goal_id": {"type": "integer"},
                "status": {
                    "type": "string",
                    "enum": ["ACTIVE", "COMPLETED", "PAUSED", "CANCELLED"],
                },
            },
            "required": ["goal_id", "status"],
        },
    },
    {
        "name": "update_user_profile",
        "description": (
            "Update the user's stored profile (name, IANA "
            "timezone, or default reminder lead time in "
            "minutes)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "timezone": {
                    "type": "string",
                    "description": "IANA timezone, e.g. Asia/Tashkent",
                },
                "default_reminder_minutes": {"type": "integer"},
            },
        },
    },
]


# =========================================================
# DISPATCHER
# =========================================================

def execute_tool(user_id, name, tool_input):
    """
    Executes exactly one tool call, scoped to user_id.
    Returns a plain JSON-serializable dict, always containing
    "ok". Never raises -- any exception is caught and reported
    back as ok=False so the model (and the user) get an honest
    account instead of a crash.
    """

    try:
        handler = _HANDLERS.get(name)

        if handler is None:
            return {"ok": False, "error": f"Unknown tool: {name}"}

        result = handler(user_id, tool_input or {})

        if not isinstance(result, dict):
            return {"ok": False, "error": "Tool execution failed"}

        if "ok" not in result:
            return {"ok": False, "error": "Tool execution failed"}

        if result.get("ok") is False and "error" not in result:
            result["error"] = "Tool execution failed"

        return result

    except Exception as e:

        log.error(
            "Tool execution failed: %s(%s)",
            name, tool_input, exc_info=True,
        )

        return {"ok": False, "error": _safe_error_message(e)}


def _h_create_task(user_id, i):
    task_id = _create_task(
        user_id,
        title=i["title"],
        priority=i.get("priority", "MEDIUM"),
        due_date=i.get("due_date"),
        category=i.get("category", "GENERAL"),
        estimated_minutes=i.get("estimated_minutes"),
    )
    return {"ok": True, "task": _row_to_dict(get_task(user_id, task_id))}


def _h_update_task(user_id, i):
    try:
        task_id = _coerce_int(i.get("task_id"), "task_id")
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    if get_task(user_id, task_id) is None:
        return {"ok": False, "error": f"Task {task_id} not found"}

    changes = {}

    if i.get("title") is not None:
        changes["title"] = i["title"]

    if i.get("priority") is not None:
        changes["priority"] = i["priority"]

    if i.get("notes") is not None:
        changes["notes"] = i["notes"]

    if i.get("due_date") is not None:
        try:
            update_task_time(user_id, task_id, i["due_date"])
        except Exception as exc:
            log.error("Failed to reschedule task id=%s user=%s", task_id, user_id, exc_info=True)
            return {"ok": False, "error": "Task update failed"}

    try:
        updated = update_task_fields(user_id, task_id, **changes)
    except KeyError:
        return {"ok": False, "error": f"Task {task_id} not found"}
    except Exception as exc:
        log.error("Task update failed user=%s task_id=%s", user_id, task_id, exc_info=True)
        return {"ok": False, "error": "Task update failed"}

    return {"ok": True, "task": _row_to_dict(updated)}


def _h_complete_task(user_id, i):
    try:
        task_id = _coerce_int(i.get("task_id"), "task_id")
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    task = get_task(user_id, task_id)
    if task is None:
        return {"ok": False, "error": f"Task {task_id} not found"}

    try:
        update_task_status(user_id, task_id, "COMPLETED")
    except Exception as exc:
        log.error("Failed to complete task id=%s user=%s", task_id, user_id, exc_info=True)
        return {"ok": False, "error": "Task completion failed"}

    return {"ok": True, "task": _row_to_dict(get_task(user_id, task_id))}


def _h_cancel_task(user_id, i):
    try:
        task_id = _coerce_int(i.get("task_id"), "task_id")
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    task = get_task(user_id, task_id)
    if task is None:
        return {"ok": False, "error": f"Task {task_id} not found"}

    try:
        update_task_status(user_id, task_id, "CANCELLED")
    except Exception as exc:
        log.error("Failed to cancel task id=%s user=%s", task_id, user_id, exc_info=True)
        return {"ok": False, "error": "Task cancellation failed"}

    return {"ok": True, "task": _row_to_dict(get_task(user_id, task_id))}


def _h_delete_task(user_id, i):
    try:
        task_id = _coerce_int(i.get("task_id"), "task_id")
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    task = get_task(user_id, task_id)
    if task is None:
        return {"ok": False, "error": f"Task {task_id} not found"}

    try:
        _delete_task(user_id, task_id)
    except Exception as exc:
        log.error("Failed to delete task id=%s user=%s", task_id, user_id, exc_info=True)
        return {"ok": False, "error": "Task deletion failed"}

    return {"ok": True, "deleted_task_id": task_id}


def _h_reschedule_task(user_id, i):
    try:
        task_id = _coerce_int(i.get("task_id"), "task_id")
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    task = get_task(user_id, task_id)
    if task is None:
        return {"ok": False, "error": f"Task {task_id} not found"}

    if i.get("new_due_date") is None:
        return {"ok": False, "error": "new_due_date is required"}

    try:
        update_task_time(user_id, task_id, i["new_due_date"])
    except Exception as exc:
        log.error("Failed to reschedule task id=%s user=%s", task_id, user_id, exc_info=True)
        return {"ok": False, "error": "Task reschedule failed"}

    return {"ok": True, "task": _row_to_dict(get_task(user_id, task_id))}


def _h_list_tasks(user_id, i):
    rows = get_tasks(user_id)

    status = i.get("status")

    if status:
        rows = [r for r in rows if r["status"] == status]

    return {"ok": True, "tasks": _rows_to_list(rows)}


def _h_get_today_tasks(user_id, i):
    return {"ok": True, "tasks": _rows_to_list(_get_today_tasks(user_id))}


def _h_get_overdue_tasks(user_id, i):
    return {"ok": True, "tasks": _rows_to_list(_get_overdue_tasks(user_id))}


def _h_create_reminder(user_id, i):
    reminder_id = _create_reminder(
        user_id, i["remind_at"], i.get("message"), i.get("task_id"),
    )
    return {"ok": True, "reminder_id": reminder_id}


def _h_cancel_reminder(user_id, i):
    cancelled = _cancel_reminder(user_id, i["reminder_id"])

    if not cancelled:
        return {"ok": False, "error": "Reminder not found or already sent"}

    return {"ok": True}


def _h_list_reminders(user_id, i):
    return {"ok": True, "reminders": _rows_to_list(_list_reminders(user_id))}


def _h_create_habit(user_id, i):
    habit_id = _create_habit(
        user_id, i["name"], i.get("target"), i.get("unit"),
        i.get("frequency", "DAILY"),
    )
    return {"ok": True, "habit_id": habit_id}


def _h_log_habit(user_id, i):
    habit = find_habit_by_name(user_id, i["name"])

    if not habit:
        return {"ok": False, "error": f"No habit named '{i['name']}'"}

    _log_habit(habit["id"], i["value"], i.get("date"))

    return {
        "ok": True,
        "progress": _get_habit_progress(habit["id"], i.get("date")),
    }


def _h_get_habit_progress(user_id, i):
    if i.get("name"):
        habit = find_habit_by_name(user_id, i["name"])

        if not habit:
            return {"ok": False, "error": f"No habit named '{i['name']}'"}

        return {"ok": True, "progress": _get_habit_progress(habit["id"])}

    habits = get_habits(user_id)

    return {
        "ok": True,
        "progress": [_get_habit_progress(h["id"]) for h in habits],
    }


def _h_create_schedule_event(user_id, i):
    event_id = _create_schedule_event(
        user_id, i["title"], i["start_time"], i["end_time"],
        i["days"], i.get("notes"),
    )
    return {"ok": True, "event_id": event_id}


def _h_get_schedule(user_id, i):
    return {"ok": True, "events": _rows_to_list(get_schedule_events(user_id))}


def _h_delete_schedule_event(user_id, i):
    _delete_schedule_event(user_id, i["event_id"])
    return {"ok": True}


def _h_create_recurring_task(user_id, i):
    template_id = _create_recurring_task(
        user_id, i["title"], i["days"], i.get("time"),
        i.get("estimated_minutes"), i.get("category", "GENERAL"),
        i.get("priority", "MEDIUM"),
    )
    return {"ok": True, "recurring_task_id": template_id}


def _h_list_recurring_tasks(user_id, i):
    return {"ok": True, "templates": _rows_to_list(get_recurring_tasks(user_id))}


def _h_save_memory(user_id, i):
    _save_memory(user_id, i["memory"], i.get("category", "important_context"))
    return {"ok": True}


def _h_list_memories(user_id, i):
    return {"ok": True, "memories": _rows_to_list(list_memories(user_id))}


def _h_delete_memory(user_id, i):
    deleted = _delete_memory(user_id, i["memory_id"])

    if not deleted:
        return {"ok": False, "error": "Memory not found"}

    return {"ok": True}


def _h_create_goal(user_id, i):
    goal_id = _create_goal(
        user_id=user_id,
        name=i["name"],
        category=i.get("category", "GENERAL"),
        target_value=i.get("target_value"),
        unit=i.get("unit"),
        deadline=i.get("deadline"),
        priority=i.get("priority", "MEDIUM"),
    )
    return {"ok": True, "goal_id": goal_id}


def _h_list_goals(user_id, i):
    rows = get_goals(user_id, status=i.get("status", "ACTIVE"))
    return {"ok": True, "goals": _rows_to_list(rows)}


def _h_update_goal_progress(user_id, i):
    _update_goal_progress(user_id, i["goal_id"], i["current_progress"])
    return {"ok": True}


def _h_update_goal_status(user_id, i):
    _update_goal_status(user_id, i["goal_id"], i["status"])
    return {"ok": True}


def _h_update_user_profile(user_id, i):
    _update_user_profile(
        user_id,
        name=i.get("name"),
        timezone=i.get("timezone"),
        default_reminder_minutes=i.get("default_reminder_minutes"),
    )
    return {"ok": True}


_HANDLERS = {
    "create_task": _h_create_task,
    "update_task": _h_update_task,
    "complete_task": _h_complete_task,
    "cancel_task": _h_cancel_task,
    "delete_task": _h_delete_task,
    "reschedule_task": _h_reschedule_task,
    "list_tasks": _h_list_tasks,
    "get_today_tasks": _h_get_today_tasks,
    "get_overdue_tasks": _h_get_overdue_tasks,
    "create_reminder": _h_create_reminder,
    "cancel_reminder": _h_cancel_reminder,
    "list_reminders": _h_list_reminders,
    "create_habit": _h_create_habit,
    "log_habit": _h_log_habit,
    "get_habit_progress": _h_get_habit_progress,
    "create_schedule_event": _h_create_schedule_event,
    "get_schedule": _h_get_schedule,
    "delete_schedule_event": _h_delete_schedule_event,
    "create_recurring_task": _h_create_recurring_task,
    "list_recurring_tasks": _h_list_recurring_tasks,
    "save_memory": _h_save_memory,
    "list_memories": _h_list_memories,
    "delete_memory": _h_delete_memory,
    "create_goal": _h_create_goal,
    "list_goals": _h_list_goals,
    "update_goal_progress": _h_update_goal_progress,
    "update_goal_status": _h_update_goal_status,
    "update_user_profile": _h_update_user_profile,
}
