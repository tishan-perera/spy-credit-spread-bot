"""Dashboard status collector: reads project files only, never calls Robinhood."""
import json
from datetime import date, datetime
from pathlib import Path

import pytest

from spybot import dashboard
from spybot.dashboard import ET

ROOT = Path(__file__).resolve().parent.parent


def _snap(root, day, hhmm, n_legs=3, bad=None):
    d = root / "data" / "snapshots" / day
    d.mkdir(parents=True, exist_ok=True)
    if bad:
        (d / f"{hhmm}.bad.json").write_text(json.dumps({"problems": bad}))
    else:
        legs = {f"put:{700 + i}": {} for i in range(n_legs)}
        (d / f"{hhmm}.json").write_text(json.dumps({"day": day, "run": "10:15:00", "spy": 1, "vix": 1, "legs": legs}))


# --- logger runs and calendar ------------------------------------------------

def test_logger_runs_reads_good_and_bad_snapshots(tmp_path):
    _snap(tmp_path, "2026-11-18", "1015", n_legs=4)
    _snap(tmp_path, "2026-11-18", "1530", bad=["missing delta"])
    runs = dashboard.logger_runs(tmp_path)
    assert [(r["day"], r["hhmm"], r["result"], r["contracts"]) for r in runs] == [
        ("2026-11-18", "1015", "ok", 4), ("2026-11-18", "1530", "bad", None)]
    assert runs[1]["problems"] == ["missing delta"]
    assert runs[0]["time"] == "10:15 AM"


def test_calendar_marks_ok_bad_missed_next_and_off():
    runs = [{"day": "2026-11-17", "hhmm": "1015", "result": "ok"},
            {"day": "2026-11-17", "hhmm": "1530", "result": "bad"}]
    scheduled = [{"day": "2026-11-17", "hhmm": "1000"},     # passed, no file → missed
                 {"day": "2026-11-18", "hhmm": "1015"}]     # still ahead → next
    now = datetime(2026, 11, 18, 9, 0, tzinfo=ET)
    grid = dashboard.calendar_grid(runs, scheduled, now)
    assert grid["Nov 17"] == {"10:00": "missed", "10:15": "ok", "10:30": "off", "3:30": "bad", "3:40": "off"}
    assert grid["Nov 18"]["10:15"] == "next"
    assert list(grid)[-1] == "Nov 19"                    # always shows the next trading day


def test_next_run_is_first_scheduled_time_after_now():
    sched = [{"when": "2026-11-18T10:10:00-05:00", "what": "a"}, {"when": "2026-11-19T10:10:00-05:00", "what": "b"}]
    nxt = dashboard.next_run(sched, datetime(2026, 11, 18, 12, 0, tzinfo=ET))
    assert nxt["what"] == "b" and nxt["iso"] == "2026-11-19T10:10:00-05:00"
    assert nxt["when"] == "Thu Nov 19 · 10:10 AM ET"
    assert dashboard.next_run(sched, datetime(2026, 11, 20, tzinfo=ET)) is None


# --- transcripts: order audit and logger cost ---------------------------------

def _line(**kw):
    return json.dumps(kw)


def _assistant(mid, tools=(), out=10, read=100, write=5, ts="2026-11-17T15:15:00Z"):
    content = [{"type": "tool_use", "name": n, "input": i} for n, i in tools] or [{"type": "text", "text": "x"}]
    return _line(type="assistant", timestamp=ts, message={"id": mid, "content": content, "usage": {
        "output_tokens": out, "cache_read_input_tokens": read, "cache_creation_input_tokens": write, "input_tokens": 1}})


def test_audit_counts_orders_and_previews_on_robinhood_servers_only(tmp_path):
    (tmp_path / "a.jsonl").write_text("\n".join([
        _line(type="user", message={"content": "hello"}),
        _assistant("m1", [("mcp__robinhood__get_option_quotes", {})]),
        _assistant("m2", [("mcp__54da6bf0-5ad5-4b1a-b2c8-3eb2d921e7d1__review_option_order", {})]),
        _assistant("m3", [("mcp__robinhood__place_option_order", {})]),
        _assistant("m4", [("mcp__scheduled-tasks__cancel_task", {})]),   # not a broker tool
    ]))
    a = dashboard.scan_transcripts(tmp_path)
    assert (a["transcripts"], a["toolCalls"], a["orderCalls"], a["previewCalls"]) == (1, 4, 1, 1)
    assert a["previewWhen"] == "Nov 17, 10:15 AM ET"


