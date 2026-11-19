# SPY Credit-Spread Bot, Phase A (Stages 0-1) Implementation Plan

> **Superseded on 2026-11-17 by `2026-11-17-price-test-and-logger-plan.md`.** Tasks 3–8 below were not built.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove what the Robinhood connection can supply, then log SPY option data every few minutes and score naive "shadow" strategies from it. **No orders are ever placed in this phase.**

**Architecture:** Two halves. (1) A *collector*: a Claude session that follows `collector/RUNBOOK.md`, calls the read-only market-data tools, and hands each snapshot to a validating CLI. (2) *Pure Python code* (stdlib + pytest) that reads the saved snapshot files and simulates shadow strategies. All logic is testable offline from fixtures.

**Tech Stack:** Python 3 stdlib (`dataclasses`, `zoneinfo`, `json`, `argparse`, `math`), pytest. **[my call]**, verified in Task 2.

**Spec:** `2026-11-16-spy-credit-spread-bot-design.md` (revision 2), same folder. Executors read both.

## Global Constraints
- Phase A places **no orders**. Robinhood approvals are OFF on the account, so any order tool is live. **Forbidden tools** (the full list, used by the runbook and by the Task 1 guard): every tool whose name starts with `place_` or `cancel_` (`place_option_order`, `place_equity_order`, `place_advanced_order`, `place_crypto_order`, `cancel_option_order`, `cancel_equity_order`, `cancel_advanced_order`, `cancel_crypto_order`, `cancel_option_exercise`), plus `exercise_option` and `decline_trade_approval`.
- Read-only tools only. `review_option_order` is allowed in Task 2 for a dry check, never `place_option_order`.
- **Enforcement, not just instructions:** before any session that has the Robinhood connection does Phase A work, the owner adds Claude Code permission *deny* rules for every forbidden tool above (Task 1, Step 0). The Python guard alone is not enough, because Python code cannot reach Robinhood; only the Claude session can.
- Account: Robinhood "MCP" account (digits in `CLAUDE.local.md`). The other account is never touched.
- Fully separate from the MGC "Manager" system: no shared code, files or memory. Do not read or modify `~/MGC-Trading-Agent`.
- Times are America/Chicago. Market 8:30-15:00 CT (early-close days per `events.json`).
- Spread: $1 wide, short strike near 10 delta, minimum credit $0.10, take profit at 50% of credit, hard flat 60 minutes before the close.
- Loss exit is SPY trading through the short strike. Mark-based 2x-credit exit is a shadow variant.
- Fills are pessimistic: sell at the bid, buy at the ask.
- Fees: $0.04 per contract per leg per transaction (real figure from the Task 2 order review: OCC $0.02 + ORF $0.02; $0.16 for a full open-and-close of one spread).
- Snapshot cadence **[my call]**: every 5 minutes; a gap over 15 minutes marks the day incomplete.

## Review Focus
1. One-sided or zero quotes (bid 0 or missing): that strike is skipped, never crashes or yields a fake credit. (Task 5)
2. A gap in the snapshot series (collector paused): the day is flagged incomplete and excluded from results, not silently computed. (Task 3, Task 6)
3. Holidays and early-close days (day after Thanksgiving closes 12:00 CT): no trade on closed days, and the flat cutoff moves with the real close. (Task 4)
4. No same-day (0DTE) expiry in the chain: the day is skipped with a reason. (Task 6)
5. Corrupt or partial snapshot file, or a repeated write of the same timestamp: the bad file is skipped with a warning; an identical rewrite is a no-op; a different rewrite is refused. (Task 3)
6. Optimism leaks: no data after the entry time is used to pick the trade; strike touches between snapshots are caught from 1-minute bars; take-profit fills at its limit price; when a loss and a win land in the same window, the loss counts. (Task 6)
7. Coverage: a day that starts after the entry time or stops before the flat cutoff is incomplete, not quietly scored. (Task 3, Task 4)

---

## File Structure
```
spybot/__init__.py   config.py   models.py   snapshots.py   events.py
spybot/ingest.py     strikes.py  bias.py     shadow.py      report.py   __main__.py
tests/conftest.py  tests/test_*.py  tests/fixtures/
collector/RUNBOOK.md   docs/stage0-findings.md   data/  (git-ignored)
CLAUDE.md  (exists: hard rules)   .gitignore   pyproject.toml
```

