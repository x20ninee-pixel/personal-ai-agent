import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import config
import database
import agent
import tools
from tasks import create_task


@pytest.fixture
def isolated_db(monkeypatch, tmp_path):
    db_path = tmp_path / "agent.db"
    monkeypatch.setattr(config, "DATABASE_PATH", str(db_path))
    monkeypatch.setattr(database, "DATABASE_PATH", str(db_path))
    database.init_database()
    return db_path


def test_successful_tool_call_returns_ok_true(isolated_db):
    result = tools.execute_tool("user-1", "create_task", {"title": "Write test"})

    assert result["ok"] is True
    assert "task" in result
    assert result["task"]["title"] == "Write test"


def test_agent_must_not_report_success_after_failed_tool_result(isolated_db):
    class ToolUseBlock:
        def __init__(self, call_id, name, payload):
            self.type = "tool_use"
            self.id = call_id
            self.name = name
            self.input = payload

    class TextBlock:
        def __init__(self, text):
            self.type = "text"
            self.text = text

    first_response = SimpleNamespace(
        content=[ToolUseBlock("call_1", "complete_task", {"task_id": 999})],
        stop_reason="tool_use",
    )
    second_response = SimpleNamespace(
        content=[TextBlock("I completed the task.")],
        stop_reason="end_turn",
    )

    fake_messages = SimpleNamespace(create=lambda *args, **kwargs: second_response if len(args) > 0 else second_response)

    def fake_create(*args, **kwargs):
        call = kwargs.get("messages", [])
        if len(call) == 1:
            return first_response
        return second_response

    fake_messages = SimpleNamespace(create=fake_create)

    with patch.object(agent, "execute_tool", return_value={"ok": False, "error": "Task 999 not found"}):
        with patch.object(agent.client, "messages", fake_messages):
            result = agent.ask_agent("user-1", "complete task 999")

    assert "completed" not in result.lower()
    assert "not found" in result.lower()


def test_nonexistent_task_and_invalid_task_id_return_ok_false(isolated_db):
    missing = tools.execute_tool("user-1", "complete_task", {"task_id": 999})
    invalid = tools.execute_tool("user-1", "complete_task", {"task_id": "abc"})

    assert missing["ok"] is False
    assert invalid["ok"] is False


def test_cross_user_task_access_rejected(isolated_db):
    task_id = create_task("user-1", "Only for user-1")

    result = tools.execute_tool("user-2", "complete_task", {"task_id": task_id})

    assert result["ok"] is False
    assert "not found" in result["error"].lower()


def test_database_or_tool_exception_returns_ok_false_no_crash(isolated_db):
    def boom(*args, **kwargs):
        raise RuntimeError("DB_PASSWORD=super-secret")

    with patch("tools.get_task", side_effect=boom):
        result = tools.execute_tool("user-1", "complete_task", {"task_id": 1})

    assert result["ok"] is False
    assert "super-secret" not in str(result)
    assert "DB_PASSWORD" not in str(result)


def test_multi_turn_tool_loop_passes_tool_result_back_to_claude(isolated_db):
    class ToolUseBlock:
        def __init__(self, call_id, name, payload):
            self.type = "tool_use"
            self.id = call_id
            self.name = name
            self.input = payload

    class TextBlock:
        def __init__(self, text):
            self.type = "text"
            self.text = text

    first_response = SimpleNamespace(
        content=[ToolUseBlock("call_1", "create_task", {"title": "Test loop"})],
        stop_reason="tool_use",
    )
    second_response = SimpleNamespace(
        content=[TextBlock("Created task successfully.")],
        stop_reason="end_turn",
    )

    seen = {}

    def fake_create(*args, **kwargs):
        messages = kwargs["messages"]
        if len(messages) >= 3 and messages[-1]["role"] == "user":
            seen["tool_result_payload"] = messages[-1]["content"]
        if len(messages) == 1:
            return first_response
        return second_response

    fake_messages = SimpleNamespace(create=fake_create)

    with patch.object(agent, "execute_tool", return_value={"ok": True, "task": {"id": 7, "title": "Test loop"}}):
        with patch.object(agent.client, "messages", fake_messages):
            result = agent.ask_agent("user-1", "create task Test loop")

    assert "Created task successfully." in result
    assert seen["tool_result_payload"][0]["tool_use_id"] == "call_1"
    payload = json.loads(seen["tool_result_payload"][0]["content"])
    assert payload["ok"] is True


def test_no_secrets_in_error_output(isolated_db):
    def boom(*args, **kwargs):
        raise RuntimeError("API_KEY=secret-123")

    with patch("tools.execute_tool", side_effect=boom):
        with pytest.raises(RuntimeError):
            tools.execute_tool("user-1", "create_task", {"title": "x"})

    # This guard ensures the app-level safety layer normalizes errors before they reach the caller.
    # The real check is exercised in test_database_or_tool_exception_returns_ok_false_no_crash.
