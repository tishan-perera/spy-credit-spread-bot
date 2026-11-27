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
                "evidence", "slippage", "skipBoard", "upcoming", "eod", "explorer", "profit", "asOfISO"):
        assert key in s, key
    # 9.34: with history through Nov 17 (refreshed 2026-11-25) Nov 18 is judged by plan v2 (call 742/747);
    # before the refresh it fell back to sell-every-day (17.34)
    assert s["shadow"]["resultCautious"] == pytest.approx(9.34)
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
    assert got["Nov 18"] == ("done", pytest.approx(9.34))          # plan v2 since the history refresh
    assert got["Nov 19"][0] == "no exit" and got["Nov 20"][0] == "no runs" and got["Nov 23"][0] == "no entry"
    assert got["Nov 24"] == ("done", pytest.approx(9.34))          # plan v2 (call 730/735) since the refresh
    assert days[-1]["day"] == "Nov 24"


def test_static_file_serves_bundled_fonts_only():
    body, kind = dashboard.static_file(ROOT, "/static/fonts/Inter-Regular.ttf")
    assert kind == "font/ttf" and len(body) > 1000
    assert dashboard.static_file(ROOT, "/static/../../spybot/config.py") is None
    assert dashboard.static_file(ROOT, "/static/fonts/missing.ttf") is None
    assert dashboard.static_file(ROOT, "/static/%2e%2e/manual.json") is None


# --- workflow health on the dashboard (planned runs come from the calendar) ---

@pytest.mark.skipif(not (ROOT / "data" / "history").exists(), reason="no local price history")
def test_usable_days_match_the_report(tmp_path):
    from spybot import report
    today = date(2026, 11, 25)
    pt = dashboard.price_test(ROOT)
    tp = dashboard.trading_panels(ROOT, pt, dashboard.load_manual(ROOT), today)
    spy = report._load(ROOT)[0]
    _, used, _, _, _ = report._logged_rows(ROOT, spy, pt["events"], today)
    assert tp["usableDays"] == len(used)


def test_calendar_comes_from_the_market_calendar(tmp_path):
    for h in ("1000", "1015", "1030", "1530", "1540"):
        _snap(tmp_path, "2026-11-24", h)
    _snap(tmp_path, "2026-11-25", "1000")
    _snap(tmp_path, "2026-11-25", "1015", bad=["x"])
    raw = tmp_path / "data" / "raw" / "2026-11-25"
    raw.mkdir(parents=True)
    (raw / "1030.error.txt").write_text("tool failed")
    now = datetime(2026, 11, 25, 15, 0, tzinfo=ET)
    grid = dashboard.calendar_grid(tmp_path, now)
    assert grid["Nov 25"] == {"10:00": "ok", "10:15": "bad", "10:30": "error", "3:30": "next", "3:40": "planned"}
    assert grid["Nov 24"]["3:40"] == "ok"
    assert list(grid)[-1] == "Nov 27"                      # next trading day, skipping Thanksgiving
    assert grid["Nov 27"]["3:30"] == "planned"             # its exit runs are 12:30/12:40, shown in the exit columns


@pytest.mark.skipif(not (ROOT / "data" / "history").exists(), reason="no local price history")
def test_dashboard_alerts_and_next_run_come_from_health(tmp_path):
    s = dashboard.collect(tmp_path, datetime(2026, 11, 25, 16, 30, tzinfo=ET), tests={"passed": 1, "failed": 0},
                          transcripts=tmp_path, pt=dashboard.price_test(ROOT))
    texts = [a["text"] for a in s["alerts"]]
    assert "Logger run Wed Nov 25 10:00 AM never ran." in texts
    assert s["nextRunISO"] == "2026-11-27T10:00:00-05:00"
    assert "trading day" in s["logger"]["daily"]


def test_daily_task_run_is_labelled_from_task_name_and_start_time(tmp_path):
    (tmp_path / "run.jsonl").write_text("\n".join([
        _line(type="queue-operation", timestamp="2026-11-25T15:22:31.000Z"),
        _line(type="user", message={"content": '<scheduled-task name="spy-logger-1030" file="x"> '
                                               "follow collector/logger-task.md, with DAY = today's date"}),
        _assistant("m1", [("Bash", {"command": "cat > notes"})], out=4),
    ]))
    runs = dashboard.scan_transcripts(tmp_path)["loggerRuns"]
    assert [(r["day"], r["hhmm"], r["output"]) for r in runs] == [("2026-11-25", "1030", 4)]


