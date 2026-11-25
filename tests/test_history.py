from datetime import date, time
from pathlib import Path

from spybot import history

FIX = Path(__file__).parent / "fixtures" / "history"


def test_loads_spy_daily_sample():
    bars, problems = history.load_daily([FIX / "spy_day.json"])
    assert bars[date(2022, 1, 3)] == history.DayBar(date(2022, 1, 3), 476.30, 477.85, 473.85, 477.71)
    assert problems == []


def test_loads_vix_daily_sample_and_drops_weekend_filler_quietly():
    bars, problems = history.load_daily([FIX / "vix_day.json"])
    assert bars[date(2022, 1, 3)].open == 17.6
    assert date(2022, 1, 8) not in bars
    assert problems == []


def test_interpolated_bars_are_dropped_and_reported():
    bars, problems = history.load_intraday([FIX / "spy_5min_filler.json"])
    assert bars == {}
    assert any("interpolated" in p for p in problems)


def test_missing_trading_day_is_reported():
    bars, _ = history.load_daily([FIX / "spy_day.json"])
    del bars[date(2022, 1, 5)]
    assert any("2022-01-05" in p for p in history.check_daily(bars, date(2022, 1, 3), date(2022, 1, 7)))


def test_bad_prices_are_reported():
    bars, _ = history.load_daily([FIX / "spy_day.json"])
    d = date(2022, 1, 4)
    bars[d] = history.DayBar(d, 479.0, 470.0, 475.0, 477.0)      # high < low
    bars[date(2022, 1, 6)] = history.DayBar(date(2022, 1, 6), 300.0, 301.0, 299.0, 300.0)  # -36% jump
    problems = history.check_daily(bars, date(2022, 1, 3), date(2022, 1, 7))
    assert any("2022-01-04" in p and "high" in p for p in problems)
    assert any("2022-01-06" in p and "jump" in p for p in problems)


def test_intraday_uses_eastern_time():
    intraday, problems = history.load_intraday([FIX / "spy_5min_morning.json", FIX / "spy_5min_afternoon.json"])
    day = date(2026, 11, 16)
    assert problems == []
    assert history.price_at(intraday, day, time(10, 15)) == 745.0499
    assert history.price_at(intraday, day, time(15, 30)) == 739.30
    assert history.price_at(intraday, day, time(11, 0)) is None


def test_cboe_mismatches_are_found():
    vix, _ = history.load_daily([FIX / "vix_day.json"])
    cboe = history.load_cboe(FIX / "cboe_vix.csv")
    assert cboe[date(2022, 1, 3)] == (17.6, 16.6)
    # 2022-01-06 close differs (19.61 vs 22.00); 2022-01-07 is not in the Cboe sample, so not judged
    assert history.cboe_mismatches(vix, cboe) == [date(2022, 1, 6)]


# --- daily refresh: save a downloaded answer under data/history and keep the newest ---
import json


def _answer(symbol, interval, days, value=1.0, index=False):
    bars = []
    for d in days:
        b = {"begins_at": f"{d}T00:00:00Z" if interval == "day" else f"{d}T14:30:00Z"}
        keys = ("open_value", "high_value", "low_value", "close_value") if index else \
               ("open_price", "high_price", "low_price", "close_price")
        b.update({k: str(value) for k in keys})
        bars.append(b)
    return {"data": {"results": [{"symbol": symbol, "interval": interval, "bars": bars}]}}


def test_save_history_names_file_by_its_range(tmp_path):
    src = tmp_path / "answer.txt"
    src.write_text(json.dumps([{"type": "text", "text": json.dumps(
        _answer("SPY", "day", ["2026-11-17", "2026-11-18", "2026-11-24"]))}]))
    out = history.save_history(tmp_path, "spy_day", src)
    assert out == tmp_path / "data" / "history" / "spy_day_2026-11-17_2026-11-24.json"
    assert json.loads(out.read_text())["data"]["results"][0]["symbol"] == "SPY"


def test_save_history_rejects_the_wrong_kind(tmp_path):
    src = tmp_path / "a.json"
    src.write_text(json.dumps(_answer("QQQ", "day", ["2026-11-17"])))
    try:
        history.save_history(tmp_path, "spy_day", src)
    except ValueError as e:
        assert "SPY" in str(e)
    else:
        raise AssertionError("accepted the wrong symbol")
    src.write_text(json.dumps(_answer("SPY", "5minute", ["2026-11-17"])))
    try:
        history.save_history(tmp_path, "spy_day", src)
    except ValueError as e:
        assert "day" in str(e)
    else:
        raise AssertionError("accepted the wrong interval")


def test_save_history_removes_older_refresh_files_it_fully_covers(tmp_path):
    hist = tmp_path / "data" / "history"
    hist.mkdir(parents=True)
    keep = hist / "spy_day_2021-12-01_2026-11-16.json"            # starts earlier: kept
    old = hist / "spy_day_2026-11-10_2026-11-20.json"             # inside the new range: removed
    keep.write_text(json.dumps(_answer("SPY", "day", ["2021-12-01", "2026-11-16"])))
    old.write_text(json.dumps(_answer("SPY", "day", ["2026-11-10", "2026-11-20"])))
    src = tmp_path / "a.json"
    src.write_text(json.dumps(_answer("SPY", "day", ["2026-11-02", "2026-11-24"])))
    history.save_history(tmp_path, "spy_day", src)
    assert sorted(p.name for p in hist.iterdir()) == ["spy_day_2021-12-01_2026-11-16.json",
                                                      "spy_day_2026-11-02_2026-11-24.json"]


def test_newest_download_wins_when_files_overlap(tmp_path):
    a = tmp_path / "vix_day_2024-06-01_2026-11-16.json"
    b = tmp_path / "vix_day_2023-11-25_2026-11-24.json"            # newer, but sorts earlier by name
    a.write_text(json.dumps(_answer("VIX", "day", ["2026-11-16"], value=1.0, index=True)))
    b.write_text(json.dumps(_answer("VIX", "day", ["2026-11-16"], value=2.0, index=True)))
    bars, _ = history.load_daily(history.by_age([a, b]))
    assert bars[date(2026, 11, 16)].close == 2.0


def test_save_history_command(tmp_path, capsys):
    from spybot.__main__ import main
    src = tmp_path / "a.json"
    src.write_text(json.dumps(_answer("SPY", "day", ["2026-11-17", "2026-11-18"])))
    assert main(["save-history", "spy_day", str(src), "--root", str(tmp_path)]) == 0
    assert "spy_day_2026-11-17_2026-11-18.json" in capsys.readouterr().out
    src.write_text("{}")
    assert main(["save-history", "spy_day", str(src), "--root", str(tmp_path)]) == 1
    assert "BAD" in capsys.readouterr().out
