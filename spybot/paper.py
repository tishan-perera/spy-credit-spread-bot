"""Paper trading (plan v2 stage 3): replay each logged day's ticket with cautious costs,
apply the guardrails, and check the go-live gate. No orders anywhere."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from spybot import config
from spybot.compare import RealRow
from spybot.pricetest import cost_per_share, exit_value
from spybot.ticket import Ticket, make_ticket


@dataclass(frozen=True)
class DayIn:
    day: date
    row: RealRow | None
    need: float | None
    spy_close: float | None = None      # settlement fallback when both exit runs are missing


@dataclass(frozen=True)
class Entry:
    day: date
    action: str
    reason: str
    ticket: Ticket
    exit_source: str | None = None      # "3:30", "3:40", "close (...)" or "missing"
    exit_value: float | None = None
    result: float | None = None         # dollars per contract after cautious costs
    max_loss: float | None = None


def _week(d: date) -> tuple[int, int]:
    return d.isocalendar()[:2]


def _exit(d: DayIn) -> tuple[str, float | None]:
    r = d.row
    if r.value_1530 is not None:
        return "3:30", r.value_1530
    if r.value_1540 is not None:
        return "3:40", r.value_1540
    if d.spy_close is not None:
        return "close (3:30 and 3:40 missed)", exit_value(r.side, r.short, r.setup.width, d.spy_close)
    return "missing", None


def ledger(days: list[DayIn]) -> list[Entry]:
    out, week, streak, week_loss, halt = [], None, 0, 0.0, None
    for d in sorted(days, key=lambda x: x.day):
        if _week(d.day) != week:
            week, streak, week_loss, halt = _week(d.day), 0, 0.0, None
        t = make_ticket(d.row, d.need, halted=halt)
        if t.action != "trade":
            out.append(Entry(d.day, t.action, t.reason, t))
            continue
        source, value = _exit(d)
        result = None if value is None else round((d.row.mid_credit - value - cost_per_share("cautious")) * 100, 2)
        out.append(Entry(d.day, "trade", t.reason, t, source, value, result, t.max_loss))
        if result is None:
            continue
        streak = streak + 1 if result < 0 else 0
        week_loss += min(result, 0.0)
        if streak >= config.LOSS_STREAK_HALT:
            halt = f"{streak} losses in a row: halted until next week"
        elif -week_loss >= config.WEEKLY_LOSS_LIMIT_MAX_LOSSES * t.max_loss - 0.005:
            halt = f"weekly loss limit hit (${-week_loss:.2f}): halted until next week"
    return out


def summary(entries: list[Entry]) -> dict:
    done = [e.result for e in entries if e.action == "trade" and e.result is not None]
    return {"days": sum(e.action in ("trade", "skip") for e in entries),
            "trades": sum(e.action == "trade" for e in entries),
            "wins": sum(x > 0 for x in done), "losses": sum(x <= 0 for x in done),
            "total": round(sum(done), 2), "worst": min(done) if done else None,
            "unpriced": sum(e.action == "trade" and e.result is None for e in entries)}


def go_live_gate(logged_days: int, target_days: int, ledger: list[Entry], leg_gap: float | None,
                 account_rule_met: bool) -> list[dict]:
    s = summary(ledger)
    assumed = config.SLIPPAGE["cautious"][0]
    return [
        {"check": "Logged days", "value": f"{logged_days} of {target_days}", "ok": logged_days >= target_days},
        {"check": "Paper-trading days", "value": f"{s['days']} of {config.PAPER_DAYS_TARGET}",
         "ok": s["days"] >= config.PAPER_DAYS_TARGET},
        {"check": "Paper result after cautious costs", "value": f"${s['total']:.2f} over {s['trades']} trades",
         "ok": s["trades"] > 0 and s["total"] > 0},
        {"check": "Real bid/ask gaps within the cost assumption",
         "value": "no data" if leg_gap is None else f"${leg_gap:.3f} per leg vs ${assumed:.3f} assumed",
         "ok": leg_gap is not None and leg_gap <= assumed},
        {"check": "Account size rule (owner)",
         "value": "met" if account_rule_met else "not met (1-2% rule)",
         "ok": bool(account_rule_met)},
    ]


def gate_passes(checks: list[dict]) -> bool:
    return all(c["ok"] for c in checks)
