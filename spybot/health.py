"""Health of the daily workflow: which logger runs were planned, which passed, failed or never ran,
and whether the price history and calendar are up to date. Reads project files only."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from spybot import calendar, config

ET = ZoneInfo(config.MARKET_TZ)
MISSED_AFTER = timedelta(minutes=30)     # a run with no file 30 minutes after its time never ran
LOOKBACK_DAYS = 3                        # trading days checked for missed or failed runs
COVERAGE_DAYS = 60                       # warn when the calendar or event list ends sooner


def planned(day: date) -> tuple[str, ...]:
    """Logger runs scheduled for a day (the daily schedule began on config.LOGGER_START)."""
    return calendar.log_runs(day) if day >= config.LOGGER_START else ()


def slot_time(day: date, hhmm: str) -> datetime:
    return datetime.combine(day, time(int(hhmm[:2]), int(hhmm[2:])), tzinfo=ET)


def slot_state(root: Path, day: date, hhmm: str, now: datetime) -> str:
    """ok | bad (failed the check) | error (stopped before the check) | missed | upcoming."""
    snaps = Path(root) / "data" / "snapshots" / day.isoformat()
    raw = Path(root) / "data" / "raw" / day.isoformat()
    if (snaps / f"{hhmm}.json").exists():
        return "ok"
    if (snaps / f"{hhmm}.bad.json").exists():
        return "bad"
    if (raw / f"{hhmm}.error.txt").exists():
        return "error"
    return "missed" if slot_time(day, hhmm) + MISSED_AFTER < now else "upcoming"


def label(day: date, hhmm: str) -> str:
    t = time(int(hhmm[:2]), int(hhmm[2:]))
    return f"{day:%a %b} {day.day} {t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def recent_days(now: datetime, n: int = LOOKBACK_DAYS) -> list[date]:
    today = now.astimezone(ET).date()
    return calendar.trading_days(today - timedelta(days=3 * n + 7), today)[-n:]


def run_problems(root: Path, now: datetime) -> list[str]:
    words = {"bad": "failed the check", "error": "stopped with an error", "missed": "never ran"}
    out = []
    for day in recent_days(now):
        for hhmm in planned(day):
            state = slot_state(root, day, hhmm, now)
            if state in words:
                out.append(f"Logger run {label(day, hhmm)} {words[state]}.")
    return out


def next_planned(now: datetime) -> datetime | None:
    now = now.astimezone(ET)
    day = now.date()
    for _ in range(30):
        for hhmm in planned(day):
            if slot_time(day, hhmm) > now:
                return slot_time(day, hhmm)
        day += timedelta(days=1)
    return None


def history_missing(history_last: date, now: datetime) -> list[date]:
    """Trading days after the last history day and before today (today's bars arrive after the close)."""
    today = now.astimezone(ET).date()
    return calendar.trading_days(history_last + timedelta(days=1), today - timedelta(days=1))


def check(root: Path, now: datetime, history_last: date | None) -> list[str]:
    out = run_problems(root, now)
    if history_last is None:
        out.append("No price history found.")
    else:
        missing = history_missing(history_last, now)
        if missing:
            out.append(f"Price history is {len(missing)} trading day(s) behind (last day {history_last}).")
    return out + coverage_problems(now)


def coverage_problems(now: datetime) -> list[str]:
    out = []
    horizon = now.astimezone(ET).date() + timedelta(days=COVERAGE_DAYS)
    if calendar.covered_until() < horizon:
        out.append(f"Market calendar ends {calendar.covered_until()}; add the next year's holidays.")
    if calendar.events_covered_until() < horizon:
        out.append(f"Fed/CPI/jobs list ends {calendar.events_covered_until()}; add the next dates.")
    return out


def new_problems(state_path: Path, msgs: list[str]) -> list[str]:
    """The problems not reported last time; remembers the current list so each is reported once."""
    import json
    state_path = Path(state_path)
    try:
        before = set(json.loads(state_path.read_text()))
    except (OSError, ValueError):
        before = set()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(msgs))
    return [m for m in msgs if m not in before]


def notify_mac(messages: list[str]) -> None:
    """Show a macOS notification (works from the background service, outside Claude's sandbox)."""
    import subprocess
    text = messages[0] if len(messages) == 1 else f"{len(messages)} problems: {messages[0]}"
    text = text.replace("\\", "").replace('"', "'")[:200]
    subprocess.run(["osascript", "-e", f'display notification "{text}" with title "SPY bot needs a look"'],
                   check=False, capture_output=True)