def test_cost_per_day_totals():
    runs = [{"day": "2026-11-25", "output": 1, "write": 2, "reread": 3},
            {"day": "2026-11-25", "output": 10, "write": 20, "reread": 30}]
    assert dashboard.cost_per_day(runs) == [{"day": "2026-11-25", "runs": 2, "output": 11, "write": 22, "reread": 33}]


def test_calendar_shows_runs_that_happened_before_the_daily_schedule(tmp_path):
    # Nov 23 is before config.LOGGER_START, so nothing was planned, but two runs did happen and passed.
    _snap(tmp_path, "2026-11-23", "1530")
    _snap(tmp_path, "2026-11-23", "1540")
    grid = dashboard.calendar_grid(tmp_path, datetime(2026, 11, 25, 15, 0, tzinfo=ET))
    assert grid["Nov 23"] == {"10:00": "off", "10:15": "off", "10:30": "off", "3:30": "ok", "3:40": "ok"}


@pytest.mark.skipif(not (ROOT / "data" / "history").exists(), reason="no local price history")
def test_every_progress_counter_uses_finished_days(tmp_path):
    # One definition on every tab: a day counts once its would-be trade has a real 10:15 entry and 3:30 exit.
    s = dashboard.collect(ROOT, datetime(2026, 11, 25, 16, 30, tzinfo=ET),
                          tests={"passed": 1, "failed": 0}, transcripts=tmp_path)
    assert s["verdictDays"] == s["profit"]["finished"]
    if (ROOT / "data" / "snapshots" / "2026-11-24" / "1530.json").exists():
        assert s["verdictDays"] == 2       # Nov 18 and Nov 24; Nov 19 had no 3:30 log, Nov 25 sat out


def test_profit_months_lists_every_weekday_with_market_status():
    months = dashboard.profit_months(date(2026, 11, 18), date(2026, 12, 3))
    assert [m["month"] for m in months] == ["2026-11", "2026-12"]
    nov = {d["date"]: d for d in months[0]["days"]}
    assert months[0]["label"] == "November 2026"
    assert min(nov) == "2026-11-02" and max(nov) == "2026-11-30"   # weekdays only, whole month
    assert len(nov) == 21 and "2026-11-21" not in nov              # no weekends
    assert nov["2026-11-26"]["open"] is False                      # Thanksgiving
    assert nov["2026-11-27"]["early"] is True and nov["2026-11-24"]["early"] is False


@pytest.mark.skipif(not (ROOT / "data" / "history").exists(), reason="no local price history")
@pytest.mark.skipif(not (ROOT / "data" / "snapshots" / "2026-11-18").exists(), reason="no Nov 18 log")
def test_profit_days_cover_every_trading_day_since_the_first_log():
    pt = dashboard.price_test(ROOT)
    days = dashboard.profit_days(ROOT, pt, {"shadow": {"width": 5, "k": 1.0}}, date(2027, 1, 29))
    assert days[0]["date"] == "2026-11-18" and days[-1]["date"] == "2027-01-29"   # no 10-day cap


@pytest.mark.skipif(not (ROOT / "data" / "snapshots" / "2026-11-24").exists(), reason="no Nov 24 log")
def test_paper_panel_replays_logged_days(tmp_path):
    s = dashboard.collect(ROOT, datetime(2026, 11, 24, 16, 52, tzinfo=ET),
                          tests={"passed": 1, "failed": 0}, transcripts=tmp_path)
    p = s["paper"]
    json.dumps(p)
    by_day = {e["date"]: e for e in p["ledger"]}
    assert by_day["2026-11-18"]["action"] == "trade" and by_day["2026-11-18"]["result"] == pytest.approx(9.34)
    assert by_day["2026-11-24"]["result"] == pytest.approx(9.34)
    assert p["today"]["date"] == "2026-11-24" and p["today"]["action"] in ("trade", "skip", "no data")
    assert [c["check"] for c in p["gate"]][0] == "Logged days" and p["gatePasses"] is False
    assert p["summary"]["days"] >= 2 and p["targetDays"] == 30


def test_dashboard_works_on_a_new_computer_with_no_data(tmp_path):
    # SETUP.md installs the dashboard service before any price history is downloaded.
    pt = dashboard.price_test(tmp_path)
    assert pt["inputs"] == []
    s = dashboard.collect(tmp_path, datetime(2026, 11, 25, 16, 30, tzinfo=ET),
                          tests={"passed": 1, "failed": 0}, transcripts=tmp_path, pt=pt)
    json.dumps(s)
