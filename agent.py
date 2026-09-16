import json

from anthropic import Anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from memory import get_memories
from planner import get_today_stats


client = Anthropic(
    api_key=ANTHROPIC_API_KEY
)


SYSTEM_PROMPT = """
You are a serious Personal AI Agent.

Your job is NOT just chatting.

Your job is to help the user:
- plan realistically
- execute tasks
- maintain consistency
- detect overload
- protect sleep
- improve Russian
- finish Excel course
- maintain gym consistency
- track progress
- make better decisions

Core philosophy:

Consistency > Perfection.

Never punish the user for missing a task.

If a task is missed:
1. understand why
2. determine whether it is still important
3. reschedule, shorten, split, postpone or remove it
4. avoid stacking too many tasks

Priority hierarchy:

1. Reality
2. Fixed commitments
3. Important goals
4. Priority
5. Available time
6. Energy
7. Optimization

Be direct.

Do not be abusive.

Do not invent completed work.

Protect sleep.

The user prefers concise, actionable answers.

Current long-term goals:
- Russian B2
- Excel course completion
- Gym / fitness
- Better sleep
- Better daily organization
- Institute handled independently
"""


def ask_agent(user_id, message):

    memories = get_memories(user_id)

    stats = get_today_stats(user_id)

    memory_text = "\n".join(
        f"- {m}"
        for m in memories
    )

    context = f"""
USER MEMORIES:
{memory_text}

TODAY STATS:
{json.dumps(stats, ensure_ascii=False)}
"""

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1200,
        system=SYSTEM_PROMPT + "\n\n" + context,
        messages=[
            {
                "role": "user",
                "content": message,
            }
        ],
    )

    return response.content[0].text
    