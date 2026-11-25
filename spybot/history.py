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


# --- daily refresh -------------------------------------------------------------------

KINDS = {"spy_day": ("SPY", "day"), "vix_day": ("VIX", "day"), "spy_5min": ("SPY", "5minute")}


def _range(name: str) -> tuple[str, str]:
    """('2026-11-02', '2026-11-24') from 'spy_day_2026-11-02_2026-11-24.json'."""
    parts = Path(name).stem.split("_")
    return parts[-2], parts[-1]


def by_age(paths) -> list[Path]:
    """History files in load order: the one reaching the latest day last, so the newest download wins."""
    return sorted((Path(p) for p in paths), key=lambda p: (_range(p.name)[1], _range(p.name)[0]))


def save_history(root: Path, kind: str, source: Path) -> Path:
    """Save one downloaded Robinhood answer (plain JSON or text blocks) as data/history/KIND_FIRST_LAST.json,
    after checking it holds the right symbol and interval. Older refresh files of the same kind that the
    new file fully covers are removed."""
    from spybot.ingest import _load_tool_result
    symbol, interval = KINDS[kind]
    data = _load_tool_result(source)
    results = data["data"]["results"]
    if not results or results[0].get("symbol") != symbol:
        raise ValueError(f"{source}: expected {symbol} bars, got {results[0].get('symbol') if results else 'none'}")
    if results[0].get("interval") != interval:
        raise ValueError(f"{source}: expected {interval} bars, got {results[0].get('interval')}")
    days = sorted(_utc(b["begins_at"]).astimezone(ET).date() if interval != "day" else date.fromisoformat(b["begins_at"][:10])
                  for r in results for b in r["bars"])
    if not days:
        raise ValueError(f"{source}: no bars")
    first, last = days[0].isoformat(), days[-1].isoformat()
    folder = Path(root) / "data" / "history"
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"{kind}_{first}_{last}.json"
    out.write_text(json.dumps(data))
    for old in folder.glob(f"{kind}_*.json"):
        a, b = _range(old.name)
        if old != out and a >= first and b <= last:
            old.unlink()
    return out
