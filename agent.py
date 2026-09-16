import json
from datetime import datetime

from anthropic import Anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from memory import get_memories
from planner import get_today_stats, get_today_tasks
from tasks import get_overdue_tasks
from goals import get_goals
from users import get_or_create_user
from tools import TOOLS, execute_tool
from logger import get_logger
from timezone_service import now_for_user


log = get_logger(__name__)

client = Anthropic(
    api_key=ANTHROPIC_API_KEY
)


MAX_TOOL_ITERATIONS = 6


SYSTEM_PROMPT = """
You are a serious Personal AI Agent running inside a Telegram bot.

Your job is NOT just chatting. Your job is to help the user:
- plan realistically
- execute tasks
- maintain consistency
- detect overload
- protect sleep
- track progress toward goals and habits
- make better decisions

Core philosophy: Consistency > Perfection.

Never punish the user for missing a task. If a task is missed:
1. understand why (ask briefly if it isn't clear)
2. determine whether it is still important
3. reschedule, shorten, split, postpone or remove it
4. avoid stacking too many tasks

Priority hierarchy:
1. Reality
2. Fixed commitments (schedule_events)
3. Important goals
4. Priority
5. Available time
6. Energy

CRITICAL RULES:
- You have tools. Use them to actually read and change the
  user's data. Never claim you created, moved, completed, or
  deleted anything unless the matching tool call actually
  succeeded (ok: true in the tool result).
- If a tool call fails (ok: false), tell the user honestly
  what went wrong. Do not pretend it worked.
- Resolve relative dates ("tomorrow", "in 2 hours", "next
  Monday") yourself using the current date/time given in your
  context, and pass explicit datetimes like "2026-09-17 10:00"
  to tools.
- Ask a clarifying question only when you genuinely cannot
  proceed safely. Prefer inferring reasonable defaults.
- Before deleting a task, cancelling a goal, or any other
  clearly irreversible action, confirm with the user first --
  unless they already explicitly asked for exactly that.
- Be direct, concise, and practical. Not verbose. Not
  overly motivational. Not childish.
- Only call save_memory for durable facts (preferences,
  routines, goals, important context) -- not one-off details.
"""


def build_context(user_id):

    user = get_or_create_user(user_id)

    now = now_for_user(user_id)

    memories = get_memories(user_id)

    today_tasks = get_today_tasks(user_id)
    overdue = get_overdue_tasks(user_id)
    stats = get_today_stats(user_id)
    goals = get_goals(user_id, status="ACTIVE")

    def brief_task(t):
        return {
            "id": t["id"],
            "title": t["title"],
            "status": t["status"],
            "priority": t["priority"],
            "due_date": t["due_date"],
        }

    context = {
        "current_datetime": now.strftime("%Y-%m-%d %H:%M (%A)"),
        "user_timezone": user["timezone"] if user else "Asia/Tashkent",
        "user_name": user["name"] if user else None,
        "today_tasks": [brief_task(t) for t in today_tasks],
        "overdue_tasks": [brief_task(t) for t in overdue],
        "today_stats": stats,
        "active_goals": [
            {"id": g["id"], "name": g["name"], "priority": g["priority"]}
            for g in goals
        ],
        "memories": list(memories),
    }

    return context


def _sanitize_tool_input(value):
    if value is None:
        return None

    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            lower = str(key).lower()
            if any(token in lower for token in ("token", "secret", "password", "api_key", "key")):
                result[key] = "[redacted]"
            else:
                result[key] = _sanitize_tool_input(item)
        return result

    if isinstance(value, list):
        return [_sanitize_tool_input(item) for item in value]

    if isinstance(value, str):
        return value[:200]

    return value


def _looks_like_success_claim(text):
    if not text:
        return False

    lower = text.lower()
    success_markers = (
        "completed", "created", "updated", "deleted", "saved",
        "finished", "done", "successfully", "rescheduled",
        "cancelled", "canceled", "added", "removed"
    )

    return any(marker in lower for marker in success_markers)


def ask_agent(user_id, message):
    """
    Runs the full agent loop: build context -> call Claude with
    tools -> execute any tool calls -> feed results back -> repeat
    until Claude returns a final text-only response (or the
    iteration cap is hit).
    """

    context = build_context(user_id)

    system = (
        SYSTEM_PROMPT
        + "\n\nCURRENT CONTEXT (JSON):\n"
        + json.dumps(context, ensure_ascii=False, default=str)
    )

    messages = [{"role": "user", "content": message}]

    final_text_parts = []
    saw_tool_failure = False
    last_failure_result = None

    for _ in range(MAX_TOOL_ITERATIONS):

        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1200,
            system=system,
            tools=TOOLS,
            messages=messages,
        )

        tool_uses = [
            block for block in response.content
            if block.type == "tool_use"
        ]

        text_blocks = [
            block.text for block in response.content
            if block.type == "text"
        ]

        if not tool_uses:
            if text_blocks:
                final_text_parts.extend(text_blocks)
            break

        tool_failure = False
        tool_results = []

        for call in tool_uses:

            safe_input = _sanitize_tool_input(call.input)
            log.info(
                "Tool call: user=%s name=%s input=%s",
                user_id, call.name, safe_input,
            )

            result = execute_tool(user_id, call.name, call.input)

            if not isinstance(result, dict) or result.get("ok") is not True:
                tool_failure = True
                saw_tool_failure = True
                last_failure_result = result

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": call.id,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })

        if tool_failure:
            final_text_parts = []

        if not tool_failure and text_blocks:
            final_text_parts.extend(text_blocks)

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        if tool_failure:
            messages.append({
                "role": "user",
                "content": (
                    "The previous tool call failed. "
                    "Do not claim the action succeeded. "
                    "Report the actual failure result and the next safe step."
                )
            })

        if response.stop_reason != "tool_use":
            break

    else:
        log.error(
            "Agent hit max tool iterations for user=%s", user_id,
        )
        final_text_parts.append(
            "⚠️ Bu so'rov juda ko'p qadam talab qildi. "
            "Iltimos, so'rovni soddaroq qilib qayta yuboring."
        )

    if saw_tool_failure:
        if last_failure_result and isinstance(last_failure_result, dict):
            failure_text = last_failure_result.get("error") or "Tool execution failed."
            final_text_parts = [f"⚠️ {failure_text}"]
        else:
            final_text_parts = ["⚠️ The previous tool call failed. No success was confirmed."]

    if not final_text_parts:
        return "⚠️ Javob olishda muammo bo'ldi. Qayta urinib ko'ring."

    return "\n".join(final_text_parts)
