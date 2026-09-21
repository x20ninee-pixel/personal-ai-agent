import asyncio

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import TELEGRAM_BOT_TOKEN

from logger import setup_logging, get_logger

from database import init_database

from memory import (
    save_memory,
    get_memories,
)

from tasks import (
    create_task,
    get_tasks,
    get_task,
    get_overdue_tasks,
    update_task_status,
    update_task_time,
    update_recovery_deadline,
    clear_task_schedule,
    delete_task,
    apply_reschedule_option,
)

from planner import (
    get_today_tasks,
    build_today_message,
    build_smart_plan,
    build_reschedule_message,
)
from reports import get_daily_report, get_weekly_report

from agent import ask_agent

from reminders import reminder_engine

from goals import (
    create_goal,
    get_goals,
    update_goal_progress,
    format_goal,
)

from users import get_or_create_user
from keyboards import build_task_keyboard, build_reschedule_keyboard, parse_callback_data


log = get_logger(__name__)


# =========================================================
# GLOBAL ERROR HANDLER
# =========================================================

async def error_handler(update, context):
    """
    Catches any exception raised inside a handler so the bot
    never crashes and never shows a raw stack trace to the user.
    """

    log.error(
        "Unhandled exception while processing update",
        exc_info=context.error,
    )

    if isinstance(update, Update) and update.effective_message:

        try:

            await update.effective_message.reply_text(
                "⚠️ Nimadir xato ketdi. "
                "Qayta urinib ko'ring."
            )

        except Exception:

            log.error(
                "Failed to send error fallback message",
                exc_info=True,
            )


# =========================================================
# START
# =========================================================

async def start(update, context):

    user_id = str(update.effective_user.id)

    get_or_create_user(
        user_id,
        name=update.effective_user.first_name,
        telegram_chat_id=update.effective_user.id,
    )

    await update.message.reply_text(
        "🤖 PERSONAL AI AGENT v2.0\n\n"

        "🧠 Memory\n"
        "📋 Tasks\n"
        "🎯 Goals\n"
        "🔁 Habits\n"
        "📅 Smart Planner\n"
        "🔄 Adaptive Rescheduling\n"
        "🔴 Overdue Recovery\n"
        "� Reports\n"
        "�🔔 Reminders\n\n"

        "Endi tabiiy tilda yozing -- masalan:\n"
        "\"Ertaga 10:00 da 2 soat ACCA o'qishim kerak\"\n"
        "\"ACCA ni kechqurunga ko'chir\"\n"
        "\"10 daqiqa oldin eslat\"\n\n"

        "Yoki komandalar:\n"
        "/today\n"
        "/plan\n"
        "/tasks\n"
        "/daily\n"
        "/weekly\n"
        "/overdue\n"
        "/goals\n"
        "/help"
    )


# =========================================================
# REPORTS
# =========================================================

async def daily_report_command(update, context):
    user_id = str(update.effective_user.id)
    result = get_daily_report(user_id)
    if not result.get("ok"):
        await update.message.reply_text(f"⚠️ {result.get('error', 'Daily report failed')}")
        return

    summary = result["summary"]
    text = (
        "📊 DAILY REPORT\n\n"
        f"Tasks\n"
        f"✅ Completed: {summary.get('completed', 0)}\n"
        f"🟡 Partial: {summary.get('partial', 0)}\n"
        f"⏭ Skipped: {summary.get('skipped', 0)}\n"
        f"❌ Missed: {summary.get('missed', 0)}\n\n"
    )
    if result.get("goal_progress"):
        text += "Goals\n"
        for goal in result["goal_progress"][:3]:
            text += f"🎯 {goal['name']}: {goal['progress']}%\n"
        text += "\n"
    if result.get("habit_progress"):
        text += "Habits\n"
        for habit in result["habit_progress"][:3]:
            text += f"✅ {habit['habit']}: {habit['current']} / {habit['target']} {habit.get('unit', '')}\n"
        text += "\n"
    await update.message.reply_text(text.strip())


