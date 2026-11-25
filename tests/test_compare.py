import math
from datetime import date, datetime, time, timezone

import pytest

from spybot import compare
from spybot.ingest import Leg, Snapshot
from spybot.pricetest import Setup

DAY = date(2026, 11, 17)
F = 315 / 390
SPY = 730.0
VIX = 4.0 / (SPY / 100 * math.sqrt(F / 252))   # expected move = 4.0 → k=1 put short 726
FLAT = (SPY,) * 20


def leg(bid, ask, delta=-0.12):
    return Leg(bid, ask, 10, 10, (bid + ask) / 2, 0.4, delta, 100, 1000,
               datetime(2026, 11, 17, 15, 15, tzinfo=timezone.utc))


def snap(run, legs):
    return Snapshot(DAY, run, SPY, VIX, legs)


def snaps_with(**legs):
    parsed = {}
    for name, (bid, ask) in legs.items():
        side = "put" if name.startswith("put") else "call"
        parsed[(side, int(name[len(side):]))] = leg(bid, ask)
    return {"1015": snap(time(10, 15), parsed)}


def row(setup, snaps, prev_close=SPY):
    return compare.real_row(DAY, setup, snaps, FLAT, prev_close, SPY)


def test_mid_and_natural_credit():
    r = row(Setup(5, 1.0, "baseline"), snaps_with(put726=(0.41, 0.42), put721=(0.10, 0.11)))
    assert r.status == "ok" and (r.side, r.short, r.long) == ("put", 726, 721)
    assert r.mid_credit == pytest.approx(0.31) and r.natural_credit == pytest.approx(0.30)
    assert r.leg_gaps == pytest.approx((0.01, 0.01))
    assert r.short_delta == -0.12


def test_strike_outside_logged_range_is_not_logged():
    r = row(Setup(10, 2.0, "baseline"), snaps_with(put726=(0.41, 0.42)))
    assert r.status == "not logged" and r.mid_credit is None


def test_missing_1015_run():
    assert row(Setup(5, 1.0, "baseline"), {"1015": None}).status == "no 10:15 run"
    assert row(Setup(5, 1.0, "baseline"), {}).status == "no 10:15 run"


def test_v2_uses_call_side_in_downtrend():
    snaps = snaps_with(call734=(0.30, 0.31), call739=(0.05, 0.06))
    r = row(Setup(5, 1.0, "v2"), snaps, prev_close=SPY * 0.99)
    assert (r.side, r.short, r.long, r.status) == ("call", 734, 739, "ok")


def test_afternoon_values():
    snaps = snaps_with(put726=(0.41, 0.42), put721=(0.10, 0.11))
    snaps["exit"] = snap(time(15, 30), {("put", 726): leg(0.03, 0.04), ("put", 721): leg(0.0, 0.01)})
    r = row(Setup(5, 1.0, "baseline"), snaps)
    assert r.value_1530 == pytest.approx(0.03) and r.value_1540 is None


def test_delta_by_k_averages_absolute_delta():
    def row_k(k, delta):
        return compare.RealRow(DAY, Setup(5, k, "baseline"), "put", 726, 721, "ok", 0.3, 0.29,
                               delta, (0.01, 0.01), None, None)
    bad = compare.RealRow(DAY, Setup(5, 1.0, "baseline"), "put", 726, 721, "not logged",
                          None, None, None, None, None, None)
    assert compare.delta_by_k([row_k(1.0, -0.12), row_k(1.0, -0.16), bad]) == {1.0: pytest.approx(0.14)}


# --- review fixes -----------------------------------------------------------

def test_skip_rules_apply_to_logged_rows():
    snaps = snaps_with(put726=(0.41, 0.42), put721=(0.10, 0.11))
    up = SPY * 1.01                                    # uptrend so v2 sells puts
    cpi = compare.real_row(DAY, Setup(5, 1.0, "v2"), snaps, FLAT, up, up, events=("cpi",))
    assert cpi.status == "skipped" and cpi.mid_credit is None
    gap = compare.real_row(DAY, Setup(5, 1.0, "put_skips"), snaps, FLAT, up, up * 0.98)
    assert gap.status == "skipped"
    base = compare.real_row(DAY, Setup(5, 1.0, "baseline"), snaps, FLAT, up, up * 0.98, events=("cpi",))
    assert base.status == "ok"


def test_unclear_trend_is_skipped_for_v2():
    snaps = snaps_with(put726=(0.41, 0.42), put721=(0.10, 0.11))
    r = row(Setup(5, 1.0, "v2"), snaps)                # prev_close == average → unclear
    assert r.status == "skipped"


def test_logged_row_carries_vix_band():
    r = row(Setup(5, 1.0, "baseline"), snaps_with(put726=(0.41, 0.42), put721=(0.10, 0.11)))
    assert r.vix_band == "<15"                         # helper VIX is about 9.7
