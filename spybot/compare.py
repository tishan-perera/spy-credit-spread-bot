"""Compare real logged credits with the price test's break-even credit."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from spybot import calendar, config
from spybot.ingest import Snapshot
from spybot.pricetest import DayInputs, Setup, _skips, expected_move, strikes, trend, vix_band


@dataclass(frozen=True)
class RealRow:
    day: date
    setup: Setup
    side: str
    short: int
    long: int
    status: str                      # "ok", "skipped", "not logged", "no 10:15 run"
    mid_credit: float | None
    natural_credit: float | None
    short_delta: float | None
    leg_gaps: tuple[float, float] | None
    value_1530: float | None
    value_1540: float | None
    vix_band: str | None = None
    skipped: tuple[str, ...] = ()


def _spread_mid(snap: Snapshot | None, side: str, short: int, long_: int) -> float | None:
    if snap is None or (side, short) not in snap.legs or (side, long_) not in snap.legs:
        return None
    return snap.legs[(side, short)].mark - snap.legs[(side, long_)].mark


def real_row(day: date, setup: Setup, snaps: dict[str, Snapshot | None],
             closes_before: tuple[float, ...], prev_close: float, open_price: float,
             events: tuple[str, ...] = ()) -> RealRow:
    morning = snaps.get("1015")
    if morning is None:
        return RealRow(day, setup, "put", 0, 0, "no 10:15 run", None, None, None, None, None, None)
    inp = DayInputs(day=day, entry=morning.spy, exit=morning.spy, open=open_price, prev_close=prev_close,
                    closes_before=closes_before, vix_open=morning.vix,
                    fraction=calendar.remaining_fraction(day, config.ENTRY_TIME), events=tuple(events),
                    real_times=True)
    band = vix_band(morning.vix)
    side, skipped = "put", []
    if setup.variant in ("put_skips", "v2"):
        skipped = _skips(inp)
    if setup.variant == "v2":
        t = trend(inp)
        if t == "down":
            side = "call"
        elif t == "unclear":
            skipped.append("trend unclear")
    short, long_ = strikes(inp.entry, expected_move(inp), side, setup.k, setup.width)
    if skipped:
        return RealRow(day, setup, side, short, long_, "skipped", None, None, None, None, None, None,
                       band, tuple(skipped))
    s, l = morning.legs.get((side, short)), morning.legs.get((side, long_))
    if s is None or l is None:
        return RealRow(day, setup, side, short, long_, "not logged", None, None, None, None, None, None, band)
    return RealRow(
        day, setup, side, short, long_, "ok",
        mid_credit=s.mark - l.mark,
        natural_credit=s.bid - l.ask,
        short_delta=s.delta,
        leg_gaps=(s.ask - s.bid, l.ask - l.bid),
        value_1530=_spread_mid(snaps.get("1530"), side, short, long_),
        value_1540=_spread_mid(snaps.get("1540"), side, short, long_),
        vix_band=band,
    )


def delta_by_k(rows: list[RealRow]) -> dict[float, float]:
    found: dict[float, list[float]] = {}
    for r in rows:
        if r.status == "ok" and r.short_delta is not None:
            found.setdefault(r.setup.k, []).append(abs(r.short_delta))
    return {k: sum(v) / len(v) for k, v in found.items()}