async def weekly_report_command(update, context):
    user_id = str(update.effective_user.id)
    result = get_weekly_report(user_id)
    if not result.get("ok"):
        await update.message.reply_text(f"⚠️ {result.get('error', 'Weekly report failed')}")
        return

    summary = result["summary"]
    text = (
        "📈 WEEKLY REPORT\n\n"
        f"Tasks\n"
        f"✅ Completed: {summary.get('completed', 0)}\n"
        f"🟡 Partial: {summary.get('partial', 0)}\n"
        f"⏭ Skipped: {summary.get('skipped', 0)}\n"
        f"❌ Missed: {summary.get('missed', 0)}\n"
        f"🔄 Rescheduled: {summary.get('rescheduled', 0)}\n\n"
    )
    if result.get("bottlenecks"):
        text += "Bottlenecks\n"
        for item in result["bottlenecks"][:2]:
            text += f"⚠️ {item['note']}\n"
    else:
        text += "⚠️ No clear bottlenecks yet.\n"
    await update.message.reply_text(text.strip())


async def help_command(update, context):

    await update.message.reply_text(
        "🤖 COMMANDS\n\n"

        "📋 TASKS\n"
        "/tasks\n"
        "/today\n"
        "/plan\n"
        "/reschedule\n"
        "/done ID\n"
        "/partial ID\n"
        "/skip ID\n"
        "/delete ID\n\n"

        "🔴 OVERDUE RECOVERY\n"
        "/overdue\n"
        "/recover ID\n"
        "/recover_today ID\n"
        "/recover_tomorrow ID\n"
        "/recover_short ID\n"
        "/recover_cancel ID\n\n"

        "🎯 GOALS\n"
        "/goals\n"
        "/goal NAME\n"
        "/progress ID VALUE\n\n"

        "🧠 MEMORY\n"
        "/memory\n"
        "Eslab qol: ...\n\n"

        "� REPORTS\n"
        "/daily\n"
        "/weekly\n\n"

        "�📋 TASK YARATISH\n"
        "task: Excel Lesson 14\n"
        "task: Excel Lesson 14 | 2026-09-15 16:00"
    )


# =========================================================
# TASKS
# =========================================================

async def _send_task_action_cards(message, tasks):
    """Send inline action cards for active tasks."""
    for task in tasks:
        if task["status"] in {"COMPLETED", "CANCELLED", "SKIPPED"}:
            continue
        await message.reply_text(
            f"📋 #{task['id']} — {task['title']}\nStatus: {task['status']}",
            reply_markup=build_task_keyboard(task["id"]),
        )


async def tasks_command(update, context):

    user_id = str(update.effective_user.id)
    tasks = get_tasks(user_id)

    if not tasks:
        await update.message.reply_text("📋 Hozircha task yo'q.")
        return

    message = "📋 TASKLAR\n\n"
    for task in tasks:
        message += (
            f"#{task['id']} — {task['title']}\n"
            f"Status: {task['status']}\n"
            f"Priority: {task['priority']}\n"
        )
        if task["due_date"]:
            message += f"⏰ Original deadline: {task['due_date']}\n"
        if task["recovery_deadline"]:
            message += f"🔄 Recovery deadline: {task['recovery_deadline']}\n"
        if task["scheduled_start"]:
            message += f"🕐 {task['scheduled_start']} → {task['scheduled_end']}\n"
        message += "\n"

    await update.message.reply_text(message)
    await _send_task_action_cards(update.message, tasks)


# =========================================================
# TODAY
# =========================================================

async def today_command(update, context):
    user_id = str(update.effective_user.id)
    await update.message.reply_text(build_today_message(user_id))
    await _send_task_action_cards(update.message, get_today_tasks(user_id))


# =========================================================
# PLAN
# =========================================================

async def plan_command(update, context):

    user_id = str(
        update.effective_user.id
    )

    await update.message.reply_text(
        build_smart_plan(user_id)
    )


# =========================================================
# RESCHEDULE
# =========================================================