def test_logger_cost_sums_each_message_once_and_labels_by_notes_file(tmp_path):
    notes = "/x/data/raw/2026-11-18/1530.notes.txt"
    (tmp_path / "run.jsonl").write_text("\n".join([
        _line(type="user", message={"content": "Follow collector/logger-task.md for DAY 2026-11-18"}),
        _assistant("m1", out=10, read=100, write=5),
        _assistant("m1", out=10, read=100, write=5),          # same message, second block: count once
        _assistant("m2", [("Write", {"file_path": notes})], out=7, read=50, write=3),
    ]))
    (tmp_path / "dev.jsonl").write_text(_line(type="user", message={"content": "status report"}))
    a = dashboard.scan_transcripts(tmp_path)
    assert a["loggerRuns"] == [{"label": "Nov 18 3:30", "day": "2026-11-18", "hhmm": "1530",
                                "output": 17, "reread": 150, "write": 10}]


def test_missing_transcript_folder_gives_empty_audit(tmp_path):
    a = dashboard.scan_transcripts(tmp_path / "nope")
    assert a["transcripts"] == 0 and a["loggerRuns"] == []


# --- settings, freshness, events, money ---------------------------------------

def test_blocked_tools_reads_project_settings():
    b = dashboard.blocked_tools(ROOT)
    assert b["orders"] and b["previews"]


