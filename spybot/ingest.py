"""Check raw logger files written by the Claude session and save clean snapshots.

A file with any problem is never fixed: it is marked bad, with its reasons.
"""
from __future__ import annotations

from typing import Optional

import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from spybot import config

LABEL_TOLERANCE_MIN = 5          # a run more than 5 minutes from its label is not that run
ET = ZoneInfo(config.MARKET_TZ)

GREEK_FIELDS = ("implied_volatility", "delta")
LEG_FIELDS = ("bid_price", "ask_price", "bid_size", "ask_size", "mark_price",
              "implied_volatility", "delta", "open_interest", "volume", "updated_at")


@dataclass(frozen=True)
class Leg:
    bid: float
    ask: float
    bid_size: int
    ask_size: int
    mark: float
    iv: Optional[float]       # None only for in-the-money legs (Robinhood leaves greeks empty)
    delta: Optional[float]
    open_interest: int
    volume: int
    updated_at: datetime


@dataclass(frozen=True)
class Snapshot:
    day: date
    run: time
    spy: float
    vix: float
    legs: dict[tuple[str, int], Leg]
    dropped: tuple[str, ...] = ()   # "put:703 stale quote (...)": left out, so the strike reads "not logged"


def _opt_float(v):
    return None if v in (None, "") else float(v)


def parse_ts(text: str) -> datetime:
    """ISO timestamp with 'Z' or offset and up to 9 fraction digits (Python 3.9 safe)."""
    text = text.replace("Z", "+00:00")
    text = re.sub(r"\.(\d{6})\d+", r".\1", text)
    return datetime.fromisoformat(text)


def quote_time(raw: dict) -> datetime | None:
    """When the quotes were taken, from Robinhood's own SPY and VIX stamps (the newest one).

    The session's hand-noted run_et can be a minute early (it is written before the long quote
    request), so these machine stamps are used whenever they are present."""
    stamps = []
    try:
        q = raw["spy"]["data"]["results"][0]["quote"]
        stamps += [q.get(k) for k in ("venue_last_trade_time", "venue_bid_time", "venue_ask_time")]
    except (KeyError, IndexError, TypeError):
        pass
    try:
        stamps.append(raw["vix"]["data"]["quotes"][0].get("updated_at"))
    except (KeyError, IndexError, TypeError):
        pass
    times = []
    for s in stamps:
        if s:
            try:
                times.append(parse_ts(s))
            except ValueError:
                pass
    return max(times) if times else None


def parse(raw: dict) -> tuple[Snapshot | None, list[str]]:
    problems: list[str] = []
    stale: list[tuple[tuple[str, int], str]] = []
    try:
        run_at = (quote_time(raw) or parse_ts(raw["run_et"])).astimezone(ET)
        day = run_at.date()
        if raw["expiry"] != day.isoformat():
            problems.append(f"expiry {raw['expiry']} is not the run day {day}")
        spy = float(raw["spy"]["data"]["results"][0]["quote"]["last_trade_price"])
        vix = float(raw["vix"]["data"]["quotes"][0]["value"])
        instruments = raw["instruments"]
        quotes = [r["quote"] for block in raw["quotes"] for r in block["data"]["results"]]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        return None, [f"missing or unreadable top-level field: {exc!r}"]

    legs: dict[tuple[str, int], Leg] = {}
    for q in quotes:
        iid = q.get("instrument_id")
        inst = instruments.get(iid)
        if inst is None:
            problems.append(f"unknown instrument {iid}")
            continue
        if inst.get("expiry") != day.isoformat():
            problems.append(f"{iid}: instrument expiry {inst.get('expiry')} is not {day}")
        missing = [f for f in LEG_FIELDS if q.get(f) in (None, "")]
        in_the_money = (float(inst["strike"]) > spy) if inst.get("type") == "put" else (float(inst["strike"]) < spy)
        if in_the_money:
            missing = [f for f in missing if f not in GREEK_FIELDS]
        if missing:
            problems.append(f"{iid}: missing {', '.join(missing)}")
            continue
        leg = Leg(float(q["bid_price"]), float(q["ask_price"]), int(q["bid_size"]), int(q["ask_size"]),
                  float(q["mark_price"]), _opt_float(q.get("implied_volatility")), _opt_float(q.get("delta")),
                  int(q["open_interest"]), int(q["volume"]), parse_ts(q["updated_at"]))
        strike = float(inst["strike"])
        if q.get("break_even_price") not in (None, ""):
            # Robinhood: break-even = strike -/+ adjusted_mark_price (older files: ask)
            be = float(q["break_even_price"])
            price = float(q["adjusted_mark_price"]) if q.get("adjusted_mark_price") not in (None, "") else leg.ask
            implied = be + price if inst["type"] == "put" else be - price
            if abs(implied - strike) > 0.011:
                problems.append(f"{iid}: labelled strike {strike} but break-even implies {implied:.2f}")
        if leg.bid > leg.ask:
            problems.append(f"{iid}: bid > ask ({leg.bid} > {leg.ask})")
        age = abs((leg.updated_at - run_at).total_seconds())
        key = (inst["type"], int(round(float(inst["strike"]))))
        if age > config.STALE_QUOTE_SEC:
            stale.append((key, f"{iid}: stale quote ({age:.0f}s from run time)"))
            continue
        legs[key] = leg
    # A single old quote is usually a far-away $0/$0.01 offer that has not changed (Robinhood stamps the
    # last bid/ask change), so that contract is left out. Many old quotes mean the batch itself is bad.
    if stale and len(stale) > config.STALE_DROP_MAX_SHARE * len(quotes):
        problems += [msg for _, msg in stale]
    if problems:
        return None, problems
    dropped = tuple(f"{t}:{k} {msg}" for (t, k), msg in stale)
    return Snapshot(day, run_at.time().replace(tzinfo=None), spy, vix, legs, dropped), []