async def reschedule_command(update, context):

    user_id = str(
        update.effective_user.id
    )

    await update.message.reply_text(
        build_reschedule_message(user_id)
    )


# =========================================================
# DONE
# =========================================================

async def done_command(update, context):

    user_id = str(
        update.effective_user.id
    )

    if not context.args:

        await update.message.reply_text(
            "Misol:\n/done 5"
        )

        return

    try:

        task_id = int(
            context.args[0]
        )

    except ValueError:

        await update.message.reply_text(
            "❌ ID raqam bo'lishi kerak."
        )

        return

    task = get_task(
        user_id,
        task_id
    )

    if not task:

        await update.message.reply_text(
            "❌ Task topilmadi."
        )

        return

    update_task_status(
        user_id,
        task_id,
        "COMPLETED"
    )

    await update.message.reply_text(
        "✅ COMPLETED\n\n"
        f"📋 {task['title']}"
    )


# =========================================================
# PARTIAL
# =========================================================

async def partial_command(update, context):

    user_id = str(
        update.effective_user.id
    )

    if not context.args:

        await update.message.reply_text(
            "Misol:\n/partial 5"
        )

        return

    try:

        task_id = int(
            context.args[0]
        )

    except ValueError:

        await update.message.reply_text(
            "❌ ID raqam bo'lishi kerak."
        )

        return

    task = get_task(
        user_id,
        task_id
    )

    if not task:

        await update.message.reply_text(
            "❌ Task topilmadi."
        )

        return

    update_task_status(
        user_id,
        task_id,
        "PARTIAL"
    )

    await update.message.reply_text(
        "🟡 PARTIAL\n\n"
        f"📋 {task['title']}"
    )


# =========================================================
# SKIP
# =========================================================

async def skip_command(update, context):

    user_id = str(
        update.effective_user.id
    )

    if not context.args:

        await update.message.reply_text(
            "Misol:\n/skip 5"
        )

        return

    try:

        task_id = int(
            context.args[0]
        )

    except ValueError:

        await update.message.reply_text(
            "❌ ID raqam bo'lishi kerak."
        )

        return

    task = get_task(
        user_id,
        task_id
    )

    if not task:

        await update.message.reply_text(
            "❌ Task topilmadi."
        )

        return

    update_task_status(
        user_id,
        task_id,
        "SKIPPED"
    )

    await update.message.reply_text(
        "⏭️ SKIPPED\n\n"
        f"📋 {task['title']}"
    )


# =========================================================
# DELETE
# =========================================================

async def delete_command(update, context):

    user_id = str(
        update.effective_user.id
    )

    if not context.args:

        await update.message.reply_text(
            "Misol:\n/delete 5"
        )

        return

    try:

        task_id = int(
            context.args[0]
        )

    except ValueError:

        await update.message.reply_text(
            "❌ ID raqam bo'lishi kerak."
        )

        return

    task = get_task(
        user_id,
        task_id
    )

    if not task:

        await update.message.reply_text(
            "❌ Task topilmadi."
        )

        return

    delete_task(
        user_id,
        task_id
    )

    await update.message.reply_text(
        "🗑️ O'CHIRILDI\n\n"
        f"📋 {task['title']}"
    )


# =========================================================
# OVERDUE
# =========================================================

async def overdue_command(update, context):
    user_id = str(update.effective_user.id)
    tasks = get_overdue_tasks(user_id)

    if not tasks:
        await update.message.reply_text(
            "🟢 OVERDUE TASK YO'Q\n\nBarcha deadline'lar nazoratda."
        )
        return

    message = "🔴 OVERDUE TASKLAR\n\n"
    for task in tasks:
        message += (
            f"#{task['id']} — {task['title']}\n"
            f"⚡ Priority: {task['priority']}\n"
            f"⏳ Deadline: {task['due_date']}\n"
            f"📊 Status: {task['status']}\n\n"
        )
    message += "━━━━━━━━━━━━━━\nQayta rejalashtirish: /recover ID"
    await update.message.reply_text(message)
    await _send_task_action_cards(update.message, tasks)


