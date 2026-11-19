import json
import shutil
from datetime import date, timedelta
from pathlib import Path

import pytest

from spybot import calendar, report
from spybot.__main__ import main

FIX = Path(__file__).parent / "fixtures"


def _write_history(root, start, end, price=500.0, vix=16.0, name="a"):
    days = calendar.trading_days(start, end)
    hist = root / "data" / "history"
    hist.mkdir(parents=True, exist_ok=True)
    spy_bars = [{"begins_at": f"{d}T00:00:00Z", "open_price": str(price), "high_price": str(price + 2),
                 "low_price": str(price - 2), "close_price": str(price - 1 if d.day % 7 == 0 else price),
                 "volume": 1, "session": "reg"} for d in days]
    vix_bars = [{"begins_at": f"{d}T00:00:00Z", "open_value": str(vix), "high_value": str(vix + 1),
                 "low_value": str(vix - 1), "close_value": str(vix)} for d in days]
    (hist / f"spy_day_{name}.json").write_text(json.dumps({"data": {"results": [{"symbol": "SPY", "bars": spy_bars}]}}))
    (hist / f"vix_day_{name}.json").write_text(json.dumps({"data": {"results": [{"symbol": "VIX", "bars": vix_bars}]}}))


@pytest.fixture
def tmp_root(tmp_path):
    _write_history(tmp_path, date(2023, 10, 2), date(2024, 3, 28))
    return tmp_path


@pytest.fixture
def tmp_root_with_2025_days(tmp_root):
    _write_history(tmp_root, date(2025, 1, 2), date(2025, 3, 28), price=600.0, vix=22.0, name="b")
    return tmp_root


@pytest.fixture
def tmp_root_with_filler(tmp_root):
    shutil.copy(FIX / "history" / "spy_5min_filler.json", tmp_root / "data" / "history" / "spy_5min_x.json")
    return tmp_root


@pytest.fixture
def tmp_root_with_log(tmp_root):
    _write_history(tmp_root, date(2026, 10, 1), date(2026, 11, 19), price=730.0, vix=26.0, name="c")
    raw = tmp_root / "data" / "raw" / "2026-11-17"
    raw.mkdir(parents=True)
    good = json.loads((FIX / "logger" / "good_1507.json").read_text())
    good["run_et"] = "2026-11-17T10:15:30-05:00"           # a real 10:15 run
    template = good["quotes"][0]["data"]["results"][0]
    template["quote"]["updated_at"] = "2026-11-17T15:15:20Z"
    good["instruments"], results = {}, []
    for side, strikes in (("put", range(690, 730)), ("call", range(730, 770))):
        for strike in strikes:
            iid = f"{side}-{strike}"
            good["instruments"][iid] = {"type": side, "strike": float(strike), "expiry": "2026-11-17"}
            q = json.loads(json.dumps(template))
            q["quote"]["instrument_id"] = iid
            results.append(q)
    good["quotes"] = [{"data": {"results": results}}]
    (raw / "1015.json").write_text(json.dumps(good))
    from spybot import ingest
    assert ingest.ingest(tmp_root, date(2026, 11, 17), "1015") == []
    return tmp_root


def test_report_starts_with_limits_text(tmp_root):
    md, _ = report.build_report(tmp_root, date(2026, 11, 20))
    assert md.lstrip().startswith("**What this test can and cannot show.**")


def test_report_has_period_tables_and_verdicts(tmp_root):
    md, rows = report.build_report(tmp_root, date(2026, 11, 20))
    assert "## Plan v2 rules (trend + skips), $5 wide" in md
    assert any(r["period"] == "validation" and r["n_traded"] > 0 for r in rows)
    assert len([r for r in rows if r["period"] == "validation"]) == 144


def test_report_never_contains_sealed_days(tmp_root_with_2025_days):
    md, rows = report.build_report(tmp_root_with_2025_days, date(2026, 11, 20))
    assert "2025-" not in md and "2026-0" not in md
    assert all(r["period"] in ("train", "validation", "logged") for r in rows)
    assert all("day" not in r for r in rows if r["period"] == "logged")


