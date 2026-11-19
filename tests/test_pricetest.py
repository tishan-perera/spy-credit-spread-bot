import math
from datetime import date, time

import pytest

from spybot import calendar, pricetest
from spybot.history import DayBar
from spybot.pricetest import DayInputs, Setup

DAY = date(2024, 3, 6)  # Wednesday, normal close


def inp(**kw):
    base = dict(day=DAY, entry=500.0, exit=500.0, open=500.0, prev_close=500.0,
                closes_before=(500.0,) * 20, vix_open=16.0, fraction=315 / 390,
                events=(), real_times=False)
    base.update(kw)
    return DayInputs(**base)


def spy_history(day=DAY, n=25, price=500.0):
    days = calendar.trading_days(date(2024, 1, 1), day)[-n:]
    return {d: DayBar(d, price, price + 1, price - 1, price) for d in days}


def vix_history(days, value=16.0):
    return {d: DayBar(d, value, value + 1, value - 1, value) for d in days}


# --- formulas -------------------------------------------------------------

def test_expected_move():
    assert pricetest.expected_move(inp()) == pytest.approx(500 * 0.16 * math.sqrt((315 / 390) / 252))


def test_put_strikes_round_to_nearest_dollar():
    assert pricetest.strikes(500.0, 4.5, "put", 1.0, 5) == (496, 491)    # 495.5 rounds up
    assert pricetest.strikes(500.0, 4.5, "call", 1.0, 5) == (505, 510)   # 504.5 rounds up
    assert pricetest.strikes(500.0, 4.4, "put", 1.0, 2) == (496, 494)    # 495.6


def test_exit_value_partial_and_full_loss():
    assert pricetest.exit_value("put", 496, 5, 497.0) == 0
    assert pricetest.exit_value("put", 496, 5, 494.0) == 2.0
    assert pricetest.exit_value("put", 496, 5, 480.0) == 5
    assert pricetest.exit_value("call", 505, 5, 507.5) == 2.5


# --- trend and look-ahead --------------------------------------------------

def test_trend_rule():
    assert pricetest.trend(inp(prev_close=505.0)) == "up"
    assert pricetest.trend(inp(prev_close=501.0)) == "unclear"
    assert pricetest.trend(inp(prev_close=495.0)) == "down"


def test_trend_ignores_trade_day_and_later():
    spy = spy_history()
    vix = vix_history(spy)
    a = pricetest.build_inputs(DAY, spy, vix, {}, {})
    later = dict(spy)
    later[DAY] = DayBar(DAY, 500.0, 600.0, 400.0, 590.0)             # trade day's own close changes
    nxt = calendar.trading_days(date(2024, 3, 7), date(2024, 3, 7))[0]
    later[nxt] = DayBar(nxt, 900.0, 901.0, 899.0, 900.0)             # a future day appears
    b = pricetest.build_inputs(DAY, later, vix_history(later), {}, {})
    assert a.closes_before == b.closes_before and a.prev_close == b.prev_close
    assert pricetest.trend(a) == pricetest.trend(b)
    assert len(a.closes_before) == 20


# --- skips and sides -------------------------------------------------------

def test_v2_skips_events_and_gap_down_but_baseline_does_not():
    day = inp(events=("cpi",), open=494.0)                           # 1.2% gap down
    r_base = pricetest.score_day(day, Setup(5, 1.0, "baseline"))
    r_v2 = pricetest.score_day(day, Setup(5, 1.0, "v2"))
    r_ps = pricetest.score_day(day, Setup(5, 1.0, "put_skips"))
    assert r_base.skipped == ()
    assert {"cpi", "gap down"} <= set(r_v2.skipped)
    assert {"cpi", "gap down"} <= set(r_ps.skipped)


def test_small_gap_is_not_skipped():
    assert pricetest.score_day(inp(open=496.0), Setup(5, 1.0, "put_skips")).skipped == ()


def test_v2_side_follows_trend():
    assert pricetest.score_day(inp(prev_close=505.0), Setup(5, 1.0, "v2")).side == "put"
    assert pricetest.score_day(inp(prev_close=495.0), Setup(5, 1.0, "v2")).side == "call"
    unclear = pricetest.score_day(inp(), Setup(5, 1.0, "v2"))
    assert unclear.side == "put" and "trend unclear" in unclear.skipped


def test_score_day_value_uses_exit_price():
    move = pricetest.expected_move(inp())
    r = pricetest.score_day(inp(exit=480.0), Setup(5, 1.0, "baseline"))
    assert (r.short, r.long) == pricetest.strikes(500.0, move, "put", 1.0, 5)
    assert r.value == 5 and r.vix_open == 16.0


# --- build_inputs ----------------------------------------------------------