# =========================================================
# RECOVER
# =========================================================

async def recover_command(update, context):

    user_id = str(
        update.effective_user.id
    )

    if not context.args:

        await update.message.reply_text(
            "Misol:\n/recover 5"
        )

        return

    try:

        task_id = int(
            context.args[0]
        )

    except ValueError:

        await update.message.reply_text(
            "❌ ID raqam bo'lishi kerak."
        )

        return

    task = get_task(
        user_id,
        task_id
    )

    if not task:

        await update.message.reply_text(
            "❌ Task topilmadi."
        )

        return

    await update.message.reply_text(

        "🔴 OVERDUE TASK\n\n"

        f"📌 {task['title']}\n"

        f"⏳ Original deadline: "
        f"{task['due_date']}\n\n"

        "Nima qilamiz?\n\n"

        "1️⃣ Bugun bajaraman\n"
        "2️⃣ Ertaga ko'chiramiz\n"
        "3️⃣ Qisqa session qilaman\n"
        "4️⃣ Bekor qilamiz\n\n"

        "Tanlash:\n"

        f"/recover_today {task_id}\n"
        f"/recover_tomorrow {task_id}\n"
        f"/recover_short {task_id}\n"
        f"/recover_cancel {task_id}"
    )


# =========================================================
# RECOVER TODAY
# =========================================================

async def recover_today_command(
    update,
    context
):

    user_id = str(
        update.effective_user.id
    )

    if not context.args:

        await update.message.reply_text(
            "/recover_today ID"
        )

        return

    try:

        task_id = int(
            context.args[0]
        )

    except ValueError:

        await update.message.reply_text(
            "❌ ID raqam bo'lishi kerak."
        )

        return

    task = get_task(
        user_id,
        task_id
    )

    if not task:

        await update.message.reply_text(
            "❌ Task topilmadi."
        )

        return

    apply_reschedule_option(user_id, task_id, "today")

    await update.message.reply_text(

        "🔄 RECOVERY ACCEPTED\n\n"

        f"📌 {task['title']}\n\n"

        f"⏳ Original deadline:\n"
        f"{task['due_date']}\n\n"

        "Original deadline saqlandi.\n"

        "Task bugungi schedule'ga "
        "qaytarildi.\n\n"

        "Endi:\n"
        "/reschedule"
    )


# =========================================================
# RECOVER TOMORROW
# =========================================================

async def recover_tomorrow_command(
    update,
    context
):

    user_id = str(
        update.effective_user.id
    )

    if not context.args:

        await update.message.reply_text(
            "/recover_tomorrow ID"
        )

        return

    try:

        task_id = int(
            context.args[0]
        )

    except ValueError:

        await update.message.reply_text(
            "❌ ID raqam bo'lishi kerak."
        )

        return

    task = get_task(
        user_id,
        task_id
    )

    if not task:

        await update.message.reply_text(
            "❌ Task topilmadi."
        )

        return

    apply_reschedule_option(user_id, task_id, "tomorrow")

    await update.message.reply_text(

        "📅 POSTPONED\n\n"

        f"📌 {task['title']}\n\n"

        f"⏳ Original deadline:\n"
        f"{task['due_date']}\n\n"

        "Original deadline saqlandi.\n"

        "Task ertangi reja uchun "
        "qoldirildi."
    )


# =========================================================
# RECOVER SHORT
# =========================================================

async def recover_short_command(
    update,
    context
):

    user_id = str(
        update.effective_user.id
    )

    if not context.args:

        await update.message.reply_text(
            "/recover_short ID"
        )

        return

    try:

        task_id = int(
            context.args[0]
        )

    except ValueError:

        await update.message.reply_text(
            "❌ ID raqam bo'lishi kerak."
        )

        return

    task = get_task(
        user_id,
        task_id
    )

    if not task:

        await update.message.reply_text(
            "❌ Task topilmadi."
        )

        return

    apply_reschedule_option(user_id, task_id, "short")

    await update.message.reply_text(

        "🟡 SHORT SESSION\n\n"

        f"📌 {task['title']}\n\n"

        f"⏳ Original deadline:\n"
        f"{task['due_date']}\n\n"

        "Original deadline saqlandi.\n"

        "Task qisqa session uchun "
        "tayyor.\n\n"

        "Keyingi /reschedule vaqtni "
        "qayta hisoblaydi."
    )


