"""Market calendar: trading days, early closes, same-day-expiry days, event days."""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path

from spybot import config

REFERENCE = Path(__file__).resolve().parent / "reference"


@lru_cache(maxsize=None)
def _market() -> tuple[frozenset, frozenset]:
    raw = json.loads((REFERENCE / "market_calendar.json").read_text())
    holidays = frozenset(date.fromisoformat(d) for d in raw["holidays"])
    early = frozenset(date.fromisoformat(d) for d in raw["early_closes"])
    return holidays, early


def is_trading_day(day: date) -> bool:
    return day.weekday() < 5 and day not in _market()[0]


def trading_days(start: date, end: date) -> list[date]:
    days, d = [], start
    while d <= end:
        if is_trading_day(d):
            days.append(d)
        d += timedelta(days=1)
    return days


def previous_trading_day(day: date) -> date:
    d = day - timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def close_time(day: date) -> time:
    return time(13, 0) if day in _market()[1] else time(16, 0)


def exit_time(day: date) -> time:
    close = datetime.combine(day, close_time(day))
    return (close - timedelta(minutes=config.EXIT_MINUTES_BEFORE_CLOSE)).time()


def remaining_fraction(day: date, start: time) -> float:
    minutes = (datetime.combine(day, exit_time(day)) - datetime.combine(day, start)).total_seconds() / 60
    return minutes / config.TRADING_MINUTES_PER_DAY


def has_0dte(day: date) -> bool:
    if not is_trading_day(day):
        return False
    if day.weekday() in (0, 2, 4):
        return True
    return day >= config.TUE_THU_0DTE_START


@lru_cache(maxsize=None)
def _events() -> dict[date, tuple[str, ...]]:
    raw = json.loads((REFERENCE / "events.json").read_text())
    out: dict[date, list[str]] = {}
    for label in ("fomc", "cpi", "jobs"):
        for text in raw[label]:
            day = date.fromisoformat(text)
            if is_trading_day(day):
                out.setdefault(day, []).append(label)
    return {d: tuple(v) for d, v in out.items()}


def event_days() -> dict[date, list[str]]:
    """Fed decision, CPI and jobs-report days that are trading days."""
    return {d: list(v) for d, v in _events().items()}