def test_build_inputs_uses_real_times_when_available():
    spy = spy_history()
    vix = vix_history(spy)
    intraday = {DAY: {time(10, 15): 501.0, time(15, 30): 499.0}}
    a = pricetest.build_inputs(DAY, spy, vix, intraday, {DAY: ["cpi"]})
    assert (a.entry, a.exit, a.real_times, a.events) == (501.0, 499.0, True, ("cpi",))
    b = pricetest.build_inputs(DAY, spy, vix, {DAY: {time(10, 15): 501.0}}, {})
    assert (b.entry, b.exit, b.real_times) == (500.0, 500.0, False)
    assert a.fraction == pytest.approx(315 / 390)


def test_build_inputs_early_close_day():
    day = date(2024, 12, 24)
    spy = spy_history(day)
    intraday = {day: {time(10, 15): 501.0, time(12, 30): 498.0}}
    a = pricetest.build_inputs(day, spy, vix_history(spy), intraday, {})
    assert a.exit == 498.0 and a.fraction == pytest.approx(135 / 390)


def test_build_inputs_none_when_data_missing():
    spy = spy_history()
    vix = vix_history(spy)
    del vix[DAY]
    assert pricetest.build_inputs(DAY, spy, vix, {}, {}) is None
    short = spy_history(n=15)
    assert pricetest.build_inputs(DAY, short, vix_history(short), {}, {}) is None


# --- Task 5: sweep and break-even -----------------------------------------

def result(value=0.0, skipped=(), vix=16.0, day=DAY):
    return pricetest.DayResult(day, "put", 496, 491, value, tuple(skipped), vix)


def test_cost_per_share_matches_plan_v2():
    assert pricetest.cost_per_share("cautious") == pytest.approx(0.0766)
    assert pricetest.cost_per_share("best") == pytest.approx(0.0216)


def test_breakeven_is_average_value_plus_costs():
    s = pricetest.summarize([result(0.0), result(0.0), result(0.0), result(5.0)], 5)
    assert s.avg_value == pytest.approx(1.25)
    assert s.breakeven["cautious"] == pytest.approx(1.25 + 0.0766)
    assert s.breakeven["best"] == pytest.approx(1.25 + 0.0216)
    assert s.loss_rate == 0.25 and s.full_loss_rate == 0.25


def test_skipped_days_are_counted_but_not_averaged():
    s = pricetest.summarize([result(5.0, skipped=("cpi",)), result(0.0)], 5)
    assert (s.n_traded, s.n_skipped, s.avg_value) == (1, 1, 0.0)


def test_summary_with_no_traded_days():
    s = pricetest.summarize([result(5.0, skipped=("cpi",))], 5)
    assert s.n_traded == 0 and s.avg_value is None and s.breakeven == {}


def test_worst_streak():
    vals = [0, 1, 2, 0, 1, 1, 1, 0]
    assert pricetest.summarize([result(v) for v in vals], 5).worst_streak == 3


def test_breakeven_by_vix_band():
    s = pricetest.summarize([result(0.0, vix=12), result(2.0, vix=12), result(5.0, vix=35)], 5)
    assert s.by_band["<15"] == (2, pytest.approx(1.0 + 0.0766))
    assert s.by_band["30+"] == (1, pytest.approx(5.0 + 0.0766))
    assert "15-20" not in s.by_band


def test_vix_band_edges():
    assert [pricetest.vix_band(v) for v in (14.9, 15, 20, 30)] == ["<15", "15-20", "20-30", "30+"]


def test_in_period():
    assert pricetest.in_period(date(2023, 12, 29), "train")
    assert pricetest.in_period(date(2024, 1, 2), "validation")
    assert pricetest.in_period(date(2026, 11, 17), "test")
    assert not pricetest.in_period(date(2025, 1, 2), "validation")


def test_sealed_period_refused():
    with pytest.raises(PermissionError):
        pricetest.run_sweep([], "test")
    assert len(pricetest.run_sweep([], "test", allow_sealed=True)) == 144


def test_sweep_covers_144_setups_and_filters_period():
    out = pricetest.run_sweep([inp(day=date(2024, 3, 6)), inp(day=date(2023, 3, 6))], "validation")
    assert len(out) == 144
    assert len({s for s, _ in out}) == 144
    assert all(s.n_traded + s.n_skipped == 1 for _, s in out)


def test_build_inputs_none_when_previous_trading_day_missing():
    spy = spy_history()
    vix = vix_history(spy)
    prev = calendar.trading_days(date(2024, 3, 5), date(2024, 3, 5))[0]
    del spy[prev]
    assert pricetest.build_inputs(DAY, spy, vix, {}, {}) is None