# =========================================================
# RECOVER CANCEL
# =========================================================

async def recover_cancel_command(
    update,
    context
):

    user_id = str(
        update.effective_user.id
    )

    if not context.args:

        await update.message.reply_text(
            "/recover_cancel ID"
        )

        return

    try:

        task_id = int(
            context.args[0]
        )

    except ValueError:

        await update.message.reply_text(
            "❌ ID raqam bo'lishi kerak."
        )

        return

    task = get_task(
        user_id,
        task_id
    )

    if not task:

        await update.message.reply_text(
            "❌ Task topilmadi."
        )

        return

    apply_reschedule_option(user_id, task_id, "cancel")

    await update.message.reply_text(

        "❌ CANCELLED\n\n"

        f"📌 {task['title']}\n\n"

        "Task bekor qilindi."
    )


# =========================================================
# GOALS
# =========================================================

async def goals_command(update, context):

    user_id = str(
        update.effective_user.id
    )

    goals = get_goals(
        user_id
    )

    if not goals:

        await update.message.reply_text(
            "🎯 Hozircha goal yo'q.\n\n"
            "/goal Russian B2"
        )

        return

    message = "🎯 GOALLAR\n\n"

    for goal in goals:

        message += (
            format_goal(goal)
            + "\n\n"
        )

    await update.message.reply_text(
        message
    )


# =========================================================
# CREATE GOAL
# =========================================================

async def goal_command(update, context):

    user_id = str(
        update.effective_user.id
    )

    name = (
        update.message.text
        .replace("/goal", "", 1)
        .strip()
    )

    if not name:

        await update.message.reply_text(
            "Misol:\n/goal Russian B2"
        )

        return

    goal_id = create_goal(

        user_id=user_id,

        name=name,

        category="GENERAL",

        priority="HIGH",
    )

    await update.message.reply_text(

        "🎯 GOAL YARATILDI\n\n"

        f"ID: {goal_id}\n"

        f"Goal: {name}\n"

        "Status: ACTIVE"
    )


# =========================================================
# PROGRESS
# =========================================================

async def progress_command(
    update,
    context
):

    user_id = str(
        update.effective_user.id
    )

    if len(context.args) != 2:

        await update.message.reply_text(

            "/progress ID VALUE\n\n"

            "Misol:\n"
            "/progress 1 25"
        )

        return

    try:

        goal_id = int(
            context.args[0]
        )

        progress = float(
            context.args[1]
        )

    except ValueError:

        await update.message.reply_text(
            "❌ Raqam kiriting."
        )

        return

    goals = get_goals(
        user_id
    )

    target = None

    for goal in goals:

        if goal["id"] == goal_id:

            target = goal

            break

    if not target:

        await update.message.reply_text(
            "❌ Goal topilmadi."
        )

        return

    update_goal_progress(
        user_id,
        goal_id,
        progress
    )

    await update.message.reply_text(

        "📈 Progress yangilandi!\n\n"

        f"🎯 {target['name']}\n"

        f"📊 {progress}"
    )


# =========================================================
# MEMORY
# =========================================================

async def memory_command(
    update,
    context
):

    user_id = str(
        update.effective_user.id
    )

    memories = get_memories(
        user_id
    )

    if not memories:

        await update.message.reply_text(
            "🧠 Memory yo'q."
        )

        return

    message = "🧠 MEMORY\n\n"

    for i, memory in enumerate(
        memories[:20],
        1
    ):

        message += (
            f"{i}. {memory}\n"
        )

    await update.message.reply_text(
        message
    )


