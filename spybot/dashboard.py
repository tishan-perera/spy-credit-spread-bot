"""Local read-only dashboard: gathers project status from files and serves one page.

Reads only: project files, git, the project's Claude run records, and the local
price history. It never calls Robinhood and never changes anything.
Hand-kept items (rollout stages, decisions, schedule) live in dashboard/manual.json.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time as _time
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote
from zoneinfo import ZoneInfo

from spybot import calendar, compare, config, ingest, pricetest, report
from spybot.pricetest import Setup

ET = ZoneInfo(config.MARKET_TZ)
# The audit must name the forbidden tools in order to count them. Names only; nothing here calls them.
# <!-- forbidden-start -->
BROKER_SERVERS = ("mcp__robinhood__", "mcp__54da6bf0-5ad5-4b1a-b2c8-3eb2d921e7d1__")
ORDER_TOOLS = ("place_option_order", "place_equity_order", "place_advanced_order", "place_crypto_order",
               "cancel_option_order", "cancel_equity_order", "cancel_advanced_order", "cancel_crypto_order",
               "cancel_option_exercise", "exercise_option", "decline_trade_approval")
PREVIEW_TOOLS = ("review_option_order", "review_equity_order", "review_advanced_order", "preview_crypto_order")
ORDER_PREFIXES = ("place_", "cancel_")
# <!-- forbidden-end -->
EVENT_NAMES = {"fomc": "Fed decision", "cpi": "CPI report", "jobs": "Jobs report"}
SLOTS = tuple(f"{t.hour:02d}{t.minute:02d}" for t in config.LOG_TIMES)
NOTES_RE = re.compile(r"data/raw/(\d{4}-\d{2}-\d{2})/(\d{4})\.notes\.txt")
TASK_RE = re.compile(r"DAY = (\d{4}-\d{2}-\d{2}) and HHMM = (\d{4})")


# --- small formatting helpers --------------------------------------------------

def _clock(hhmm: str) -> str:
    h, m = int(hhmm[:2]), int(hhmm[2:])
    return f"{h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def _slot(hhmm: str) -> str:
    h, m = int(hhmm[:2]), int(hhmm[2:])
    return f"{h % 12 or 12}:{m:02d}"


def _short(day: date) -> str:
    return f"{day:%b} {day.day}"


def _when(dt: datetime) -> str:
    dt = dt.astimezone(ET)
    return f"{dt:%a} {_short(dt.date())} · {_clock(f'{dt:%H%M}')} ET"


def _r(x, n=3):
    return None if x is None else round(x, n)


# --- logger runs and calendar --------------------------------------------------

def logger_runs(root: Path) -> list[dict]:
    """Every checked logger run: one per HHMM.json (passed) or HHMM.bad.json (failed)."""
    runs = []
    snap_root = Path(root) / "data" / "snapshots"
    for folder in sorted(p for p in snap_root.glob("*") if p.is_dir()):
        for path in sorted(folder.glob("*.json")):
            hhmm, bad = path.name.split(".")[0], path.name.endswith(".bad.json")
            data = json.loads(path.read_text())
            runs.append({"day": folder.name, "hhmm": hhmm, "time": _clock(hhmm),
                         "result": "bad" if bad else "ok",
                         "contracts": None if bad else len(data.get("legs", {})),
                         "problems": data.get("problems", []) if bad else []})
    return runs


def calendar_grid(runs: list[dict], scheduled: list[dict], now: datetime) -> dict:
    """Last three trading days up to today, plus the next one; each slot ok/bad/missed/next/off."""
    today = now.astimezone(ET).date()
    days = [d for d in calendar.trading_days(today - timedelta(days=10), today)][-3:]
    nxt = today + timedelta(days=1)
    while not calendar.is_trading_day(nxt):
        nxt += timedelta(days=1)
    days.append(nxt)
    done = {(r["day"], r["hhmm"]): r["result"] for r in runs}
    planned = {(s["day"], s["hhmm"]) for s in scheduled}
    grid, next_marked = {}, False
    for day in days:
        row = {}
        for hhmm in SLOTS:
            key = (day.isoformat(), hhmm)
            slot_time = datetime(day.year, day.month, day.day, int(hhmm[:2]), int(hhmm[2:]), tzinfo=ET)
            if key in done:
                state = done[key]
            elif key in planned and slot_time + timedelta(minutes=30) < now:
                state = "missed"
            elif key in planned and not next_marked:
                state, next_marked = "next", True
            else:
                state = "off"
            row[_slot(hhmm)] = state
        grid[_short(day)] = row
    return grid


def next_run(scheduled: list[dict], now: datetime) -> dict | None:
    ahead = sorted((datetime.fromisoformat(s["when"]), s) for s in scheduled
                   if datetime.fromisoformat(s["when"]) > now)
    if not ahead:
        return None
    dt, s = ahead[0]
    return {"iso": s["when"], "when": _when(dt), "what": s.get("what", "")}


# --- Claude run records: order audit and logger cost ------------------------------

def _first_user_text(lines: list[dict]) -> str:
    for obj in lines:
        if obj.get("type") == "user":
            c = obj.get("message", {}).get("content")
            if isinstance(c, str):
                return c
            if isinstance(c, list):
                return " ".join(b.get("text", "") for b in c if isinstance(b, dict))
    return ""


def scan_transcripts(folder: Path) -> dict:
    out = {"transcripts": 0, "toolCalls": 0, "orderCalls": 0, "previewCalls": 0, "previewWhen": None,
           "loggerRuns": []}
    folder = Path(folder)
    if not folder.exists():
        return out
    previews, seen = [], set()
    for path in sorted(folder.rglob("*.jsonl")):
        lines = []
        for text in path.read_text(errors="replace").splitlines():
            try:
                lines.append(json.loads(text))
            except ValueError:
                continue
        out["transcripts"] += 1
        first = _first_user_text(lines)
        is_logger = "logger-task.md" in first
        m = TASK_RE.search(first)
        usage, label = {}, (m.groups() if m else None)
        for obj in lines:
            if obj.get("type") != "assistant":
                continue
            msg = obj.get("message", {})
            if is_logger and msg.get("id") and isinstance(msg.get("usage"), dict):
                usage[msg["id"]] = msg["usage"]
            for block in msg.get("content") or []:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                name = block.get("name", "")
                tid = block.get("id") or (msg.get("id"), name, json.dumps(block.get("input"), sort_keys=True))
                if tid in seen:             # forked sessions repeat earlier messages
                    continue
                seen.add(tid)
                out["toolCalls"] += 1
                if name.startswith(BROKER_SERVERS):
                    tool = name.split("__", 2)[-1]
                    if tool in ORDER_TOOLS or tool.startswith(ORDER_PREFIXES):
                        out["orderCalls"] += 1
                    elif tool in PREVIEW_TOOLS:
                        out["previewCalls"] += 1
                        previews.append(obj.get("timestamp", ""))
                m = NOTES_RE.search(json.dumps(block.get("input")))
                if m and label is None:
                    label = m.groups()
        if is_logger and label:
            day, hhmm = label
            u = usage.values()
            out["loggerRuns"].append({
                "label": f"{_short(date.fromisoformat(day))} {_slot(hhmm)}", "day": day, "hhmm": hhmm,
                "output": sum(x.get("output_tokens", 0) for x in u),
                "reread": sum(x.get("cache_read_input_tokens", 0) for x in u),
                "write": sum(x.get("cache_creation_input_tokens", 0) + x.get("input_tokens", 0) for x in u)})
    out["loggerRuns"].sort(key=lambda r: (r["day"], r["hhmm"]))
    if previews:
        first = datetime.fromisoformat(min(p for p in previews if p).replace("Z", "+00:00")).astimezone(ET)
        out["previewWhen"] = f"{_short(first.date())}, {_clock(f'{first:%H%M}')} ET"
    return out


def transcript_folder(root: Path) -> Path:
    return Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(Path(root).resolve()))


# --- settings, freshness, events, money ---------------------------------------------

def blocked_tools(root: Path) -> dict:
    try:
        deny = set(json.loads((Path(root) / ".claude" / "settings.json").read_text())["permissions"]["deny"])
    except (OSError, ValueError, KeyError):
        deny = set()
    covers = lambda tools: all(s + t in deny for s in BROKER_SERVERS for t in tools)
    return {"orders": covers(ORDER_TOOLS), "previews": covers(PREVIEW_TOOLS)}


def freshness(last: date, today: date) -> dict:
    expected = calendar.previous_trading_day(today)
    missing = [d.isoformat() for d in calendar.trading_days(last + timedelta(days=1), expected)] if last < expected else []
    return {"last": last.isoformat(), "behindDays": len(missing), "missing": missing}


def upcoming(events: dict, today: date, days: int = 60) -> tuple[list[dict], str]:
    up = [{"day": f"{d:%a} {_short(d)}", "what": " + ".join(EVENT_NAMES[e] for e in labels), "skip": True}
          for d, labels in sorted(events.items()) if today <= d <= today + timedelta(days=days)]
    nm = date(today.year + today.month // 12, today.month % 12 + 1, 1)
    have = {e for d, labels in events.items() if (d.year, d.month) == (nm.year, nm.month) for e in labels}
    gaps = [n for e, n in (("cpi", "CPI"), ("jobs", "jobs-report")) if e not in have]
    note = (f"{nm:%B} {' and '.join(gaps)} dates are not in the events file yet." if gaps else "")
    return up, note


def result_per_contract(credit: float | None, value: float | None, case: str) -> float | None:
    if credit is None or value is None:
        return None
    return round((credit - value - pricetest.cost_per_share(case)) * 100, 2)


# --- price test, real credits, shadow trade -------------------------------------------

def price_test(root: Path) -> dict:
    """The slow part: history, sweeps for train and validation, skip-rule scoreboard."""
    spy, vix, intraday, problems = report._load(root)
    events = calendar.event_days()
    inputs = []
    for day in calendar.trading_days(config.HISTORY_START, max(spy)):
        if calendar.has_0dte(day) and (pricetest.in_period(day, "train") or pricetest.in_period(day, "validation")):
            inp = pricetest.build_inputs(day, spy, vix, intraday, events)
            if inp:
                inputs.append(inp)
    sweeps = {p: dict(pricetest.run_sweep(inputs, p)) for p in ("train", "validation")}
    board = {}
    probe = Setup(5, 1.0, "baseline")
    for p in ("train", "validation"):
        days = [i for i in inputs if pricetest.in_period(i.day, p)]
        val = {i.day: pricetest.score_day(i, probe).value for i in days}
        avg = lambda ds: _r(sum(val[d] for d in ds) / len(ds)) if ds else None
        rules = [("Fed day", [i.day for i in days if "fomc" in i.events]),
                 ("Trend unclear", [i.day for i in days if pricetest.trend(i) == "unclear"]),
                 ("Jobs day", [i.day for i in days if "jobs" in i.events]),
                 ("CPI day", [i.day for i in days if "cpi" in i.events]),
                 ("Gap-down open", [i.day for i in days if "gap down" in pricetest._skips(i)])]
        board[p] = {"all": avg(list(val)), "rules": [[n, len(ds), avg(ds)] for n, ds in rules]}
    return {"spy": spy, "vix": vix, "intraday": intraday, "problems": problems, "events": events,
            "inputs": inputs, "sweeps": sweeps, "board": board}


def _real_rows(root: Path, day: date, pt: dict) -> tuple[dict, bool]:
    """Real rows for one logged day. 'fresh' is False when history lacks the day before."""
    spy = pt["spy"]
    snaps = {run: ingest.load_snapshot(root, day, run) for run in report.LOG_RUNS}
    before = [d for d in sorted(spy) if d < day][-config.TREND_LOOKBACK:]
    fresh = len(before) == config.TREND_LOOKBACK and before[-1] == calendar.previous_trading_day(day)
    if snaps["1015"] is None or not before:
        return {}, fresh
    earlier = tuple(spy[d].close for d in before)
    open_price = spy[day].open if day in spy else snaps["1015"].spy
    variants = pricetest.VARIANTS if fresh else ("baseline",)
    rows = {s: compare.real_row(day, s, snaps, earlier, earlier[-1], open_price,
                                events=tuple(pt["events"].get(day, ())))
            for s in pricetest.all_setups() if s.variant in variants}
    return rows, fresh


def _summary(s) -> dict:
    return {"be": _r(s.breakeven.get("cautious")), "best": _r(s.breakeven.get("best")), "loss": _r(s.loss_rate),
            "full": _r(s.full_loss_rate), "n": s.n_traded, "skip": s.n_skipped, "streak": s.worst_streak}


def trading_panels(root: Path, pt: dict, manual: dict, today: date | None = None) -> dict:
    sweeps, val = pt["sweeps"], pt["sweeps"]["validation"]
    width, k = manual.get("shadow", {}).get("width", 5), manual.get("shadow", {}).get("k", 1.0)
    logged = sorted(date.fromisoformat(p.name) for p in (Path(root) / "data" / "snapshots").glob("*")
                    if (p / "1015.json").exists())
    if today is not None:                           # never show days after the "as of" date
        logged = [d for d in logged if d <= today]
    per_day = {d: _real_rows(root, d, pt) for d in logged}

    points, credits, gaps_in, gaps_out = [], [], {}, {}
    for d, (rows, fresh) in per_day.items():
        setup = Setup(width, k, "v2" if fresh else "baseline")
        r = rows.get(setup)
        if r is None or r.status != "ok":
            continue
        need = val[setup].by_band.get(r.vix_band, (0, None))[1]
        vs = f"{'plan v2' if fresh else 'sell-every-day'}, k {k}, ${width}"
        if need is not None:
            points.append({"day": _short(d), "band": r.vix_band, "margin": _r(r.mid_credit - need), "vs": vs})
        credits.append({"day": d.isoformat(), "k": k, "mid": _r(r.mid_credit, 2)})
        snaps = {run: ingest.load_snapshot(root, d, run) for run in ("1015", "1530")}
        for row in rows.values():
            if row.status != "ok":
                continue
            for strike in (row.short, row.long):
                for run, store in (("1015", gaps_in), ("1530", gaps_out)):
                    leg = snaps[run].legs.get((row.side, strike)) if snaps[run] else None
                    if leg is not None:
                        store[(d, row.side, strike)] = leg.ask - leg.bid
    avg = lambda xs: _r(sum(xs) / len(xs), 4) if xs else None

    shadow, explorer_real, move, spy_px, vix_px, xday = None, {}, None, None, None, None
    if logged:
        d = logged[-1]
        rows, fresh = per_day[d]
        events = pt["events"].get(d, [])
        morning = ingest.load_snapshot(root, d, "1015")
        r = rows.get(Setup(width, k, "v2" if fresh else "baseline"))
        checks = [{"rule": "Fed / CPI / jobs day", "hit": bool(events),
                   "note": ", ".join(EVENT_NAMES[e] for e in events) or None}]
        if fresh and r is not None:
            checks += [{"rule": "Gap-down open", "hit": "gap down" in r.skipped, "note": None},
                       {"rule": "Trend unclear", "hit": "trend unclear" in r.skipped, "note": None}]
        else:
            why = f"not checked: {_short(calendar.previous_trading_day(d))} close missing"
            checks += [{"rule": "Gap-down open", "hit": None, "note": why},
                       {"rule": "Trend unclear", "hit": None, "note": why}]
        if r is not None and r.status in ("ok", "skipped"):
            exit_snap = ingest.load_snapshot(root, d, "1530") or ingest.load_snapshot(root, d, "1540")
            value = r.value_1530 if r.value_1530 is not None else r.value_1540
            shadow = {"day": _short(d), "spread": f"{r.side.title()} {r.short}/{r.long}", "width": width, "k": k,
                      "status": r.status, "skipped": list(r.skipped),
                      "rules": "Plan v2" if fresh else
                               f"Sell every day (plan v2 trend rule needs the {_short(calendar.previous_trading_day(d))} close, missing)",
                      "skipChecks": checks, "delta": _r(abs(r.short_delta), 2) if r.short_delta is not None else None,
                      "entry": {"spy": morning.spy, "vix": morning.vix, "mid": _r(r.mid_credit, 2),
                                "natural": _r(r.natural_credit, 2)},
                      "exit": {"spy": exit_snap.spy if exit_snap else None, "value": _r(value, 2)},
                      "resultCautious": result_per_contract(r.mid_credit, value, "cautious"),
                      "resultBest": result_per_contract(r.mid_credit, value, "best")}
        for s, row in rows.items():
            if s.variant == "baseline":
                explorer_real[f"{s.width}|{s.k}"] = {"short": row.short, "long": row.long,
                                                     "mid": _r(row.mid_credit, 2),
                                                     "delta": _r(abs(row.short_delta), 2) if row.short_delta is not None else None}
        before = [x for x in sorted(pt["spy"]) if x < d][-config.TREND_LOOKBACK:]
        inp = pricetest.DayInputs(d, morning.spy, morning.spy, morning.spy, morning.spy, (), morning.vix,
                                  calendar.remaining_fraction(d, config.ENTRY_TIME), (), True)
        move, spy_px, vix_px, xday = _r(pricetest.expected_move(inp), 2), morning.spy, morning.vix, _short(d)

    return {
        "usableDays": len(points),
        "breakeven": [{"k": kk, "v2": _r(val[Setup(5, kk, "v2")].breakeven.get("cautious")),
                       "base": _r(val[Setup(5, kk, "baseline")].breakeven.get("cautious"))} for kk in report.TABLE_KS],
        "realCredits": credits,
        "evidence": {"targetDays": manual.get("evidenceTargetDays", 60), "points": points},
        "slippage": {"legGap1015": avg(list(gaps_in.values())), "legs1015": len(gaps_in),
                     "legGap1530": avg(list(gaps_out.values())), "legs1530": len(gaps_out),
                     "assumedIn": config.SLIPPAGE["cautious"][0], "assumedOut": config.SLIPPAGE["cautious"][1],
                     "bestIn": config.SLIPPAGE["best"][0], "bestOut": config.SLIPPAGE["best"][1]},
        "skipBoard": pt["board"],
        "shadow": shadow,
        "explorer": {"rows": {f"{s.variant}|{s.width}|{s.k}": {p: _summary(sweeps[p][s]) for p in sweeps}
                              for s in pricetest.all_setups()},
                     "real": explorer_real, "move": move, "spy": spy_px, "vix": vix_px, "day": xday},
    }


# --- profitability (would-be trades priced with real logged quotes; no orders) ------------

def profit_days(root: Path, pt: dict, manual: dict, today: date, n: int = 10) -> list[dict]:
    """One entry per trading day from the first 10:15 log to today (last n days).

    state: done (entry and exit priced) | no exit | no entry | no runs | sat out (rules skipped the day)
    """
    root = Path(root)
    width, k = manual.get("shadow", {}).get("width", 5), manual.get("shadow", {}).get("k", 1.0)
    snap_root = root / "data" / "snapshots"
    firsts = [date.fromisoformat(p.name) for p in snap_root.glob("*") if (p / "1015.json").exists()]
    if not firsts:
        return []
    val = pt["sweeps"]["validation"]
    out = []
    for d in calendar.trading_days(min(firsts), today)[-n:]:
        folder = snap_root / d.isoformat()
        rows, fresh = _real_rows(root, d, pt)
        setup = Setup(width, k, "v2" if fresh else "baseline")
        r = rows.get(setup)
        e = {"day": _short(d), "date": d.isoformat(), "state": "no runs", "credit": None, "value": None,
             "need": None, "result": None, "best": None, "spread": None, "band": None,
             "rules": "plan v2" if fresh else "sell every day", "skipped": []}
        if r is None or r.status in ("no 10:15 run", "not logged"):
            if folder.exists() and any(folder.glob("*.json")):
                e["state"] = "no entry"
            out.append(e)
            continue
        e.update(spread=f"{r.side.title()} {r.short}/{r.long}", band=r.vix_band,
                 need=_r(val[setup].by_band.get(r.vix_band, (0, None))[1]))
        if r.status == "skipped":
            e.update(state="sat out", skipped=list(r.skipped))
        else:
            value = r.value_1530 if r.value_1530 is not None else r.value_1540
            e.update(credit=_r(r.mid_credit, 2), value=_r(value, 2))
            if value is None:
                e["state"] = "no exit"
            else:
                e.update(state="done", result=result_per_contract(r.mid_credit, value, "cautious"),
                         best=result_per_contract(r.mid_credit, value, "best"))
        out.append(e)
    return out


def profit_summary(days: list[dict], width: int) -> dict:
    done = [d for d in days if d["state"] == "done"]
    results = [d["result"] for d in done]
    wins = [x for x in results if x > 0]
    with_need = [d for d in done if d["need"] is not None]
    cost = pricetest.cost_per_share("cautious")
    risk = (sum((width - d["credit"] + cost) * 100 for d in done) / len(done)) if done else None
    avg = sum(results) / len(results) if results else None
    credited = [d for d in days if d["state"] in ("done", "no exit") and d["credit"] is not None and d["need"] is not None]
    g_credit = sum(d["credit"] for d in credited) / len(credited) if credited else None
    g_need = sum(d["need"] for d in credited) / len(credited) if credited else None
    return {
        "finished": len(done), "wins": len(wins), "losses": len(results) - len(wins),
        "total": round(sum(results), 2), "totalBest": round(sum(d["best"] for d in done), 2),
        "avg": _r(avg, 2), "worst": _r(min(results), 2) if results else None,
        "expected": _r(sum((d["credit"] - d["need"]) * 100 for d in with_need) / len(with_need), 2) if with_need else None,
        "risk": _r(risk, 2),
        "winsToRepay": round(risk / (sum(wins) / len(wins))) if wins and risk else None,
        "profitOverRisk": _r(avg / risk, 4) if avg is not None and risk else None,
        "gauge": {"days": len(credited), "credit": _r(g_credit, 4), "need": _r(g_need, 4),
                  "margin": _r(g_credit - g_need, 4) if credited else None,
                  "dates": [d["day"] for d in credited]},
    }


def profitability(root: Path, pt: dict, manual: dict, today: date) -> dict:
    width, k = manual.get("shadow", {}).get("width", 5), manual.get("shadow", {}).get("k", 1.0)
    days = profit_days(root, pt, manual, today)
    fresh = bool(days) and all(d["rules"] == "plan v2" for d in days if d["state"] != "no runs")
    variant = "v2" if fresh else "baseline"
    s = pt["sweeps"]["validation"][Setup(width, k, variant)]
    return {**profit_summary(days, width), "days": days, "width": width, "k": k,
            "rules": "Plan v2" if fresh else "Sell every day",
            "historyEnd": _short(max(pt["spy"])), "targetDays": manual.get("evidenceTargetDays", 60),
            "backtest": {"winRate": _r(1 - s.loss_rate, 3) if s.loss_rate is not None else None,
                         "fullLossRate": _r(s.full_loss_rate, 3), "days": s.n_traded,
                         "lossDaysPerYear": round(s.loss_rate * s.n_traded) if s.loss_rate is not None else None,
                         "fullLossesPerYear": round(s.full_loss_rate * s.n_traded) if s.full_loss_rate is not None else None,
                         "needAll": _r(s.breakeven.get("cautious"))}}


# --- git and tests ---------------------------------------------------------------------

def _git(root: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def git_status(root: Path) -> tuple[dict, list[dict]]:
    name = _git(root, "rev-parse", "--abbrev-ref", "HEAD") or "?"
    ahead = int(_git(root, "rev-list", "--count", "main..HEAD") or 0)
    log = _git(root, "log", "-12", "--date=format:%b %d", "--format=%ad|%s")
    activity = [dict(zip(("when", "what"), line.split("|", 1))) for line in log.splitlines() if "|" in line]
    return {"name": name, "ahead": ahead, "merged": ahead == 0}, activity


def run_tests(root: Path) -> dict:
    try:
        out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=root,
                             capture_output=True, text=True, timeout=300).stdout
    except (OSError, subprocess.SubprocessError):
        return {"passed": 0, "failed": 0, "error": True}
    tail = out.strip().splitlines()[-1] if out.strip() else ""
    num = lambda word: int(m.group(1)) if (m := re.search(rf"(\d+) {word}", tail)) else 0
    return {"passed": num("passed"), "failed": num("failed") + num("error")}


# --- the whole status ----------------------------------------------------------------

def load_manual(root: Path) -> dict:
    path = Path(root) / "dashboard" / "manual.json"
    return json.loads(path.read_text()) if path.exists() else {}


def collect(root: Path, now: datetime, tests: dict, transcripts: Path | None = None, pt: dict | None = None) -> dict:
    root = Path(root)
    now = now.astimezone(ET)
    today = now.date()
    manual = load_manual(root)
    pt = pt or price_test(root)
    tp = trading_panels(root, pt, manual, today)
    runs = logger_runs(root)
    scheduled = manual.get("scheduled", [])
    nxt = next_run(scheduled, now)
    audit = scan_transcripts(transcripts if transcripts is not None else transcript_folder(root))
    blocked = blocked_tools(root)
    fresh = freshness(max(pt["spy"]), today)
    branch, activity = git_status(root)
    up, up_note = upcoming(pt["events"], today)
    grid = calendar_grid(runs, scheduled, now)
    vix_out = sum(p.startswith("VIX") for p in pt["problems"])

    alerts = []
    if tests.get("failed"):
        alerts.append({"level": "red", "text": f"{tests['failed']} automated tests are failing."})
    if audit["orderCalls"]:
        alerts.append({"level": "red", "text": f"{audit['orderCalls']} order-tool calls found in run records. Check now."})
    if not blocked["orders"] or not blocked["previews"]:
        alerts.append({"level": "red", "text": "Project settings do not block every order or order-preview tool."})
    for day, row in grid.items():
        for slot, state in row.items():
            if state in ("bad", "missed"):
                alerts.append({"level": "red", "text": f"Logger run {day} {slot} {'failed the check' if state == 'bad' else 'never ran'}."})
    if fresh["behindDays"]:
        alerts.append({"level": "amber", "text": f"Price history is {fresh['behindDays']} trading day(s) behind "
                       f"(last day {fresh['last']}; missing {', '.join(fresh['missing'])}). Plan v2's trend and gap-down rules can't be checked for the latest days."})

    latest = max((r["day"] for r in runs), default=None)
    eod_lines = []
    if latest:
        day_runs = [r for r in runs if r["day"] == latest]
        n_ok = sum(r["result"] == "ok" for r in day_runs)
        eod_lines.append(f"{len(day_runs)} logger run(s), {n_ok} passed the check.")
    sh = tp["shadow"]
    if sh and sh.get("resultCautious") is not None:
        eod_lines.append(f"Would-be trade: {sh['spread']}, {'+' if sh['resultCautious'] >= 0 else '-'}${abs(sh['resultCautious']):.2f} after cautious costs.")
    if fresh["behindDays"]:
        eod_lines.append(f"Watch: price history {fresh['behindDays']} day(s) behind.")

    costs = [r for r in audit["loggerRuns"]]
    return {
        "asOf": f"{now:%a} {_short(today)}, {now.year} · {_clock(f'{now:%H%M}')} ET",
        "stages": manual.get("stages", []),
        "safety": [
            {"label": "Orders placed by the bot", "value": str(audit["orderCalls"]), "ok": audit["orderCalls"] == 0,
             "detail": f"Counted in {audit['transcripts']} Claude run records for this project."},
            {"label": "Order tools blocked", "value": "Yes" if blocked["orders"] else "NO", "ok": blocked["orders"],
             "detail": "Deny rules in project settings + guard test"},
            {"label": "Order-preview tools blocked", "value": "Yes" if blocked["previews"] else "NO", "ok": blocked["previews"],
             "detail": "Previews cannot trade, but the plan forbids them"},
            {"label": "Account in use", "value": manual.get("account", "–"), "ok": True, "detail": "Read-only tools only"},
            {"label": "Robinhood 'approve trades'", "value": manual.get("approveTrades", "–"), "ok": False,
             "detail": "Any order tool would execute for real, which is why order tools stay blocked (set by hand; the dashboard does not ask Robinhood)"}],
        "tests": tests,
        "branch": branch,
        "logger": {"daily": manual.get("daily", ""), "next": nxt, "usableDays": tp["usableDays"],
                   "runs": runs, "schedule": [_slot(s) for s in SLOTS]},
        "history": {"spyBars": len(pt["spy"]), "from": min(pt["spy"]).isoformat(), "to": max(pt["spy"]).isoformat(),
                    "intradayFrom": min(pt["intraday"]).isoformat() if pt["intraday"] else None,
                    "vixExcluded": vix_out},
        "breakeven": tp["breakeven"], "realCredits": tp["realCredits"],
        "decisions": manual.get("decisions", []), "activity": activity,
        "nextRunISO": nxt["iso"] if nxt else None,
        "alerts": alerts, "calendar": grid,
        "costs": {"budgetPerDay": manual.get("tokenBudgetPerDay", 250000), "runs": costs},
        "freshness": fresh,
        "audit": {**{k: audit[k] for k in ("transcripts", "toolCalls", "orderCalls", "previewCalls", "previewWhen")},
                  "denyRulesCoverPreview": blocked["previews"], "guardTest": "pass" if not tests.get("failed") else "check"},
        "shadow": sh, "evidence": tp["evidence"], "slippage": tp["slippage"], "skipBoard": tp["skipBoard"],
        "upcoming": up, "upcomingNote": up_note,
        "eod": {"day": _short(date.fromisoformat(latest)) if latest else "–", "lines": eod_lines},
        "explorer": tp["explorer"],
        "profit": profitability(root, pt, manual, today),
    }


# --- server ------------------------------------------------------------------------------

class _Cache:
    """Keeps slow parts until their files change; status itself is rebuilt at most once a minute."""

    def __init__(self, root: Path):
        self.root, self.lock = root, threading.Lock()
        self.pt = self.pt_key = self.tests = self.tests_key = self.status = None
        self.status_at = 0.0

    def _stamp(self, *globs: str) -> tuple:
        return tuple(sorted((str(p), p.stat().st_mtime) for g in globs for p in self.root.glob(g)))

    def get(self) -> dict:
        with self.lock:
            if self.status and _time.time() - self.status_at < 60:
                return self.status
            key = self._stamp("data/history/*", "data/cboe/*", "spybot/*.py", "spybot/reference/*")
            if key != self.pt_key:
                self.pt, self.pt_key = price_test(self.root), key
            tkey = self._stamp("spybot/**/*.py", "tests/**/*.py", "spybot/reference/*", ".claude/settings.json")
            if tkey != self.tests_key:
                self.tests, self.tests_key = run_tests(self.root), tkey
            self.status = collect(self.root, datetime.now(ET), self.tests, pt=self.pt)
            self.status_at = _time.time()
            return self.status


STATIC_TYPES = {".ttf": "font/ttf", ".txt": "text/plain; charset=utf-8", ".css": "text/css", ".svg": "image/svg+xml"}


def static_file(root: Path, url_path: str) -> tuple[bytes, str] | None:
    """A file under dashboard/static, or None. Never serves anything outside that folder."""
    base = (Path(root) / "dashboard" / "static").resolve()
    rel = unquote(url_path.split("?")[0])[len("/static/"):]
    target = (base / rel).resolve()
    if base not in target.parents or not target.is_file() or target.suffix not in STATIC_TYPES:
        return None
    return target.read_bytes(), STATIC_TYPES[target.suffix]


def serve(root: Path, port: int = 8790) -> None:
    root = Path(root)
    page = root / "dashboard" / "index.html"
    cache = _Cache(root)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/", "/index.html"):
                body, kind = page.read_bytes(), "text/html; charset=utf-8"
            elif self.path.split("?")[0] == "/api/status":
                try:
                    body, kind = json.dumps(cache.get()).encode(), "application/json"
                except Exception as e:      # show the problem on the page instead of a blank screen
                    body, kind = json.dumps({"error": f"{type(e).__name__}: {e}"}).encode(), "application/json"
            elif self.path.startswith("/static/") and (found := static_file(root, self.path)):
                body, kind = found
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Dashboard: http://127.0.0.1:{port}  (read-only; Ctrl+C to stop)", flush=True)
    threading.Thread(target=cache.get, daemon=True).start()     # warm up
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