def _snap_dir(root: Path, day: date) -> Path:
    return Path(root) / "data" / "snapshots" / day.isoformat()


def _to_json(snap: Snapshot) -> dict:
    return {"day": snap.day.isoformat(), "run": snap.run.isoformat(), "spy": snap.spy, "vix": snap.vix,
            "legs": {f"{t}:{k}": {**asdict(leg), "updated_at": leg.updated_at.isoformat()}
                     for (t, k), leg in snap.legs.items()},
            "dropped": list(snap.dropped)}


def _from_json(d: dict) -> Snapshot:
    legs = {}
    for key, v in d["legs"].items():
        t, k = key.split(":")
        legs[(t, int(k))] = Leg(**{**v, "updated_at": datetime.fromisoformat(v["updated_at"])})
    return Snapshot(date.fromisoformat(d["day"]), time.fromisoformat(d["run"]), d["spy"], d["vix"], legs,
                    tuple(d.get("dropped", ())))


def ingest(root: Path, day: date, hhmm: str) -> list[str]:
    raw_path = Path(root) / "data" / "raw" / day.isoformat() / f"{hhmm}.json"
    out = _snap_dir(root, day)
    out.mkdir(parents=True, exist_ok=True)
    if not raw_path.exists():
        problems = [f"missing raw file {raw_path}"]
        snap = None
    else:
        snap, problems = parse(json.loads(raw_path.read_text()))
        if snap is not None and snap.day != day:
            snap, problems = None, [f"file is for {snap.day}, not {day}"]
        elif snap is not None:
            label = datetime.combine(day, time(int(hhmm[:2]), int(hhmm[2:])))
            gap = abs((datetime.combine(day, snap.run) - label).total_seconds()) / 60
            if gap > LABEL_TOLERANCE_MIN:
                snap, problems = None, [f"run time {snap.run} is {gap:.0f} min from its label {hhmm}"]
    good, bad = out / f"{hhmm}.json", out / f"{hhmm}.bad.json"
    if snap is None:                                # the latest check is the record
        good.unlink(missing_ok=True)
        bad.write_text(json.dumps({"problems": problems}, indent=1))
        return problems
    bad.unlink(missing_ok=True)
    good.write_text(json.dumps(_to_json(snap), indent=1))
    return []


def load_snapshot(root: Path, day: date, hhmm: str) -> Snapshot | None:
    path = _snap_dir(root, day) / f"{hhmm}.json"
    if not path.exists():
        return None
    return _from_json(json.loads(path.read_text()))


def _load_tool_result(path: Path):
    """A tool answer saved to a file: plain JSON, or a list of text blocks holding JSON."""
    data = json.loads(Path(path).read_text())
    if isinstance(data, list) and data and all(isinstance(b, dict) and "text" in b for b in data):
        data = json.loads("".join(b["text"] for b in data))
    return data


def assemble(root: Path, day: date, hhmm: str, quotes_paths) -> list[str]:
    """Build data/raw/DAY/HHMM.json from instruments.json, HHMM.spyvix.json and the
    saved get_option_quotes answer(s) (one path or a list), then ingest it. Returns ingest's problems."""
    folder = Path(root) / "data" / "raw" / day.isoformat()
    try:
        instruments = json.loads((folder / "instruments.json").read_text())
        spyvix = json.loads((folder / f"{hhmm}.spyvix.json").read_text())
        if isinstance(quotes_paths, (str, Path)):
            quotes_paths = [quotes_paths]
        quotes = [_load_tool_result(p) for p in quotes_paths]
        raw = {"run_et": spyvix["run_et"], "expiry": day.isoformat(), "spy": spyvix["spy"],
               "vix": spyvix["vix"], "instruments": instruments, "quotes": quotes}
    except (OSError, ValueError) as e:
        return [f"cannot assemble: {e}"]
    except KeyError as e:
        return [f"cannot assemble: {hhmm}.spyvix.json has no {e}"]
    (folder / f"{hhmm}.json").write_text(json.dumps(raw))
    return ingest(root, day, hhmm)