# =========================================================
# MESSAGE HANDLER
# =========================================================

async def message_handler(
    update,
    context
):

    user_id = str(
        update.effective_user.id
    )

    get_or_create_user(
        user_id,
        name=update.effective_user.first_name,
        telegram_chat_id=update.effective_user.id,
    )

    text = (
        update.message.text.strip()
    )

    lower = text.lower()


    # =====================================================
    # MEMORY
    # =====================================================

    patterns = [

        "eslab qol:",

        "eslab qol",

        "yodda saqla:",

        "yodda saqla",

        "remember:",

        "remember",
    ]

    for pattern in patterns:

        if lower.startswith(pattern):

            memory = (
                text[len(pattern):]
                .strip()
            )

            if not memory:

                await update.message.reply_text(
                    "🧠 Nimani eslab qolay?"
                )

                return

            save_memory(
                user_id,
                memory
            )

            await update.message.reply_text(
                "🧠 Eslab qoldim."
            )

            return


    # =====================================================
    # TASK
    # =====================================================

    if lower.startswith("task:"):

        task_text = (
            text[5:].strip()
        )

        due_date = None


        if "|" in task_text:

            title, due_date = (
                task_text.split(
                    "|",
                    1
                )
            )

            title = title.strip()

            due_date = (
                due_date.strip()
            )

        else:

            title = task_text


        if not title:

            await update.message.reply_text(
                "❌ Task nomi kerak."
            )

            return


        task_id = create_task(

            user_id,

            title,

            priority="MEDIUM",

            due_date=due_date
        )


        await update.message.reply_text(

            "📋 TASK YARATILDI\n\n"

            f"ID: {task_id}\n"

            f"Task: {title}\n"

            "Status: PLANNED"
        )

        return


    # =====================================================
    # CLAUDE AGENT
    # =====================================================

    try:

        response = await asyncio.to_thread(

            ask_agent,

            user_id,

            text
        )

        await update.message.reply_text(
            response
        )

    except Exception:

        log.error(
            "Agent call failed",
            exc_info=True,
        )

        await update.message.reply_text(
            "⚠️ Agent xatosi."
        )


# =========================================================
# INLINE TASK CALLBACKS
# =========================================================

async def handle_task_callback(update, context):
    query = update.callback_query
    try:
        action, task_id, option = parse_callback_data(query.data)
    except ValueError:
        await query.answer("❌ Noto'g'ri tugma.", show_alert=True)
        return

    user_id = str(query.from_user.id)
    task = get_task(user_id, task_id)
    if not task:
        await query.answer("❌ Task topilmadi.", show_alert=True)
        return

    if task["status"] in {"COMPLETED", "CANCELLED", "SKIPPED"}:
        await query.answer("ℹ️ Bu task allaqachon yakunlangan.", show_alert=True)
        return

    if action == "rmenu":
        await query.answer()
        await query.edit_message_reply_markup(
            reply_markup=build_reschedule_keyboard(task_id)
        )
        return

    if action == "resched" and option == "cancel":
        await query.answer()
        await query.edit_message_reply_markup(
            reply_markup=build_task_keyboard(task_id)
        )
        return

    if action == "resched":
        try:
            updated = apply_reschedule_option(user_id, task_id, option)
        except (KeyError, ValueError):
            await query.answer("❌ Task topilmadi yoki amal noto'g'ri.", show_alert=True)
            return
        await query.answer("✅ Reja yangilandi")
        await query.edit_message_text(
            f"🔄 {option.upper()}\n\n📋 {task['title']}\nStatus: {updated['status']}"
        )
        return

    status_map = {
        "done": ("COMPLETED", "✅ COMPLETED"),
        "partial": ("PARTIAL", "🟡 PARTIAL"),
        "skip": ("SKIPPED", "⏭️ SKIPPED"),
        "cancel": ("CANCELLED", "❌ CANCELLED"),
    }

    if action == "delete":
        delete_task(user_id, task_id)
        await query.answer("🗑️ O'chirildi")
        await query.edit_message_text(f"🗑️ O'CHIRILDI\n\n📋 {task['title']}")
        return

    if action in status_map:
        status, label = status_map[action]
        update_task_status(user_id, task_id, status)
        await query.answer()
        await query.edit_message_text(f"{label}\n\n📋 {task['title']}")
        return

    await query.answer("❌ Amal topilmadi.", show_alert=True)


