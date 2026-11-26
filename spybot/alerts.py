"""Mac notifications for paper trading: a ticket is ready, and the 3:25 PM close reminder.

Sent by the dashboard service (which runs outside Claude), each at most once a day.
Nothing leaves the Mac. Notifications never place or close anything.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from spybot import calendar

REMIND_BEFORE, REMIND_AFTER = timedelta(minutes=5), timedelta(minutes=15)   # around the exit time


def due(status: dict, now: datetime, sent: set[str]) -> list[tuple[str, str, str]]:
    t = (status.get("paper") or {}).get("today")
    if not t or t.get("action") != "trade" or t.get("date") != now.date().isoformat():
        return []
    out = []
    key = f"{t['date']}:ticket"
    if key not in sent:
        out.append((key, "SPY paper ticket", f"{t.get('spread')} at ${t.get('limit'):.2f} credit. Paper only."))
    key = f"{t['date']}:close"
    exit_at = datetime.combine(now.date(), calendar.exit_time(now.date()))   # 3:30, or 12:30 on early closes
    clock = now.replace(tzinfo=None)
    if key not in sent and exit_at - REMIND_BEFORE <= clock < exit_at + REMIND_AFTER:
        label = f"{exit_at:%I:%M}".lstrip("0")
        out.append((key, "SPY close reminder",
                    f"Close {t.get('spread')} by {label} ET (paper). In a live stage you close it yourself."))
    return out


def load_sent(path: Path) -> set[str]:
    try:
        return set(json.loads(Path(path).read_text()))
    except (OSError, ValueError):
        return set()


def save_sent(path: Path, sent: set[str]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(sent)))


def notify(title: str, message: str) -> bool:
    """Show a macOS notification. Returns False if it could not be shown."""
    script = f"display notification {json.dumps(message)} with title {json.dumps(title)}"
    try:
        return subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def step(status: dict, now: datetime, sent_path: Path, send=notify) -> None:
    """Send whatever is due; remember an alert only after it was shown."""
    sent = load_sent(sent_path)
    shown = {key for key, title, msg in due(status, now, sent) if send(title, msg)}
    if shown:
        save_sent(sent_path, sent | shown)
