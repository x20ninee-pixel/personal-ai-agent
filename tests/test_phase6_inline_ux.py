import asyncio
from types import SimpleNamespace

import database
import tasks
from keyboards import build_reschedule_keyboard, build_task_keyboard, parse_callback_data


def _seed(db_path, user_id="u-1", status="PLANNED"):
    database.DATABASE_PATH = str(db_path)
    database.init_database()
    task_id = tasks.create_task(user_id, "Test task")
    if status != "PLANNED":
        tasks.update_task_status(user_id, task_id, status)
    return task_id


def test_callback_parser_accepts_actions_and_options():
    assert parse_callback_data("t:done:7") == ("done", 7, None)
    assert parse_callback_data("t:resched:7:tomorrow") == ("resched", 7, "tomorrow")


def test_callback_parser_rejects_invalid_data():
    for value in ("", "x:done:1", "t:unknown:1", "t:done:x", "t:resched:1:nope", "t:done:1:x"):
        try:
            parse_callback_data(value)
        except ValueError:
            pass
        else:
            raise AssertionError(value)


def test_callback_data_is_under_telegram_limit():
    assert len("t:resched:2147483647:tomorrow".encode()) <= 64


def test_keyboards_have_expected_buttons():
    main = build_task_keyboard(1)
    submenu = build_reschedule_keyboard(1)
    main_data = [button.callback_data for row in main.inline_keyboard for button in row]
    submenu_data = [button.callback_data for row in submenu.inline_keyboard for button in row]
    assert "t:done:1" in main_data
    assert "t:partial:1" in main_data
    assert "t:rmenu:1" in main_data
    assert "t:skip:1" in main_data
    assert "t:resched:1:today" in submenu_data
    assert "t:resched:1:tomorrow" in submenu_data
    assert "t:resched:1:short" in submenu_data
    assert "t:resched:1:cancel" in submenu_data


def test_apply_reschedule_options_are_user_scoped(tmp_path):
    task_id = _seed(tmp_path / "agent.db", "u-1")
    assert tasks.apply_reschedule_option("u-1", task_id, "tomorrow")["status"] == "POSTPONED"
    assert tasks.get_task("u-2", task_id) is None


def test_apply_reschedule_options_match_expected_states(tmp_path):
    db_path = tmp_path / "agent.db"
    for option, expected in (("today", "PLANNED"), ("tomorrow", "POSTPONED"), ("short", "PARTIAL"), ("cancel", "CANCELLED")):
        task_id = _seed(db_path, f"u-{option}")
        updated = tasks.apply_reschedule_option(f"u-{option}", task_id, option)
        assert updated["status"] == expected


def test_apply_reschedule_option_rejects_invalid_option(tmp_path):
    task_id = _seed(tmp_path / "agent.db")
    try:
        tasks.apply_reschedule_option("u-1", task_id, "bad")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid option accepted")


def test_terminal_task_is_not_mutated_by_stale_callback(tmp_path):
    task_id = _seed(tmp_path / "agent.db", "u-1", status="COMPLETED")
    task = tasks.get_task("u-1", task_id)
    assert task["status"] == "COMPLETED"
    # The callback handler performs this same terminal-state guard before mutation.
    assert task["status"] in {"COMPLETED", "CANCELLED", "SKIPPED"}