# =========================================================
# POST INIT
# =========================================================

async def post_init(
    application
):

    if application.bot_data.get("_reminder_worker_started"):
        return

    application.bot_data["_reminder_worker_started"] = True
    asyncio.create_task(
        reminder_engine(
            application
        )
    )


# =========================================================
# MAIN
# =========================================================

def main():

    setup_logging()

    log.info(
        "Starting Personal AI Agent | "
        "Memory, Tasks, Goals, Planner, "
        "Reminders, Overdue Recovery: READY"
    )


    # =====================================================
    # DATABASE
    # =====================================================

    init_database()


    # =====================================================
    # APPLICATION
    # =====================================================

    application = (

        Application.builder()

        .token(
            TELEGRAM_BOT_TOKEN
        )

        .post_init(
            post_init
        )

        .build()
    )


    # =====================================================
    # BASIC COMMANDS
    # =====================================================

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CommandHandler(
            "help",
            help_command
        )
    )
    application.add_handler(
        CommandHandler(
            "daily",
            daily_report_command
        )
    )
    application.add_handler(
        CommandHandler(
            "weekly",
            weekly_report_command
        )
    )


    # =====================================================
    # TASK COMMANDS
    # =====================================================

    application.add_handler(
        CommandHandler(
            "tasks",
            tasks_command
        )
    )

    application.add_handler(
        CommandHandler(
            "today",
            today_command
        )
    )

    application.add_handler(
        CommandHandler(
            "plan",
            plan_command
        )
    )

    application.add_handler(
        CommandHandler(
            "reschedule",
            reschedule_command
        )
    )

    application.add_handler(
        CommandHandler(
            "done",
            done_command
        )
    )

    application.add_handler(
        CommandHandler(
            "partial",
            partial_command
        )
    )

    application.add_handler(
        CommandHandler(
            "skip",
            skip_command
        )
    )

    application.add_handler(
        CommandHandler(
            "delete",
            delete_command
        )
    )


    # =====================================================
    # OVERDUE RECOVERY
    # =====================================================

    application.add_handler(
        CommandHandler(
            "overdue",
            overdue_command
        )
    )

    application.add_handler(
        CommandHandler(
            "recover",
            recover_command
        )
    )

    application.add_handler(
        CommandHandler(
            "recover_today",
            recover_today_command
        )
    )

    application.add_handler(
        CommandHandler(
            "recover_tomorrow",
            recover_tomorrow_command
        )
    )

    application.add_handler(
        CommandHandler(
            "recover_short",
            recover_short_command
        )
    )

    application.add_handler(
        CommandHandler(
            "recover_cancel",
            recover_cancel_command
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            handle_task_callback,
            pattern=r"^t:"
        )
    )


    # =====================================================
    # GOALS
    # =====================================================

    application.add_handler(
        CommandHandler(
            "goals",
            goals_command
        )
    )

    application.add_handler(
        CommandHandler(
            "goal",
            goal_command
        )
    )

    application.add_handler(
        CommandHandler(
            "progress",
            progress_command
        )
    )


    # =====================================================
    # MEMORY
    # =====================================================

    application.add_handler(
        CommandHandler(
            "memory",
            memory_command
        )
    )


    # =====================================================
    # TEXT
    # =====================================================

    application.add_handler(

        MessageHandler(

            filters.TEXT
            & ~filters.COMMAND,

            message_handler
        )
    )


    # =====================================================
    # ERROR HANDLER
    # =====================================================

    application.add_error_handler(
        error_handler
    )


    # =====================================================
    # START BOT
    # =====================================================

    application.run_polling()


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":

    main()