def test_blocked_tools_reports_gaps(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(json.dumps({"permissions": {"deny": [
        "mcp__robinhood__place_option_order"]}}))
    b = dashboard.blocked_tools(tmp_path)
    assert not b["orders"] and not b["previews"]


def test_freshness_lists_missing_trading_days():
    f = dashboard.freshness(date(2026, 11, 16), date(2026, 11, 18))
    assert f == {"last": "2026-11-16", "behindDays": 1, "missing": ["2026-11-17"]}
    assert dashboard.freshness(date(2026, 11, 17), date(2026, 11, 18))["behindDays"] == 0


def test_upcoming_lists_event_days_and_flags_missing_months():
    events = {date(2026, 12, 9): ["fomc"], date(2026, 11, 10): ["cpi"]}
    up, note = dashboard.upcoming(events, date(2026, 11, 18))
    assert up == [{"day": "Wed Dec 9", "what": "Fed decision", "skip": True}]
    assert note == "December CPI and jobs-report dates are not in the events file yet."


def test_result_per_contract_after_costs():
    assert dashboard.result_per_contract(0.25, 0.0, "cautious") == pytest.approx(17.34)
    assert dashboard.result_per_contract(0.25, 0.0, "best") == pytest.approx(22.84)
    assert dashboard.result_per_contract(0.25, None, "best") is None


# --- whole status on the real project -----------------------------------------

@pytest.mark.skipif(not (ROOT / "data" / "history").exists(), reason="no local price history")
def test_collect_on_real_project_is_json_and_has_every_panel(tmp_path):
    s = dashboard.collect(ROOT, datetime(2026, 11, 18, 16, 52, tzinfo=ET),
                          tests={"passed": 1, "failed": 0}, transcripts=tmp_path)
    json.dumps(s)
    for key in ("asOf", "stages", "safety", "tests", "branch", "logger", "breakeven", "realCredits",
                "decisions", "activity", "alerts", "calendar", "costs", "freshness", "audit", "shadow",
                "evidence", "slippage", "skipBoard", "upcoming", "eod", "explorer", "profit"):
        assert key in s, key
    assert s["shadow"]["resultCautious"] == pytest.approx(17.34)
    assert len(s["explorer"]["rows"]) == 144


def test_logger_run_label_comes_from_task_text(tmp_path):
    (tmp_path / "run.jsonl").write_text("\n".join([
        _line(type="user", message={"content": "<scheduled-task> follow collector/logger-task.md, "
                                               "with DAY = 2026-11-19 and HHMM = 1015. Then ..."}),
        _assistant("m1", [("Bash", {"command": "D=data/raw/x && cat > $D/1015.notes.txt"})], out=3),
    ]))
    runs = dashboard.scan_transcripts(tmp_path)["loggerRuns"]
    assert [(r["day"], r["hhmm"], r["output"]) for r in runs] == [("2026-11-19", "1015", 3)]


def test_copied_session_does_not_double_count_tool_calls(tmp_path):
    def block(tid):
        return _line(type="assistant", timestamp="2026-11-17T15:15:00Z", message={"id": "m1", "content": [
            {"type": "tool_use", "id": tid, "name": "mcp__robinhood__review_option_order", "input": {}}]})
    (tmp_path / "a.jsonl").write_text(block("toolu_1"))
    (tmp_path / "b.jsonl").write_text(block("toolu_1"))        # a forked copy of the same session
    a = dashboard.scan_transcripts(tmp_path)
    assert (a["toolCalls"], a["previewCalls"]) == (1, 1)


@pytest.mark.skipif(not (ROOT / "data" / "snapshots" / "2026-11-19").exists(), reason="no Nov 19 log")
def test_as_of_date_hides_later_logged_days(tmp_path):
    def shadow_day(day):
        s = dashboard.collect(ROOT, datetime(2026, 11, day, 16, 52, tzinfo=ET),
                              tests={"passed": 1, "failed": 0}, transcripts=tmp_path)
        return s["shadow"]["day"]
    assert shadow_day(18) == dashboard._short(date(2026, 11, 18))
    assert shadow_day(19) == dashboard._short(date(2026, 11, 19))


# --- profitability -----------------------------------------------------------------

def _pday(day, state, credit=None, value=None, need=0.282):
    res = dashboard.result_per_contract(credit, value, "cautious") if state == "done" else None
    best = dashboard.result_per_contract(credit, value, "best") if state == "done" else None
    return {"day": day, "state": state, "credit": credit, "value": value, "need": need, "result": res, "best": best}


def test_profit_summary_totals_wins_and_expectation():
    days = [_pday("Nov 18", "done", 0.25, 0.0), _pday("Nov 19", "no exit", 0.32),
            _pday("Nov 20", "no runs"), _pday("Nov 24", "done", 0.29, 0.01)]
    s = dashboard.profit_summary(days, width=5)
    assert (s["finished"], s["wins"], s["losses"]) == (2, 2, 0)
    assert s["total"] == pytest.approx(37.68) and s["totalBest"] == pytest.approx(48.68)
    assert s["avg"] == pytest.approx(18.84)
    assert s["expected"] == pytest.approx(-1.2, abs=0.01)        # credit minus the VIX-band need, x100
    assert s["risk"] == pytest.approx(480.66, abs=0.01)          # width minus credit, plus cautious costs
    assert s["winsToRepay"] == 26
    assert s["worst"] == pytest.approx(17.34)


def test_profit_gauge_uses_every_day_with_a_credit():
    days = [_pday("Nov 18", "done", 0.25, 0.0), _pday("Nov 19", "no exit", 0.32), _pday("Nov 24", "done", 0.29, 0.01)]
    g = dashboard.profit_summary(days, width=5)["gauge"]
    assert g["days"] == 3
    assert g["credit"] == pytest.approx(0.2867, abs=1e-4) and g["need"] == pytest.approx(0.282)
    assert g["margin"] == pytest.approx(0.0047, abs=1e-4)


def test_profit_summary_counts_a_losing_day():
    s = dashboard.profit_summary([_pday("a", "done", 0.25, 0.0), _pday("b", "done", 0.25, 1.25)], width=5)
    assert (s["wins"], s["losses"]) == (1, 1)
    assert s["worst"] == pytest.approx(-107.66)


def test_profit_summary_with_no_finished_days():
    s = dashboard.profit_summary([_pday("a", "no runs")], width=5)
    assert s["finished"] == 0 and s["total"] == 0 and s["avg"] is None and s["gauge"]["days"] == 0


@pytest.mark.skipif(not (ROOT / "data" / "snapshots" / "2026-11-24" / "1530.json").exists(), reason="no Nov 24 log")
def test_profit_days_on_real_logs():
    pt = dashboard.price_test(ROOT)
    days = dashboard.profit_days(ROOT, pt, {"shadow": {"width": 5, "k": 1.0}}, date(2026, 11, 24))
    got = {d["day"]: (d["state"], d["result"]) for d in days}
    assert got["Nov 18"] == ("done", pytest.approx(17.34))
    assert got["Nov 19"][0] == "no exit" and got["Nov 20"][0] == "no runs" and got["Nov 23"][0] == "no entry"
    assert got["Nov 24"] == ("done", pytest.approx(20.34))
    assert days[-1]["day"] == "Nov 24"


def test_static_file_serves_bundled_fonts_only():
    body, kind = dashboard.static_file(ROOT, "/static/fonts/Inter-Regular.ttf")
    assert kind == "font/ttf" and len(body) > 1000
    assert dashboard.static_file(ROOT, "/static/../../spybot/config.py") is None
    assert dashboard.static_file(ROOT, "/static/fonts/missing.ttf") is None
    assert dashboard.static_file(ROOT, "/static/%2e%2e/manual.json") is None
