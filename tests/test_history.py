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
