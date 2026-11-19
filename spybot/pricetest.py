"""Price test: score past days and compute the break-even credit for each setup.

Uses only SPY and VIX prices. Option credits for past days are unknown, so the
test reports the credit each setup would have needed after costs.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, time

from spybot import calendar, config
from spybot.history import DayBar, price_at

VARIANTS = ("baseline", "put_skips", "v2")


@dataclass(frozen=True)
class Setup:
    width: int
    k: float
    variant: str


@dataclass(frozen=True)
class DayInputs:
    day: date
    entry: float
    exit: float
    open: float
    prev_close: float
    closes_before: tuple[float, ...]
    vix_open: float
    fraction: float
    events: tuple[str, ...]
    real_times: bool


@dataclass(frozen=True)
class DayResult:
    day: date
    side: str
    short: int
    long: int
    value: float
    skipped: tuple[str, ...]
    vix_open: float


def build_inputs(day: date, spy: dict[date, DayBar], vix: dict[date, DayBar],
                 intraday: dict[date, dict[time, float]],
                 events: dict[date, list[str]]) -> DayInputs | None:
    bar, vbar = spy.get(day), vix.get(day)
    if bar is None or vbar is None:
        return None
    before = [d for d in sorted(spy) if d < day][-config.TREND_LOOKBACK:]
    if len(before) < config.TREND_LOOKBACK or before[-1] != calendar.previous_trading_day(day):
        return None
    earlier = [spy[d].close for d in before]
    entry = price_at(intraday, day, config.ENTRY_TIME)
    exit_ = price_at(intraday, day, calendar.exit_time(day))
    real = entry is not None and exit_ is not None
    return DayInputs(
        day=day,
        entry=entry if real else bar.open,
        exit=exit_ if real else bar.close,
        open=bar.open,
        prev_close=earlier[-1],
        closes_before=tuple(earlier),
        vix_open=vbar.open,
        fraction=calendar.remaining_fraction(day, config.ENTRY_TIME),
        events=tuple(events.get(day, ())),
        real_times=real,
    )


def trend(inp: DayInputs) -> str:
    avg = sum(inp.closes_before[-config.TREND_LOOKBACK:]) / len(inp.closes_before[-config.TREND_LOOKBACK:])
    if inp.prev_close > avg * (1 + config.TREND_BAND):
        return "up"
    if inp.prev_close < avg * (1 - config.TREND_BAND):
        return "down"
    return "unclear"


def expected_move(inp: DayInputs) -> float:
    return inp.entry * inp.vix_open / 100 * math.sqrt(inp.fraction / 252)


def strikes(entry: float, move: float, side: str, k: float, width: int) -> tuple[int, int]:
    if side == "put":
        short = math.floor(entry - k * move + 0.5)
        return short, short - width
    short = math.floor(entry + k * move + 0.5)
    return short, short + width


def exit_value(side: str, short: int, width: int, exit_price: float) -> float:
    gap = short - exit_price if side == "put" else exit_price - short
    return min(max(gap, 0), width)


def _skips(inp: DayInputs) -> list[str]:
    reasons = list(inp.events)
    if inp.open < inp.prev_close * (1 - config.GAP_DOWN_SKIP):
        reasons.append("gap down")
    return reasons


def score_day(inp: DayInputs, setup: Setup) -> DayResult:
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
    return DayResult(inp.day, side, short, long_, exit_value(side, short, setup.width, inp.exit),
                     tuple(skipped), inp.vix_open)


# --- Sweep and break-even credit --------------------------------------------

@dataclass(frozen=True)
class Summary:
    n_traded: int
    n_skipped: int
    loss_rate: float | None
    full_loss_rate: float | None
    worst_streak: int
    avg_value: float | None
    breakeven: dict[str, float]
    by_band: dict[str, tuple[int, float]]


def cost_per_share(case: str) -> float:
    return config.FEES_ROUND_TRIP / 100 + sum(config.SLIPPAGE[case])


def vix_band(vix: float) -> str:
    low, mid, high = config.VIX_BANDS
    if vix < low:
        return f"<{low}"
    if vix < mid:
        return f"{low}-{mid}"
    if vix < high:
        return f"{mid}-{high}"
    return f"{high}+"


def summarize(results: list[DayResult], width: int) -> Summary:
    traded = [r for r in results if not r.skipped]
    n = len(traded)
    streak = worst = 0
    for r in sorted(traded, key=lambda r: r.day):
        streak = streak + 1 if r.value > 0 else 0
        worst = max(worst, streak)
    if n == 0:
        return Summary(0, len(results), None, None, 0, None, {}, {})
    avg = sum(r.value for r in traded) / n
    bands: dict[str, list[float]] = {}
    for r in traded:
        bands.setdefault(vix_band(r.vix_open), []).append(r.value)
    return Summary(
        n_traded=n,
        n_skipped=len(results) - n,
        loss_rate=sum(r.value > 0 for r in traded) / n,
        full_loss_rate=sum(r.value >= width for r in traded) / n,
        worst_streak=worst,
        avg_value=avg,
        breakeven={case: avg + cost_per_share(case) for case in config.SLIPPAGE},
        by_band={b: (len(v), sum(v) / len(v) + cost_per_share("cautious")) for b, v in bands.items()},
    )


def in_period(day: date, period: str) -> bool:
    start, end = config.PERIODS[period]
    return day >= start and (end is None or day <= end)


def all_setups() -> list[Setup]:
    return [Setup(w, k, v) for v in VARIANTS for w in config.WIDTHS for k in config.K_VALUES]


def run_sweep(inputs: list[DayInputs], period: str, allow_sealed: bool = False) -> list[tuple[Setup, Summary]]:
    if period == "test" and not allow_sealed:
        raise PermissionError("test period is sealed")
    days = [i for i in inputs if in_period(i.day, period)]
    return [(s, summarize([score_day(i, s) for i in days], s.width)) for s in all_setups()]