### Task 1: Scaffold and the no-orders guard
**Files:** Create `pyproject.toml`, `.gitignore` (contains `data/`, `__pycache__/`), `spybot/__init__.py`, `spybot/config.py`, `tests/test_config.py`, `tests/test_no_orders.py`.
**Interfaces:** Produces `spybot.config` constants: `TARGET_DELTA=0.10`, `SPREAD_WIDTH=1`, `MIN_CREDIT=0.10`, `TAKE_PROFIT_FRACTION=0.5`, `FLAT_CUTOFF_MINUTES_BEFORE_CLOSE=60`, `ENTRY_TIME=time(9,30)`, `MAX_LOSS_PCT=0.05`, `MARKET_TZ="America/Chicago"`, `FEE_PER_CONTRACT_LEG=0.03`, `SNAPSHOT_INTERVAL_MIN=5`, `MAX_GAP_MIN=15`, `VIX_UNCLEAR=30`, `TIME_EXIT=time(13,0)`.
- [ ] **Step 0 (owner action, before Task 2):** the owner adds permission deny rules for every forbidden tool in Global Constraints (Claude walks the owner through it; Claude cannot edit settings files itself). Verify by reading the settings file back and listing the deny rules in `docs/stage0-findings.md`. Do not start Task 2 until this is done.
- [ ] **Step 1:** `git init` in the project folder; write the failing tests:
  - `tests/test_config.py::test_constants_match_design` asserts `TARGET_DELTA == 0.10`, `SPREAD_WIDTH == 1`, `MIN_CREDIT == 0.10`, `TAKE_PROFIT_FRACTION == 0.5`, `FLAT_CUTOFF_MINUTES_BEFORE_CLOSE == 60`, `MAX_LOSS_PCT == 0.05`.
  - `tests/test_no_orders.py::test_source_never_references_order_tools` reads every `spybot/**/*.py` and `collector/*.md` and asserts none contains `place_`, `cancel_`, `exercise_option` or `decline_trade_approval`, except inside the runbook's clearly marked "Forbidden tools" section (the test skips the lines between `<!-- forbidden-start -->` and `<!-- forbidden-end -->`).
- [ ] **Step 2:** Run `pytest -q`. Expected: FAIL (config missing).
- [ ] **Step 3:** Implement `spybot/config.py` with the constants above.
- [ ] **Step 4:** Run `pytest -q`. Expected: 2 passed.
- [ ] **Step 5:** Commit `chore: scaffold, config, no-orders guard`.

### Task 2: Stage-0 feasibility spike (read-only, throwaway code allowed)
**Files:** Create `docs/stage0-findings.md`, `tests/fixtures/raw/` (raw tool responses, saved exactly as returned).
**Interfaces:** Produces the answers later tasks depend on; each answer recorded as `Answer: <value> (evidence: <tool call and output>)`. Also produces raw response fixtures that Task 3's parser is built and tested against. Task 2 depends on no later task.
**Precondition:** Task 1 Step 0 (deny rules) is done, and the Robinhood connection is signed in.
- [ ] **Step 1:** Environment: run `python3 --version` and `python3 -m pytest --version` on the Mac. If Python 3.9+ or pytest is missing, record it and stop for the owner.
- [ ] **Step 2:** Using Robinhood tools `get_option_chains`, `get_option_instruments`, `get_option_quotes` for SPY, record: is there a same-day expiry; are `delta` and `iv` present on quotes; how stale is the quote timestamp versus a TradingView SPY quote (`mcp-tv-get-symbol-data`).
- [ ] **Step 3:** Call `get_option_historicals` for one SPY option; record how many days and what interval exist (decides whether a backtest is possible).
- [ ] **Step 4:** Dry order check: call `review_option_order` once for a $1-wide SPY put credit spread on the MCP account (the account is found with `get_accounts`; only the `agentic_allowed` account). **Never call `place_option_order`.** Record alerts, fee lines and buying-power effect. Replace the `FEE_PER_CONTRACT_LEG` value if real fees are shown.
- [ ] **Step 5:** Data sources the collector will need, recorded with evidence: (a) yesterday's SPY close (which tool returns it); (b) SPY 1-minute high/low bars for today via TradingView `mcp-tv-get-ohlcv` (do they exist, how far back, how delayed); (c) VIX quote source.
- [ ] **Step 6:** Runner test with a **throwaway** cycle (no project code needed): each cycle reads SPY and VIX, finds today's expiry, quotes strikes within $15 of spot, and saves the raw responses unchanged to `data/stage0/<HHMM>/`. Run it every 5 minutes for **at least 60 minutes (12+ cycles)** in one session. Record: did the session stay responsive; any tool rate limits or errors; roughly how much session context each cycle uses and the projected number of cycles before the session fills (a full day is about 78 cycles). This decides the live-runner question for the next plan.
- [ ] **Step 7:** Copy one complete cycle's raw responses (chain, instruments, quotes, SPY, VIX) into `tests/fixtures/raw/`, plus one 1-minute bars response and one previous-close response. These must contain no account numbers.
- [ ] **Step 8:** Verify: `docs/stage0-findings.md` has an `Answer:` for every question above and no order was placed (check `get_option_orders` shows nothing new). Commit `docs: stage-0 findings`. **Always stop here and show the owner the findings before Task 3** (per CLAUDE.md). If delta/iv are absent, no 0DTE expiry exists, 1-minute bars are unavailable, or a full day will not fit in one session, flag it plainly: Tasks 3-8 or the design may need to change.

