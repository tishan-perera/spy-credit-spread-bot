"""Load and check historical bars saved from Robinhood (unchanged tool output)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from spybot import calendar, config

ET = ZoneInfo(config.MARKET_TZ)
MAX_DAILY_MOVE = 0.25


@dataclass(frozen=True)
class DayBar:
    day: date
    open: float
    high: float
    low: float
    close: float


def _bars(path: Path):
    for result in json.loads(Path(path).read_text())["data"]["results"]:
        yield from result["bars"]


def _ohlc(bar: dict) -> tuple[float, float, float, float]:
    if "open_price" in bar:  # equity format
        keys = ("open_price", "high_price", "low_price", "close_price")
    else:                    # index format
        keys = ("open_value", "high_value", "low_value", "close_value")
    return tuple(float(bar[k]) for k in keys)


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def load_daily(paths: list[Path]) -> tuple[dict[date, DayBar], list[str]]:
    bars: dict[date, DayBar] = {}
    problems: list[str] = []
    for path in paths:
        for bar in _bars(path):
            day = date.fromisoformat(bar["begins_at"][:10])
            if bar.get("interpolated"):
                if calendar.is_trading_day(day):
                    problems.append(f"{day}: interpolated daily bar dropped ({Path(path).name})")
                continue
            o, h, l, c = _ohlc(bar)
            bars[day] = DayBar(day, o, h, l, c)
    return bars, problems


def load_intraday(paths: list[Path]) -> tuple[dict[date, dict[time, float]], list[str]]:
    out: dict[date, dict[time, float]] = {}
    problems: list[str] = []
    for path in paths:
        for bar in _bars(path):
            local = _utc(bar["begins_at"]).astimezone(ET)
            if bar.get("interpolated"):
                problems.append(f"{local.date()} {local.time()}: interpolated intraday bar dropped ({Path(path).name})")
                continue
            out.setdefault(local.date(), {})[local.time()] = _ohlc(bar)[0]
    return out, problems


def check_daily(bars: dict[date, DayBar], start: date, end: date) -> list[str]:
    problems: list[str] = []
    prev: DayBar | None = None
    for day in calendar.trading_days(start, end):
        bar = bars.get(day)
        if bar is None:
            problems.append(f"{day}: missing trading day")
            continue
        if min(bar.open, bar.high, bar.low, bar.close) <= 0:
            problems.append(f"{day}: price at or below zero")
        if bar.high < bar.low:
            problems.append(f"{day}: high below low")
        if prev is not None and abs(bar.close / prev.close - 1) > MAX_DAILY_MOVE:
            problems.append(f"{day}: close-to-close jump over {MAX_DAILY_MOVE:.0%}")
        prev = bar
    return problems


def price_at(intraday: dict[date, dict[time, float]], day: date, t: time) -> float | None:
    return intraday.get(day, {}).get(t)


CBOE_TOLERANCE = 0.05   # VIX points; a larger gap on open or close means Robinhood's bar is wrong


def load_cboe(path: Path) -> dict[date, tuple[float, float]]:
    """Cboe's published VIX history (DATE,OPEN,HIGH,LOW,CLOSE with MM/DD/YYYY dates)."""
    import csv
    out: dict[date, tuple[float, float]] = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            day = datetime.strptime(row["DATE"], "%m/%d/%Y").date()
            out[day] = (float(row["OPEN"]), float(row["CLOSE"]))
    return out


def cboe_mismatches(vix: dict[date, DayBar], cboe: dict[date, tuple[float, float]]) -> list[date]:
    bad = []
    for day in sorted(vix):
        if day in cboe:
            o, c = cboe[day]
            if abs(vix[day].open - o) > CBOE_TOLERANCE or abs(vix[day].close - c) > CBOE_TOLERANCE:
                bad.append(day)
    return bad