def test_final_includes_test_period(tmp_root_with_2025_days):
    md, rows = report.build_report(tmp_root_with_2025_days, date(2026, 11, 20), final=True)
    assert any(r["period"] == "test" and r["n_traded"] > 0 for r in rows)


def test_verdict_line_without_logs(tmp_root):
    md, _ = report.build_report(tmp_root, date(2026, 11, 20))
    assert "no logged days yet." in md


def test_logged_credits_show_as_averages(tmp_root_with_log):
    md, rows = report.build_report(tmp_root_with_log, date(2026, 11, 20))
    logged = [r for r in rows if r["period"] == "logged"]
    assert logged and all("day" not in r for r in logged)
    assert any(r["n_ok"] > 0 for r in logged)
    assert "logged days" in md and "2026-11-17" not in md


def test_cli_check_history_fails_on_problems(tmp_root_with_filler, capsys):
    assert main(["check-history", "--root", str(tmp_root_with_filler)]) != 0
    assert "interpolated" in capsys.readouterr().out


def test_cli_report_and_final_write_files(tmp_root):
    assert main(["report", "--root", str(tmp_root)]) == 0
    assert list((tmp_root / "reports").glob("backtest-*.md")) and list((tmp_root / "reports").glob("backtest-*.csv"))
    assert main(["final", "--root", str(tmp_root)]) == 0
    assert "final run" in (tmp_root / "reports" / "final-runs.log").read_text()


def test_known_bad_bars_are_excluded(tmp_root):
    from spybot import report as r
    spy, vix, _, problems = r._load(tmp_root)
    assert date(2023, 11, 2) not in vix
    assert any("2023-11-02" in p and "known bad" in p for p in problems)


def test_days_without_a_1015_run_are_listed(tmp_root_with_log):
    md, _ = report.build_report(tmp_root_with_log, date(2026, 11, 20))
    line = next(l for l in md.splitlines() if "no usable 10:15 run" in l)
    assert "2026-11-18" in line and "2026-11-19" in line and "2026-11-17" not in line


def test_logged_day_beyond_history_is_flagged(tmp_root_with_log):
    (tmp_root_with_log / "data" / "snapshots" / "2026-12-01").mkdir()
    md, _ = report.build_report(tmp_root_with_log, date(2026, 12, 2))
    line = next(l for l in md.splitlines() if "history not up to date" in l)
    assert "2026-12-01" in line


def test_verdict_is_band_matched(tmp_root_with_log):
    # history VIX is 16 (15-20 band); the logged run has VIX 26.79 (20-30 band)
    md, _ = report.build_report(tmp_root_with_log, date(2026, 11, 20))
    assert "no verdict" in md and "pays." not in md


def test_vix_days_that_differ_from_cboe_are_excluded(tmp_root):
    cboe = tmp_root / "data" / "cboe"
    cboe.mkdir(parents=True)
    (cboe / "VIX_History.csv").write_text("DATE,OPEN,HIGH,LOW,CLOSE\n03/06/2024,16.0,17.0,15.0,16.0\n03/07/2024,25.0,26.0,24.0,25.0\n")
    from spybot import report as r
    _, vix, _, problems = r._load(tmp_root)
    assert date(2024, 3, 7) not in vix and date(2024, 3, 6) in vix
    assert any("2024-03-07" in p and "Cboe" in p for p in problems)


def test_report_handles_legs_without_delta(tmp_root_with_log):
    path = tmp_root_with_log / "data" / "snapshots" / "2026-11-17" / "1015.json"
    snap = json.loads(path.read_text())
    for leg in snap["legs"].values():
        leg["delta"], leg["iv"] = None, None
    path.write_text(json.dumps(snap))
    md, rows = report.build_report(tmp_root_with_log, date(2026, 11, 20))
    logged = [r for r in rows if r["period"] == "logged" and r["n_ok"] > 0]
    assert logged and all(r["avg_abs_delta"] is None for r in logged)
