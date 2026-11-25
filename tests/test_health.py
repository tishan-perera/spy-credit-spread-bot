"""Health check: planned logger runs come from the calendar, and every missed or failed run is reported."""
import json
from datetime import date, datetime

from spybot import config, health
from spybot.dashboard import ET


def _good(root, day, hhmm):
    d = root / "data" / "snapshots" / day
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{hhmm}.json").write_text(json.dumps({"legs": {}}))


def _bad(root, day, hhmm):
    d = root / "data" / "snapshots" / day
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{hhmm}.bad.json").write_text(json.dumps({"problems": ["x"]}))


def _raw(root, day, name, text="boom"):
    d = root / "data" / "raw" / day
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(text)


def test_planned_runs_start_with_the_daily_schedule():
    assert health.planned(date(2026, 11, 19)) == ()                 # before daily runs began
    assert health.planned(config.LOGGER_START) == ("1000", "1015", "1030", "1530", "1540")
    assert health.planned(date(2026, 11, 26)) == ()                 # Thanksgiving
    assert health.planned(date(2026, 11, 27))[-2:] == ("1230", "1240")


def test_slot_states(tmp_path):
    now = datetime(2026, 11, 25, 11, 0, tzinfo=ET)
    _good(tmp_path, "2026-11-25", "1000")
    _bad(tmp_path, "2026-11-25", "1015")
    _raw(tmp_path, "2026-11-25", "1030.error.txt")
    day = date(2026, 11, 25)
    assert health.slot_state(tmp_path, day, "1000", now) == "ok"
    assert health.slot_state(tmp_path, day, "1015", now) == "bad"
    assert health.slot_state(tmp_path, day, "1030", now) == "error"
    assert health.slot_state(tmp_path, day, "1530", now) == "upcoming"
    assert health.slot_state(tmp_path, date(2026, 11, 24), "1530", now) == "missed"


def test_a_run_is_not_missed_until_30_minutes_after_its_time(tmp_path):
    day = date(2026, 11, 25)
    assert health.slot_state(tmp_path, day, "1015", datetime(2026, 11, 25, 10, 44, tzinfo=ET)) == "upcoming"
    assert health.slot_state(tmp_path, day, "1015", datetime(2026, 11, 25, 10, 46, tzinfo=ET)) == "missed"


def test_run_problems_lists_missed_and_failed_runs(tmp_path):
    now = datetime(2026, 11, 25, 16, 30, tzinfo=ET)
    for h in ("1000", "1015", "1030", "1530", "1540"):
        _good(tmp_path, "2026-11-24", h)
        _good(tmp_path, "2026-11-23", h)
    for h in ("1000", "1015", "1540"):
        _good(tmp_path, "2026-11-25", h)
    _bad(tmp_path, "2026-11-25", "1530")
    msgs = health.run_problems(tmp_path, now)
    assert msgs == ["Logger run Wed Nov 25 10:30 AM never ran.", "Logger run Wed Nov 25 3:30 PM failed the check."]


def test_skipped_holiday_runs_are_not_problems(tmp_path):
    now = datetime(2026, 11, 26, 16, 30, tzinfo=ET)                  # Thanksgiving
    for h in ("1000", "1015", "1030", "1530", "1540"):
        _good(tmp_path, "2026-11-25", h)
        _good(tmp_path, "2026-11-24", h)
        _good(tmp_path, "2026-11-23", h)
        _raw(tmp_path, "2026-11-26", f"{h}.skipped.txt", "not a trading day")
    assert health.run_problems(tmp_path, now) == []


def test_next_planned_run():
    nxt = health.next_planned(datetime(2026, 11, 25, 16, 0, tzinfo=ET))
    assert nxt == datetime(2026, 11, 27, 10, 0, tzinfo=ET)          # skips Thanksgiving
    assert health.next_planned(datetime(2026, 11, 27, 10, 50, tzinfo=ET)) == datetime(2026, 11, 27, 12, 30, tzinfo=ET)


def test_check_flags_history_and_calendar(tmp_path):
    now = datetime(2026, 11, 25, 16, 30, tzinfo=ET)
    msgs = health.check(tmp_path, now, history_last=date(2026, 11, 16))
    assert any("price history" in m.lower() and "2026-11-16" in m for m in msgs)
    assert not any("calendar" in m.lower() for m in msgs)
    ok = health.check(tmp_path, now, history_last=date(2026, 11, 24))
    assert not any("price history" in m.lower() for m in ok)        # yesterday is enough before today's refresh


# --- notify once per problem ---

def test_new_problems_are_reported_once(tmp_path):
    state = tmp_path / "notified.json"
    assert health.new_problems(state, ["a", "b"]) == ["a", "b"]
    assert health.new_problems(state, ["a", "b"]) == []
    assert health.new_problems(state, ["b", "c"]) == ["c"]
    assert health.new_problems(state, []) == []
    assert health.new_problems(state, ["a"]) == ["a"]                  # cleared, then back: report again


def test_health_command_prints_all_good_or_problems(tmp_path, capsys):
    from spybot.__main__ import main
    code = main(["health", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 1 and "No price history found." in out


def test_new_run_problems_command_prints_each_run_problem_once(tmp_path, capsys):
    from spybot.__main__ import main
    main(["health", "--new-run-problems", "--root", str(tmp_path)])
    first = capsys.readouterr().out
    assert "never ran" in first and "price history" not in first.lower()
    main(["health", "--new-run-problems", "--root", str(tmp_path)])
    assert capsys.readouterr().out.strip() == "none"
