"""Plain-English price-test report (markdown) plus a CSV of every setup."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from spybot import calendar, compare, config, history, ingest, pricetest
from spybot.pricetest import Setup

LIMITS = (
    "**What this test can and cannot show.** Past days use the day's open and close in place of the "
    "real 10:15 and 3:30 prices, except where intraday prices exist. Option credits for past days are "
    "unknown, so the test gives the credit each setup would have *needed*; real credits come only from "
    "the bot's own logs. Credits are larger on volatile days, when losses also happen, and this test "
    "captures that only through VIX bands. Any time value left at 3:30 is ignored, which flatters wins "
    "slightly. The VIX9D skip rule is not tested (no data). This test can rule a setup out; it cannot "
    "prove one works."
)
VARIANT_LABELS = {
    "baseline": "Baseline (put spread every day, no skips)",
    "put_skips": "Put only, with skip rules",
    "v2": "Plan v2 rules (trend + skips)",
}
TABLE_KS = tuple(round(0.6 + 0.2 * i, 1) for i in range(8))   # 0.6, 0.8, ... 2.0
LOG_RUNS = ("1015", "1530", "1540")


def _money(x: float | None) -> str:
    return "–" if x is None else f"${x:.2f}"


def _pct(x: float | None) -> str:
    return "–" if x is None else f"{x:.1%}"


def _load(root: Path):
    hist = Path(root) / "data" / "history"
    spy, p1 = history.load_daily(sorted(hist.glob("spy_day_*.json")))
    vix, p2 = history.load_daily(sorted(hist.glob("vix_day_*.json")))
    intraday, p3 = history.load_intraday(sorted(hist.glob("spy_5min_*.json")))
    bad = json.loads((calendar.REFERENCE / "bad_bars.json").read_text())
    p4 = []
    for symbol, bars in (("SPY", spy), ("VIX", vix)):
        for text, why in bad[symbol].items():
            if bars.pop(date.fromisoformat(text), None) is not None:
                p4.append(f"{symbol} {text}: known bad bar excluded ({why})")
    cboe_file = Path(root) / "data" / "cboe" / "VIX_History.csv"
    if cboe_file.exists():
        cboe = history.load_cboe(cboe_file)
        for day in history.cboe_mismatches(vix, cboe):
            bar = vix.pop(day)
            o, c = cboe[day]
            p4.append(f"VIX {day}: differs from Cboe (Robinhood {bar.open}/{bar.close}, Cboe {o}/{c}); excluded")
    return spy, vix, intraday, p1 + p2 + p3 + p4


def check_history(root: Path) -> list[str]:
    spy, vix, _, problems = _load(root)
    if not spy:
        return problems + ["no SPY daily history found"]
    end = max(spy)
    problems += ["SPY " + p for p in history.check_daily(spy, config.HISTORY_START, end)]
    problems += ["VIX " + p for p in history.check_daily(vix, config.HISTORY_START, end)]
    return problems


def _logged_rows(root: Path, spy, events, today: date):
    """Real rows for every logged day, plus the days that could not be used and why."""
    snap_root = Path(root) / "data" / "snapshots"
    rows: list[compare.RealRow] = []
    used: list[date] = []
    no_1015: list[date] = []
    stale: list[date] = []
    n_bad = 0
    dirs = sorted(p for p in snap_root.iterdir() if p.is_dir()) if snap_root.exists() else []
    if not dirs:
        return rows, used, no_1015, stale, 0
    logged = {date.fromisoformat(p.name): p for p in dirs}
    first = min(logged)
    for day in calendar.trading_days(first, max(max(logged), today - timedelta(days=1))):
        if not calendar.has_0dte(day):
            continue
        folder = logged.get(day)
        if folder is not None:
            n_bad += len(list(folder.glob("*.bad.json")))
        snaps = {run: ingest.load_snapshot(root, day, run) for run in LOG_RUNS}
        before = [d for d in sorted(spy) if d < day][-config.TREND_LOOKBACK:]
        if len(before) < config.TREND_LOOKBACK or before[-1] != calendar.previous_trading_day(day):
            stale.append(day)
            continue
        morning = snaps["1015"]
        if morning is None:
            no_1015.append(day)
            continue
        used.append(day)
        earlier = tuple(spy[d].close for d in before)
        open_price = spy[day].open if day in spy else morning.spy
        for setup in pricetest.all_setups():
            rows.append(compare.real_row(day, setup, snaps, earlier, earlier[-1], open_price,
                                         events=tuple(events.get(day, ()))))
    return rows, used, no_1015, stale, n_bad


def _dates(days: list[date]) -> str:
    shown = ", ".join(map(str, days[:30]))
    return shown + (f" and {len(days) - 30} more" if len(days) > 30 else "")


def _avg(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def build_report(root: Path, today: date, final: bool = False) -> tuple[str, list[dict]]:
    spy, vix, intraday, load_problems = _load(root)
    events = calendar.event_days()
    periods = ["train", "validation"] + (["test"] if final else [])
    ref_period = "test" if final else "validation"
    last = max(spy) if spy else today

    inputs, missing = [], []
    for day in calendar.trading_days(config.HISTORY_START, last):
        if not calendar.has_0dte(day) or not any(pricetest.in_period(day, p) for p in periods):
            continue
        inp = pricetest.build_inputs(day, spy, vix, intraday, events)
        (inputs.append(inp) if inp else missing.append(day))

    sweeps = {p: dict(pricetest.run_sweep(inputs, p, allow_sealed=final)) for p in periods}
    logged, used_days, no_1015, stale_days, n_bad = _logged_rows(root, spy, events, today)
    n_logged_days = len(used_days)
    by_setup: dict[Setup, list[compare.RealRow]] = {}
    for r in logged:
        by_setup.setdefault(r.setup, []).append(r)

    rows: list[dict] = []
    for p in periods:
        for setup, s in sweeps[p].items():
            rows.append({"period": p, "variant": setup.variant, "width": setup.width, "k": setup.k,
                         "n_traded": s.n_traded, "n_skipped": s.n_skipped, "loss_rate": s.loss_rate,
                         "full_loss_rate": s.full_loss_rate, "worst_streak": s.worst_streak,
                         "avg_exit_value": s.avg_value, "breakeven_best": s.breakeven.get("best"),
                         "breakeven_cautious": s.breakeven.get("cautious")})
    for setup in pricetest.all_setups():
        ok = [r for r in by_setup.get(setup, []) if r.status == "ok"]
        if by_setup.get(setup):
            rows.append({"period": "logged", "variant": setup.variant, "width": setup.width, "k": setup.k,
                         "n_ok": len(ok), "avg_mid_credit": _avg(r.mid_credit for r in ok),
                         "avg_natural_credit": _avg(r.natural_credit for r in ok),
                         "avg_abs_delta": _avg(abs(r.short_delta) for r in ok if r.short_delta is not None)})

    out = [LIMITS, "", f"# Price test report, {today.isoformat()}", ""]

    # Coverage
    out += ["## Data coverage", ""]
    for p in periods:
        start, end = config.PERIODS[p]
        end = min(end or last, last)
        n = sum(pricetest.in_period(i.day, p) for i in inputs)
        miss = [d for d in missing if pricetest.in_period(d, p)]
        out.append(f"- **{p}** ({start} to {end}): {n} days scored, {len(miss)} days missing"
                   + (f" ({', '.join(map(str, miss[:30]))}{f' and {len(miss) - 30} more' if len(miss) > 30 else ''})" if miss else ""))
    if load_problems:
        out.append(f"- {len(load_problems)} data problems while loading (run `python -m spybot check-history`).")
    out.append(f"- {n_logged_days} usable logged days so far, {n_bad} bad logger runs.")
    if no_1015:
        out.append(f"- Days with no usable 10:15 run (left out of the credit comparison): {_dates(no_1015)}.")
    if stale_days:
        out.append(f"- Logged days after the end of the price history (history not up to date; "
                   f"download fresh SPY and VIX daily bars): {_dates(stale_days)}.")
    out.append("")

    # Stand-in error (aggregate only, no dates)
    gaps_in, gaps_out, moves_in, moves_out = [], [], [], []
    for day, prices in intraday.items():
        inp = pricetest.build_inputs(day, spy, vix, intraday, events) if day in spy else None
        if inp is None or not inp.real_times:
            continue
        bar, move = spy[day], pricetest.expected_move(inp)
        gaps_in.append(abs(bar.open - inp.entry))
        gaps_out.append(abs(bar.close - inp.exit))
        moves_in.append(abs(bar.open - inp.entry) / move)
        moves_out.append(abs(bar.close - inp.exit) / move)
    out += ["## How good are the open/close stand-ins?", ""]
    if gaps_in:
        out.append(f"Over {len(gaps_in)} recent days with real intraday prices: the open differed from the "
                   f"10:15 price by {_money(_avg(gaps_in))} on average ({_avg(moves_in):.2f} expected moves); "
                   f"the close differed from the 3:30 price by {_money(_avg(gaps_out))} "
                   f"({_avg(moves_out):.2f} expected moves).")
    else:
        out.append("No days with real intraday prices yet.")
    out.append("")

    # Per variant and width
    for variant in pricetest.VARIANTS:
        for width in config.WIDTHS:
            out += [f"## {VARIANT_LABELS[variant]}, ${width} wide", ""]
            out.append(f"| k | train break-even (cautious) | {ref_period}: days traded / skipped | loss days | "
                       f"full-loss days | worst losing streak | break-even best | break-even cautious | "
                       f"logged days | avg real credit | avg real delta |")
            out.append("|" + "---|" * 11)
            verdicts = []
            for k in TABLE_KS:
                setup = Setup(width, k, variant)
                tr, s = sweeps["train"][setup], sweeps[ref_period][setup]
                ok = [r for r in by_setup.get(setup, []) if r.status == "ok"]
                mid, delta = _avg(r.mid_credit for r in ok), _avg(abs(r.short_delta) for r in ok if r.short_delta is not None)
                out.append(f"| {k} | {_money(tr.breakeven.get('cautious'))} | {s.n_traded} / {s.n_skipped} | "
                           f"{_pct(s.loss_rate)} | {_pct(s.full_loss_rate)} | {s.worst_streak} | "
                           f"{_money(s.breakeven.get('best'))} | {_money(s.breakeven.get('cautious'))} | "
                           f"{len(ok)} | {_money(mid)} | {'–' if delta is None else f'{delta:.2f}'} |")
                need = s.breakeven.get("cautious")
                if need is None:
                    verdicts.append(f"- k {k}: no {ref_period} days traded.")
                elif not ok:
                    verdicts.append(f"- k {k}: Needs {_money(need)} a spread after cautious costs; no logged days yet.")
                else:
                    missing_bands = sorted({r.vix_band for r in ok if r.vix_band not in s.by_band})
                    if missing_bands:
                        verdicts.append(f"- k {k}: real credits were logged at VIX {', '.join(missing_bands)}, "
                                        f"where the {ref_period} period has no traded days; no verdict.")
                    else:
                        matched = _avg(s.by_band[r.vix_band][1] for r in ok)
                        pays = mid > matched
                        verdicts.append(f"- k {k}: Needs {_money(matched)} a spread after cautious costs "
                                        f"(break-even matched to each logged day's VIX band); real 10:15 credits "
                                        f"averaged {_money(mid)} over {len(ok)} logged days → "
                                        f"{'pays' if pays else 'does not pay'}.")
            out += [""] + verdicts + [""]

    # VIX bands
    bands = ["<15", "15-20", "20-30", "30+"]
    out += [f"## Break-even by VIX band (plan v2 rules, $5 wide, {ref_period}, cautious costs)", "",
            "| k | " + " | ".join(bands) + " |", "|" + "---|" * 5]
    for k in TABLE_KS:
        s = sweeps[ref_period][Setup(5, k, "v2")]
        ok = [r for r in by_setup.get(Setup(5, k, "v2"), []) if r.status == "ok"]
        cells = []
        for b in bands:
            need = f"{_money(s.by_band[b][1])} ({s.by_band[b][0]} days)" if b in s.by_band else "–"
            real = [r.mid_credit for r in ok if r.vix_band == b]
            cells.append(need + (f"; real {_money(_avg(real))} ({len(real)} logged)" if real else ""))
        out.append(f"| {k} | " + " | ".join(cells) + " |")
    out.append("")

    # Real bid/ask gaps
    out += ["## Real bid/ask gaps from the logs", ""]
    ok_all = [r for r in logged if r.status == "ok"]
    if ok_all:
        legs = {}
        for r in ok_all:
            legs[(r.day, r.side, r.short)] = r.leg_gaps[0]
            legs[(r.day, r.side, r.long)] = r.leg_gaps[1]
        vals = list(legs.values())
        v1530 = _avg(r.value_1530 for r in ok_all)
        out.append(f"Per leg: average {_money(sum(vals) / len(vals))}, worst {_money(max(vals))} "
                   f"({len(vals)} legs). Average spread value left at 3:30: {_money(v1530)}.")
    else:
        out.append("No logged days yet.")
    out.append("")
    return "\n".join(out), rows