### Task 3: Snapshot model, storage, and write CLI
**Files:** Create `spybot/models.py`, `spybot/snapshots.py`, `spybot/ingest.py`, `spybot/__main__.py`, `tests/conftest.py`, `tests/test_snapshots.py`, `tests/test_ingest.py`.
**Data layout:** all collected data lives under `data/`: snapshots in `data/snapshots/YYYY-MM-DD/HHMM.json`, 1-minute SPY bars in `data/bars/YYYY-MM-DD.json`, previous closes in `data/prev_close.json` (`{"YYYY-MM-DD": close}`, keyed by the trading day the close is used *for*), events in `data/events.json`. `--root` defaults to `data`.
**Interfaces:**
- Produces `@dataclass(frozen=True) OptionQuote(strike: float, side: str, bid: float, ask: float, delta: float | None, iv: float | None)` (`side` is `"call"` or `"put"`).
- Produces `Snapshot(ts: datetime, spy: float, vix: float | None, expiry: date, quotes: list[OptionQuote])`; `ts` is tz-aware Central.
- Produces `Bar(ts: datetime, high: float, low: float)` and `DayData(day: date, snapshots: list[Snapshot], bars: list[Bar], warnings: list[str], complete: bool)`.
- Produces `write_snapshot(root: Path, snap: Snapshot) -> Path`, `read_day(root: Path, day: date, events: Events | None = None) -> DayData` (when `events` is given, completeness also checks coverage; see Step 3).
- Produces `ingest.parse_cycle(raw_dir: Path) -> Snapshot`: builds a `Snapshot` directly from the raw tool responses the collector saved, so the collector never retypes numbers. Raises `ValueError` with a clear message on anything missing or malformed.
- Produces CLI `python -m spybot ingest --raw DIR [--root PATH]` (parse one cycle's raw responses and write the snapshot), `python -m spybot save-bars --raw FILE [--root PATH]`, `python -m spybot save-prev-close --day YYYY-MM-DD --close FLOAT [--root PATH]`. Exit code 1 with a message on invalid input.
- Produces test helper `conftest.make_snapshot(ts, spy, quotes, vix=15.0, expiry=None)`.
- [ ] **Step 1:** Write failing tests. `tests/test_snapshots.py`: `test_write_then_read_roundtrip` (equal snapshot back), `test_rewrite_identical_is_noop`, `test_rewrite_different_raises_file_exists_error`, `test_corrupt_file_skipped_with_warning` (day still loads, `warnings` has one entry), `test_gap_over_15_minutes_marks_day_incomplete` (09:30 then 09:50 → `complete is False`), `test_five_minute_series_is_complete` (08:30 to 14:00 every 5 min), `test_late_start_marks_day_incomplete` (series starts 10:00, after `ENTRY_TIME` → `complete is False`), `test_early_stop_marks_day_incomplete` (series ends 13:00, before `flat_cutoff` → `complete is False`), `test_missing_bars_marks_day_incomplete`. `tests/test_ingest.py`: `test_parse_real_cycle` (the Task 2 raw fixtures parse into a `Snapshot` with SPY, expiry and at least 20 quotes), `test_parse_missing_spy_raises`, `test_cli_ingest_rejects_bad_input` (exit code 1).
- [ ] **Step 2:** Run `pytest tests/test_snapshots.py tests/test_ingest.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement the interfaces above; JSON in/out, `zoneinfo` for tz. `complete` is False when the day has no snapshots, any gap exceeds `MAX_GAP_MIN`, the first snapshot is later than `ENTRY_TIME`, the last snapshot is earlier than `flat_cutoff(day)`, or 1-minute bars are missing for the entry-to-cutoff window. (Coverage checks need `flat_cutoff` from Task 4; until Task 4 exists, use a 14:00 default and replace it in Task 4.)
- [ ] **Step 4:** Run `pytest -q`. Expected: all pass.
- [ ] **Step 5:** Commit `feat: snapshot model, storage and CLI`.

### Task 4: Event calendar and market hours
**Files:** Create `spybot/events.py`, `tests/test_events.py`, `data/events.json` example in `tests/fixtures/events.json`.
**Interfaces:** Consumes nothing. Produces `load_events(path: Path) -> Events` (JSON: `{"events": {"YYYY-MM-DD": ["FOMC"]}, "closed": [...], "early_close": {"YYYY-MM-DD": "12:00"}}`), `skip_reason(day: date, events: Events) -> str | None`, `market_close(day: date, events: Events) -> time`, `flat_cutoff(day: date, events: Events) -> time`.
- [ ] **Step 1:** Failing tests: `test_event_day_skips` (`skip_reason(date(2026,12,9), ev) == "event: FOMC"` for a fixture entry), `test_weekend_skips` (`date(2026,11,21)` → `"weekend"`), `test_closed_day_skips` (`date(2026,11,26)` → `"market closed"`), `test_normal_close_and_cutoff` (`market_close == time(15,0)`, `flat_cutoff == time(14,0)`), `test_early_close_moves_cutoff` (`date(2026,11,27)` → close `time(12,0)`, cutoff `time(11,0)`), `test_no_skip_returns_none`.
- [ ] **Step 2-4:** Run to fail; implement; run to pass (`pytest tests/test_events.py -v`).
- [ ] **Step 4b:** Replace Task 3's 14:00 default: `read_day(root, day, events)` uses `flat_cutoff(day, events)`. Add `test_early_close_day_complete_at_new_cutoff` (2026-11-27, series 08:30 to 11:00 → `complete is True`). Run `pytest -q`; all pass.
- [ ] **Step 5:** Commit `feat: event calendar and market hours`.

### Task 5: Spread picker and delta estimate
**Files:** Create `spybot/strikes.py`, `spybot/models.py` (add `Spread`), `tests/test_strikes.py`.
**Interfaces:** Consumes `Snapshot`, `OptionQuote`. Produces `Spread(side: str, short_strike: float, long_strike: float, entry_credit: float, width: float)`, `estimate_delta(spot: float, strike: float, iv: float, minutes_to_expiry: float, side: str) -> float` (Black-Scholes, zero rate, `math.erf`), `candidate_spread(snap: Snapshot, side: str, width: float = SPREAD_WIDTH, target_delta: float = TARGET_DELTA, min_credit: float = MIN_CREDIT) -> Spread | None`.
- [ ] **Step 1:** Failing tests with an inline chain (spot 600, put 598 bid 0.15 delta -0.10, put 597 ask 0.04): `test_picks_strike_closest_to_target_delta` (short 598, long 597), `test_credit_is_pessimistic` (`entry_credit == approx(0.11)`, i.e. short bid minus long ask), `test_returns_none_below_min_credit` (long ask 0.12 → credit 0.03 → None), `test_zero_bid_returns_none`, `test_missing_long_strike_returns_none`, `test_call_side_mirrors` (short 602, long 603), `test_estimate_delta_atm_put_near_minus_half` (`estimate_delta(600,600,0.15,360,"put")` within 0.02 of -0.5), `test_deep_otm_put_delta_tiny` (`abs(estimate_delta(600,590,0.15,360,"put")) < 0.01`), `test_uses_estimate_when_quote_delta_missing`.
- [ ] **Step 2-4:** Run to fail; implement (use quote delta when present, otherwise `estimate_delta` from `iv`; skip the strike if neither exists); run to pass.
- [ ] **Step 5:** Commit `feat: spread picker`.

### Task 6: Bias reader and shadow simulator
**Files:** Create `spybot/bias.py`, `spybot/shadow.py`, `tests/test_bias.py`, `tests/test_shadow.py`.
**Interfaces:** Consumes Tasks 3-5. Produces `read_bias(day: DayData, prev_close: float) -> str` (`"bullish" | "bearish" | "neutral" | "unclear"`), `StrategySpec(name: str, width: float, side_rule: str, exit_rule: str)` with the shadow set `always_put`, `bias`, `wide2`, `wide3`, `exit_mark_2x`, `exit_time` (`SHADOW_SPECS: dict[str, StrategySpec]`), `TradeResult(strategy: str, day: date, entered: bool, skip_reason: str | None, exit_reason: str | None, pnl: float | None)` (`pnl` is dollars per contract after fees), `simulate_day(day: DayData, spec: StrategySpec, events: Events, prev_close: float | None) -> TradeResult`. `read_bias` is only called when `prev_close` is not None.
- **No look-ahead:** the entry snapshot is the first snapshot at or after `ENTRY_TIME`. `read_bias` and `candidate_spread` see only snapshots up to and including the entry snapshot; the simulator passes them a truncated `DayData`, never the whole day.
- Rules: `read_bias` returns `"unclear"` when VIX >= `VIX_UNCLEAR`; `"bullish"` when entry-time SPY is above `prev_close` and above the first snapshot's SPY; `"bearish"` when below both; else `"neutral"`. `bias` strategy: put spread if bullish/neutral, call spread if bearish, no trade if unclear.
- Shadow set side and exit rules: `always_put` (side always put, standard exits); `bias` (side from bias, standard exits); `wide2` and `wide3` (side always put, standard exits, width 2 and 3); `exit_mark_2x` (side always put, standard exits plus `mark_stop`); `exit_time` (side always put, standard exits plus `time_exit`). Keeping every variant except `bias` on puts means each comparison changes one thing at a time against `always_put`.
- Exits, checked in time order after entry, first trigger wins:
  - `strike_touch`: checked against **1-minute bars**, not just snapshots: the first bar whose low (puts) or high (calls) is at or through the short strike. The exit debit is the pessimistic debit (short ask minus long bid) at the first snapshot at or after that bar; if that is not available, the day's pnl is the maximum loss (`width` minus credit, times 100, minus fees) and the trade is flagged `"exit price unknown"`.
  - `take_profit`: a resting buy-back limit at `(1 - TAKE_PROFIT_FRACTION) * credit`, rounded **up** to the cent. It counts as filled at the first snapshot whose pessimistic debit is at or below the limit, and the fill price is **the limit price**, not the lower observed debit.
  - `mark_stop` (only `exit_mark_2x`): the debit at a snapshot is at or above `3 * credit` (a loss of 2x credit).
  - `time_exit` (only `exit_time`): first snapshot at or after `TIME_EXIT`.
  - Otherwise `time_flat`: first snapshot at or after `flat_cutoff`.
  - If a bar touch and a take-profit both fall inside the same 5-minute window, assume the loss happened first (pessimistic).
- `pnl = (credit - exit_price) * 100 - 4 * FEE_PER_CONTRACT_LEG`.
- [ ] **Step 1:** Failing tests (inline helper days): `test_bias_unclear_when_vix_at_least_30`, `test_bias_bullish_on_gap_up_and_uptrend`, `test_bias_ignores_snapshots_after_entry` (a big move after 09:30 does not change the bias or the chosen spread), `test_take_profit_fills_at_limit_price` (credit 0.12, later debit 0.05 → `exit_reason == "take_profit"`, exit price 0.06, `pnl == approx(5.84)`), `test_strike_touch_between_snapshots_is_caught` (snapshots never show SPY at the strike, but a 1-minute bar low does → `exit_reason == "strike_touch"`), `test_strike_touch_exit_is_a_loss`, `test_touch_and_take_profit_same_window_counts_loss`, `test_flat_at_cutoff_when_no_trigger`, `test_incomplete_day_not_simulated` (`entered False`, `skip_reason == "incomplete data"`), `test_no_same_day_expiry_skips` (`skip_reason == "no 0DTE chain"`), `test_event_day_skips`, `test_always_put_ignores_bias`, `test_one_sided_quotes_skip_day`, `test_missing_prev_close_skips_bias_only` (`bias` skips with `"no previous close"`; `always_put` still trades).
- [ ] **Step 2-4:** Run to fail; implement; run to pass.
- [ ] **Step 5:** Commit `feat: bias reader and shadow simulator`.

### Task 7: Report and CLI
**Files:** Create `spybot/report.py`, extend `spybot/__main__.py`, `tests/test_report.py`.
**Interfaces:** Consumes `TradeResult`. Produces `Summary(trades: int, wins: int, win_rate: float, avg_pnl: float, total_pnl: float, worst: float, skipped: int)`, `summarize(results: list[TradeResult]) -> Summary` (skipped days excluded from `trades`), `compare(by_strategy: dict[str, list[TradeResult]]) -> str` (text table), CLI `python -m spybot report [--root PATH]` (reads `events.json` and `prev_close.json` from the root; defaults to `data`). The report lists incomplete days and trades flagged `"exit price unknown"` separately, so they are visible rather than silently dropped.
- [ ] **Step 1:** Failing tests: `test_summarize_counts` (pnl `[10, 10, -90]` → `trades 3`, `wins 2`, `total_pnl -70`, `worst -90`, `win_rate approx(2/3)`), `test_skipped_excluded_from_trades`, `test_compare_contains_each_strategy_name`, `test_empty_results_does_not_crash`.
- [ ] **Step 2-4:** Run to fail; implement; run to pass.
- [ ] **Step 5:** Commit `feat: report`.

### Task 8: Collector runbook and first live logging day
**Files:** Create `collector/RUNBOOK.md`.
**Interfaces:** Consumes `python -m spybot ingest`, `save-bars`, `save-prev-close` (Task 3) and `data/events.json` (Task 4). Produces one snapshot file per cycle, one bars file per day, one previous-close entry per day.
- [ ] **Step 1:** Write the runbook:
  - Allowed tools (read-only): Robinhood `get_option_chains`, `get_option_instruments`, `get_option_quotes`, plus whichever tools Task 2 found for previous close and VIX; TradingView `mcp-tv-get-symbol-data`, `mcp-tv-get-ohlcv`, `mcp-tv-get-economic-calendar`.
  - The full forbidden list from Global Constraints, between `<!-- forbidden-start -->` and `<!-- forbidden-end -->` markers (the Task 1 guard checks nothing else in the runbook names them).
  - Morning step (before 08:30 CT): refresh `data/events.json` from the economic calendar; record yesterday's SPY close with `save-prev-close`.
  - One cycle: read SPY and VIX → find today's SPY expiry → quote strikes within $15 of spot → **save the raw responses unchanged** to `data/raw/<today>/<HHMM>/` → run `python -m spybot ingest --raw <that dir>`. Never retype prices by hand. On any error, log it and continue.
  - End-of-day step (after the flat cutoff): fetch today's SPY 1-minute bars and run `save-bars`.
  - If Task 2 showed a full day does not fit in one session, the runbook says how to hand off to a fresh session mid-day (per the Task 2 finding).
- [ ] **Step 2:** Run one cycle by hand. Verify: `ls data/snapshots/<today>/` shows one file and `python -m spybot report` runs without error.
- [ ] **Step 3:** Run a full session day (5-minute cycles, morning and end-of-day steps included). Verify: `read_day` reports `complete` for the day or lists the reasons; `pytest -q` still passes; `get_option_orders` shows no new orders.
- [ ] **Step 4:** Commit `docs: collector runbook`. Phase A is done when five full trading days are logged. The next plan (paper trading, runner choice) is written from `docs/stage0-findings.md`.

---
## Self-review notes
- Spec coverage: logger (Tasks 3, 8), event calendar (4), strike selector (5), shadow tracker and benchmark variants (6, 7), stage 0 questions including history, delta and runner (2), no-orders constraint (1). Deferred to the next plans by design: Risk Manager, Executor/Monitor, Watchdog, Reconciler, News Scanner, Reviewer, gates.
- Types: `Spread`, `TradeResult`, `DayData`, `Events` names are used identically across Tasks 3-7.
- Revision 2026-11-16 (owner-approved review fixes): deny rules as real enforcement and the full forbidden-tool list (Global Constraints, Task 1); Task 2 no longer depends on later tasks and the runner test runs 60+ minutes; collector saves raw responses and code parses them (Task 3, 8); day completeness covers entry to cutoff (Task 3, 4); no look-ahead, 1-minute-bar strike touches, take-profit at limit price (Task 6); previous close and bars collected (Task 8); shadow variant rules spelled out (Task 6); always stop after Task 2 (matches CLAUDE.md). No design thresholds were changed.
