# Price Test and Logger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only backtest ("price test") that computes the break-even credit for plan v2 setups from years of free SPY/VIX daily prices, plus a daily logger of real Robinhood option quotes whose real credits are compared against it.

**Architecture:** Claude sessions fetch Robinhood data (MCP) and write raw JSON files; plain Python (stdlib only) checks those files, scores every historical day, sweeps setups, compares with logged real credits, and writes a plain-English report. Nothing in this plan sends, changes or cancels an order.

**Tech Stack:** Python 3.9 (system), stdlib only (`dataclasses`, `json`, `zoneinfo`, `statistics`, `csv`), pytest 8 in `.venv`.

**Spec:** `docs/superpowers/specs/2026-11-17-price-test-and-logger-design.md` (owner-approved 2026-11-17). Strategy source: `docs/plan-v2.md`.

**Replaces:** `docs/superpowers/plans/2026-11-16-spy-bot-phase-a-plan.md` (Tasks 3–8 of that plan are not built).

## Global Constraints

- **Never call any order tool.** No `place_*`, `cancel_*`, `exercise_option` or `decline_trade_approval`, on either Robinhood server. Only read tools (`get_*`) are used. Do not call `review_option_order` in this plan either.
- Only the Robinhood account "MCP" (digits in `CLAUDE.local.md`) may be read; this plan needs no account calls at all.
- Never read or reuse anything from `~/MGC-Trading-Agent` or other trading folders.
- Python 3.9: every module starts with `from __future__ import annotations`. No new dependencies.
- Run tests with `.venv/bin/python -m pytest -q`. Git commits need to run outside the sandbox (`.git` writes are blocked inside it). Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- All times US Eastern (`America/New_York`). Robinhood timestamps are UTC; convert with `zoneinfo`.
- Costs (plan v2): fees $0.04 per contract per leg, $0.16 open+close for a two-leg spread. Slippage per share: best $0.01 entry + $0.01 exit; cautious $0.055 entry + $0.02 exit. Pass/fail on cautious.
- Periods: training 2022-01-01..2023-12-31, validation 2024-01-01..2024-12-31, test 2025-01-01..end (sealed: only the `final` command shows it).
- Bars with `"interpolated": true` are filler and must never be used as prices.
- Every report starts with the limits text in Task 8.
- Data files under `data/` stay git-ignored. Reference files the code needs (calendars, events) live in `spybot/reference/` and are committed.

## Review Focus

1. **Look-ahead.** Trend must use only closes before the trade day; gap uses that day's open; VIX uses that day's open. A future price must never change a past decision. Test in Task 4 (`test_trend_ignores_trade_day_and_later`).
2. **Filler bars.** Robinhood returns flat `interpolated` bars at today's price for dates it has no data for (seen 2026-11-17 for 2025 and early 2026). They must be dropped and the day reported missing. Test in Task 2 (`test_interpolated_bars_are_dropped_and_reported`).
3. **Early-close and missing days.** Day after Thanksgiving / Christmas Eve close at 13:00; exit at 12:30 and a shorter remaining-day fraction. A trading day missing from the data is listed, not silently skipped. Tests in Task 1 and Task 4.
4. **Sealed test period.** `report` must not print any 2025+ number, including in the CSV and the proxy-error section. Test in Task 8 (`test_report_never_contains_sealed_days`).
5. **Imperfect logger files.** Stale quotes, a missing 10:15 run, locked quotes (bid == ask, valid), and strikes outside what was logged ("not logged", never filled in). Tests in Tasks 6 and 7.

---

### Task 1: Plan v2 settings and market calendar

**Files:**
- Modify: `spybot/config.py` (replace the old Phase A values)
- Modify: `tests/test_config.py`
- Create: `spybot/calendar.py`
- Create: `spybot/reference/market_calendar.json`
- Create: `tests/test_calendar.py`

**Interfaces:**
- Produces (config): `MARKET_TZ = "America/New_York"`, `ENTRY_TIME = time(10, 15)`, `EXIT_TIME = time(15, 30)`, `EXIT_FALLBACK_TIME = time(15, 40)`, `LOG_TIMES = (time(10,0), time(10,15), time(10,30), time(15,30), time(15,40))`, `EXIT_MINUTES_BEFORE_CLOSE = 30`, `WIDTHS = (2, 5, 10)`, `K_VALUES` = 0.5 to 2.0 step 0.1 (16 values, rounded to 1 decimal), `FEE_PER_CONTRACT_LEG = 0.04`, `FEES_ROUND_TRIP = 0.16`, `SLIPPAGE = {"best": (0.01, 0.01), "cautious": (0.055, 0.02)}`, `TREND_LOOKBACK = 20`, `TREND_BAND = 0.005`, `GAP_DOWN_SKIP = 0.01`, `VIX_BANDS = (15, 20, 30)`, `PERIODS = {"train": (date(2022,1,1), date(2023,12,31)), "validation": (date(2024,1,1), date(2024,12,31)), "test": (date(2025,1,1), None)}`, `HISTORY_START = date(2022, 1, 3)`, `STALE_QUOTE_SEC = 60`, `TUE_THU_0DTE_START` (a `date`, set in Step 1 from a verified source).
- Produces (calendar): `trading_days(start: date, end: date) -> list[date]`, `close_time(day: date) -> time`, `exit_time(day: date) -> time`, `has_0dte(day: date) -> bool`, `remaining_fraction(day: date, start: time) -> float` (minutes from `start` to `exit_time(day)` divided by 390).

- [ ] **Step 1: Research the reference dates (read-only web lookups)**

  - NYSE holidays and early closes 2022–2026 from nyse.com (holidays page) → `spybot/reference/market_calendar.json` as `{"source": [...urls], "holidays": ["YYYY-MM-DD", ...], "early_closes": ["YYYY-MM-DD", ...]}`.
  - The first date SPY had Tuesday and Thursday expiries (Cboe/OCC notice; designer recalls about 2022-11-14) → `TUE_THU_0DTE_START`, with the source URL in a comment. If no official source is found, stop and ask the owner.

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_config.py
def test_plan_v2_values():
    assert config.WIDTHS == (2, 5, 10)
    assert config.K_VALUES[0] == 0.5 and config.K_VALUES[-1] == 2.0 and len(config.K_VALUES) == 16
    assert config.FEES_ROUND_TRIP == pytest.approx(0.16)
    assert config.SLIPPAGE["cautious"] == (0.055, 0.02)
    assert config.ENTRY_TIME == time(10, 15) and config.EXIT_TIME == time(15, 30)
    assert config.MARKET_TZ == "America/New_York"

# tests/test_calendar.py
def test_holidays_and_weekends_are_not_trading_days():
    days = calendar.trading_days(date(2024, 12, 23), date(2024, 12, 27))
    assert days == [date(2024,12,23), date(2024,12,24), date(2024,12,26), date(2024,12,27)]

def test_early_close_moves_exit_to_1230():
    assert calendar.close_time(date(2024, 12, 24)) == time(13, 0)
    assert calendar.exit_time(date(2024, 12, 24)) == time(12, 30)
    assert calendar.exit_time(date(2024, 12, 23)) == time(15, 30)

def test_remaining_fraction():
    assert calendar.remaining_fraction(date(2024, 12, 23), time(10, 15)) == pytest.approx(315 / 390)
    assert calendar.remaining_fraction(date(2024, 12, 24), time(10, 15)) == pytest.approx(135 / 390)

def test_0dte_days_before_and_after_tue_thu_start():
    assert calendar.has_0dte(date(2022, 1, 3))        # Monday
    assert not calendar.has_0dte(date(2022, 1, 4))    # Tuesday, before the start
    assert calendar.has_0dte(date(2024, 1, 2))        # Tuesday, after
    assert not calendar.has_0dte(date(2024, 12, 25))  # holiday
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_config.py tests/test_calendar.py -q`
Expected: FAIL (missing names / module).

- [ ] **Step 4: Implement `config.py` values and `calendar.py`**

  Remove the old Phase A constants (`TARGET_DELTA`, `SPREAD_WIDTH`, `MIN_CREDIT`, `TAKE_PROFIT_FRACTION`, `FLAT_CUTOFF_MINUTES_BEFORE_CLOSE`, `TIME_EXIT`, `MAX_LOSS_PCT`, `SNAPSHOT_INTERVAL_MIN`, `MAX_GAP_MIN`, `VIX_UNCLEAR`) and the old test. Keep the docstring warning that changes need owner approval. Calendar reads the JSON once (module-level cache).

- [ ] **Step 5: Run all tests** — `.venv/bin/python -m pytest -q` → all pass (including `test_no_orders.py`).

- [ ] **Step 6: Commit** — `feat: plan v2 settings and market calendar`

---

### Task 2: Historical bars loader and checks

**Files:**
- Create: `spybot/history.py`
- Create: `tests/test_history.py`
- Create: `tests/fixtures/history/` (small real samples, see Step 1)

**Interfaces:**
- Consumes: `calendar.trading_days`.
- Produces:
  - `@dataclass(frozen=True) DayBar: day: date; open: float; high: float; low: float; close: float`
  - `load_daily(paths: list[Path]) -> tuple[dict[date, DayBar], list[str]]` — merges files; returns bars and problems. Accepts both the equity format (`data.results[].bars[]` with `open_price` … `close_price`, `begins_at`) and the index format returned by `get_index_historicals` (field names taken from the real sample in Step 1).
  - `load_intraday(paths: list[Path]) -> tuple[dict[date, dict[time, float]], list[str]]` — maps ET bar start time → bar `open_price`.
  - `check_daily(bars: dict[date, DayBar], start: date, end: date) -> list[str]` — missing trading days, `high < low`, any price ≤ 0, close-to-close change over 25%.
  - `price_at(intraday: dict[date, dict[time, float]], day: date, t: time) -> float | None`

- [ ] **Step 1: Save real samples (read-only tools)**

  In a session, call `get_equity_historicals` (SPY, `interval="day"`, 2022-01-03 to 2022-01-07), `get_index_historicals` (VIX instrument id from `get_indexes`, `interval="day"`, same dates), and `get_equity_historicals` (SPY, `interval="5minute"`, one recent full day). Write each tool's JSON output unchanged to `tests/fixtures/history/spy_day.json`, `vix_day.json`, `spy_5min.json`. Also save one filler response (SPY 5-minute for 2025-06-02 14:30–15:00Z, which returns `interpolated: true` bars) as `spy_5min_filler.json`.

- [ ] **Step 2: Write the failing tests**

```python
def test_loads_spy_daily_sample():
    bars, problems = history.load_daily([FIX / "spy_day.json"])
    assert bars[date(2022, 1, 3)] == history.DayBar(date(2022,1,3), 476.30, 477.85, 473.85, 477.71)
    assert problems == []

def test_loads_vix_daily_sample():
    bars, problems = history.load_daily([FIX / "vix_day.json"])
    assert date(2022, 1, 3) in bars and problems == []

def test_interpolated_bars_are_dropped_and_reported():
    bars, problems = history.load_intraday([FIX / "spy_5min_filler.json"])
    assert bars == {}
    assert any("interpolated" in p for p in problems)

def test_missing_trading_day_is_reported():
    bars, _ = history.load_daily([FIX / "spy_day.json"])
    del bars[date(2022, 1, 5)]
    assert any("2022-01-05" in p for p in history.check_daily(bars, date(2022,1,3), date(2022,1,7)))

def test_intraday_uses_eastern_time():
    intraday, _ = history.load_intraday([FIX / "spy_5min.json"])
    day = next(iter(intraday))
    assert time(9, 30) in intraday[day] and time(15, 55) in intraday[day]
    assert history.price_at(intraday, day, time(10, 15)) is not None
```

- [ ] **Step 3: Run to verify failure** — `.venv/bin/python -m pytest tests/test_history.py -q` → FAIL.
- [ ] **Step 4: Implement `history.py`.**
- [ ] **Step 5: Run all tests** → pass.
- [ ] **Step 6: Commit** — `feat: load and check historical bars`

---

### Task 3: Event days file

**Files:**
- Create: `spybot/reference/events.json`
- Modify: `spybot/calendar.py` (add `event_days`)
- Modify: `tests/test_calendar.py`

**Interfaces:**
- Produces: `event_days() -> dict[date, list[str]]` with labels `"fomc"`, `"cpi"`, `"jobs"`.

- [ ] **Step 1: Fill `events.json` from official calendars (read-only web lookups)** — FOMC decision days (second day of each meeting) from federalreserve.gov; CPI release days and Employment Situation release days from bls.gov; 2022-01-01 through 2026-12-31. Format: `{"sources": [...urls], "fomc": [...], "cpi": [...], "jobs": [...]}`. Expect about 8 FOMC, 12 CPI and 12 jobs dates per year; if a year has a different count, write why in a `"notes"` field.
- [ ] **Step 2: Write the failing tests**

```python
def test_event_days_counts_per_year():
    ev = calendar.event_days()
    for year in (2022, 2023, 2024, 2025):
        days = [d for d in ev if d.year == year]
        assert sum("fomc" in ev[d] for d in days) == 8
def test_known_event_day():
    assert "fomc" in calendar.event_days()[date(2024, 9, 18)]
def test_event_days_are_trading_days():
    for d in calendar.event_days():
        assert d in calendar.trading_days(d, d)
```

- [ ] **Step 3: Run to verify failure**, **Step 4: implement**, **Step 5: run all tests**, **Step 6: commit** — `feat: event days from official calendars`

---

### Task 4: Score one historical day

**Files:**
- Create: `spybot/pricetest.py`
- Create: `tests/test_pricetest.py`

**Interfaces:**
- Consumes: `DayBar`, `price_at`, `calendar.exit_time`, `calendar.remaining_fraction`, `calendar.event_days`, config values.
- Produces:
  - `@dataclass(frozen=True) Setup: width: int; k: float; variant: str` — variant is `"baseline"` (put every day, no skips), `"put_skips"` (put, skip rules), `"v2"` (trend direction + skip rules).
  - `@dataclass(frozen=True) DayInputs: day: date; entry: float; exit: float; open: float; prev_close: float; closes_before: tuple[float, ...]; vix_open: float; fraction: float; events: tuple[str, ...]; real_times: bool`
  - `build_inputs(day: date, spy: dict[date, DayBar], vix: dict[date, DayBar], intraday: dict[date, dict[time, float]], events: dict[date, list[str]]) -> DayInputs | None` — `None` if the day lacks SPY or VIX bars or fewer than `TREND_LOOKBACK` earlier closes. Entry/exit = intraday prices at `ENTRY_TIME` / `calendar.exit_time(day)` when both exist (`real_times=True`), else open/close.
  - `trend(inp: DayInputs) -> str` — `"up"` if `prev_close > avg(closes_before[-20:]) * (1 + TREND_BAND)`, `"down"` if below `avg * (1 - TREND_BAND)`, else `"unclear"`.
  - `expected_move(inp: DayInputs) -> float` — `entry * vix_open / 100 * sqrt(fraction / 252)`.
  - `strikes(entry: float, move: float, side: str, k: float, width: int) -> tuple[int, int]` — put: short = `floor(entry - k*move + 0.5)`, long = short − width; call: short = `floor(entry + k*move + 0.5)`, long = short + width.
  - `exit_value(side: str, short: int, width: int, exit_price: float) -> float` — put `min(max(short - exit_price, 0), width)`, call `min(max(exit_price - short, 0), width)`.
  - `@dataclass(frozen=True) DayResult: day: date; side: str; short: int; long: int; value: float; skipped: tuple[str, ...]; vix_open: float`
  - `score_day(inp: DayInputs, setup: Setup) -> DayResult` — side is `"put"` for baseline and put_skips; for v2 it is `"put"` on up, `"call"` on down, and `"put"` (scored, but skipped with reason `"trend unclear"`) on unclear. Skip reasons for put_skips and v2: each event label, `"gap down"` when `open < prev_close * (1 - GAP_DOWN_SKIP)`. Baseline never skips.

- [ ] **Step 1: Write the failing tests**

```python
def inp(**kw):  # helper building DayInputs with neutral defaults:
    # entry=500, exit=500, open=500, prev_close=500, closes_before=(500.0,)*20,
    # vix_open=16, fraction=315/390, events=(), real_times=False, day=date(2024,3,6)
    ...

def test_expected_move():
    assert pricetest.expected_move(inp()) == pytest.approx(500 * 0.16 * math.sqrt((315/390)/252))

def test_put_strikes_round_to_nearest_dollar():
    assert pricetest.strikes(500.0, 4.5, "put", 1.0, 5) == (496, 491)   # 495.5 rounds up
    assert pricetest.strikes(500.0, 4.5, "call", 1.0, 5) == (505, 510)  # 504.5 rounds up

def test_exit_value_partial_and_full_loss():
    assert pricetest.exit_value("put", 496, 5, 497.0) == 0
    assert pricetest.exit_value("put", 496, 5, 494.0) == 2.0
    assert pricetest.exit_value("put", 496, 5, 480.0) == 5
    assert pricetest.exit_value("call", 505, 5, 507.5) == 2.5

def test_trend_ignores_trade_day_and_later():
    up = inp(prev_close=505.0)                      # 1% above the 500 average
    assert pricetest.trend(up) == "up"
    assert pricetest.trend(inp(prev_close=501.0)) == "unclear"
    assert pricetest.trend(inp(prev_close=495.0)) == "down"
    # build_inputs: changing the trade day's own close or later closes must not change closes_before
    ...

def test_v2_skips_events_and_gap_down_but_baseline_does_not():
    day = inp(events=("cpi",), open=494.0)          # 1.2% gap down
    r_base = pricetest.score_day(day, pricetest.Setup(5, 1.0, "baseline"))
    r_v2 = pricetest.score_day(day, pricetest.Setup(5, 1.0, "v2"))
    assert r_base.skipped == ()
    assert set(r_v2.skipped) >= {"cpi", "gap down"}

def test_v2_side_follows_trend():
    assert pricetest.score_day(inp(prev_close=505.0), pricetest.Setup(5, 1.0, "v2")).side == "put"
    assert pricetest.score_day(inp(prev_close=495.0), pricetest.Setup(5, 1.0, "v2")).side == "call"
    assert "trend unclear" in pricetest.score_day(inp(), pricetest.Setup(5, 1.0, "v2")).skipped

def test_build_inputs_uses_real_times_when_available():
    # 10:15 and 15:30 intraday prices present → entry/exit from them, real_times True;
    # absent → open/close, real_times False; early-close day → exit at 12:30 and fraction 135/390
    ...

def test_build_inputs_none_when_vix_missing():
    ...
```

  (Bodies marked `...` construct small `DayBar` dicts by hand; assertions as described in their comments.)

- [ ] **Step 2: Run to verify failure** — `.venv/bin/python -m pytest tests/test_pricetest.py -q` → FAIL.
- [ ] **Step 3: Implement `pricetest.py` (functions above).**
- [ ] **Step 4: Run all tests** → pass.
- [ ] **Step 5: Commit** — `feat: score one historical day`

---

### Task 5: Sweep setups and break-even credit

**Files:**
- Modify: `spybot/pricetest.py`
- Modify: `tests/test_pricetest.py`

**Interfaces:**
- Produces:
  - `cost_per_share(case: str) -> float` — `FEES_ROUND_TRIP / 100 + sum(SLIPPAGE[case])` (cautious = 0.0766, best = 0.0216).
  - `vix_band(vix: float) -> str` — `"<15"`, `"15-20"`, `"20-30"`, `"30+"` (lower bound inclusive).
  - `@dataclass(frozen=True) Summary: n_traded: int; n_skipped: int; loss_rate: float; full_loss_rate: float; worst_streak: int; avg_value: float; breakeven: dict[str, float]; by_band: dict[str, tuple[int, float]]` — `breakeven` keyed by `"best"`/`"cautious"`; `by_band[band] = (n_traded, cautious break-even)`; rates and averages are over traded (not skipped) days; `worst_streak` = longest run of consecutive traded days with `value > 0`.
  - `summarize(results: list[DayResult], width: int) -> Summary`
  - `in_period(day: date, period: str) -> bool`
  - `run_sweep(inputs: list[DayInputs], period: str, allow_sealed: bool = False) -> list[tuple[Setup, Summary]]` — every width × k × variant (144 setups); raises `PermissionError("test period is sealed")` when `period == "test"` and not `allow_sealed`.

- [ ] **Step 1: Write the failing tests**

```python
def test_cost_per_share_matches_plan_v2():
    assert pricetest.cost_per_share("cautious") == pytest.approx(0.0766)
    assert pricetest.cost_per_share("best") == pytest.approx(0.0216)

def test_breakeven_is_average_value_plus_costs():
    results = [result(value=0.0), result(value=0.0), result(value=0.0), result(value=5.0)]
    s = pricetest.summarize(results, 5)
    assert s.avg_value == pytest.approx(1.25)
    assert s.breakeven["cautious"] == pytest.approx(1.25 + 0.0766)
    assert s.loss_rate == 0.25 and s.full_loss_rate == 0.25

def test_skipped_days_are_counted_but_not_averaged():
    s = pricetest.summarize([result(value=5.0, skipped=("cpi",)), result(value=0.0)], 5)
    assert (s.n_traded, s.n_skipped, s.avg_value) == (1, 1, 0.0)

def test_worst_streak():
    vals = [0, 1, 2, 0, 1, 1, 1, 0]
    assert pricetest.summarize([result(value=v) for v in vals], 5).worst_streak == 3

def test_vix_band_edges():
    assert [pricetest.vix_band(v) for v in (14.9, 15, 20, 30)] == ["<15", "15-20", "20-30", "30+"]

def test_sealed_period_refused():
    with pytest.raises(PermissionError):
        pricetest.run_sweep([], "test")

def test_sweep_covers_144_setups_and_filters_period():
    out = pricetest.run_sweep([inp(day=date(2024, 3, 6)), inp(day=date(2023, 3, 6))], "validation")
    assert len(out) == 144
    assert all(s.n_traded + s.n_skipped == 1 for _, s in out)
```

- [ ] **Step 2: Run to verify failure**, **Step 3: implement**, **Step 4: run all tests** → pass.
- [ ] **Step 5: Commit** — `feat: sweep setups and break-even credit`

---

### Task 6: Logger file check (ingest)

**Files:**
- Create: `spybot/ingest.py`
- Create: `tests/test_ingest.py`
- Create: `tests/fixtures/logger/good_1015.json`, `stale_1015.json`

**Interfaces:**
- Raw logger file `data/raw/YYYY-MM-DD/HHMM.json` (written by the session, Task 9):
  `{"run_et": "YYYY-MM-DDTHH:MM:SS-05:00", "expiry": "YYYY-MM-DD", "spy": <get_equity_quotes output>, "vix": <get_index_quotes output>, "instruments": {"<id>": {"type": "put"|"call", "strike": 726.0, "expiry": "YYYY-MM-DD"}}, "quotes": [<get_option_quotes output>, ...]}`
- Produces:
  - `@dataclass(frozen=True) Leg: bid: float; ask: float; bid_size: int; ask_size: int; mark: float; iv: float; delta: float; open_interest: int; volume: int; updated_at: datetime`
  - `@dataclass(frozen=True) Snapshot: day: date; run: time; spy: float; vix: float; legs: dict[tuple[str, int], Leg]` — key `(type, strike)`; `spy` = SPY quote `last_trade_price`; `vix` = VIX `value`.
  - `parse(raw: dict) -> tuple[Snapshot | None, list[str]]` — problems: expiry ≠ run day, any instrument expiry ≠ run day, quote `updated_at` more than `STALE_QUOTE_SEC` from `run_et`, `bid > ask`, any required field missing, instrument id in quotes but not in `instruments`. Any problem → `(None, problems)`. `bid == ask` is valid.
  - `ingest(root: Path, day: date, hhmm: str) -> list[str]` — reads raw, writes `data/snapshots/DAY/HHMM.json` on success, or `data/snapshots/DAY/HHMM.bad.json` holding the problems; returns problems.
  - `load_snapshot(root: Path, day: date, hhmm: str) -> Snapshot | None` — `None` if missing or bad.

- [ ] **Step 1: Build fixtures from a real response** — in a session during market hours, read quotes for 4 same-day SPY puts and 4 calls (read-only `get_option_quotes`, plus `get_equity_quotes` SPY and `get_index_quotes` VIX) and write them in the raw format above as `good_1015.json`. Copy it to `stale_1015.json` and move `run_et` 5 minutes later than the quotes' `updated_at`. If the market is closed, use the 2026-11-17 19:07Z quote shape seen in the design session and hand-build the file with those field names.
- [ ] **Step 2: Write the failing tests**

```python
def test_good_file_parses_all_fields():
    snap, problems = ingest.parse(load(FIX / "good_1015.json"))
    assert problems == []
    leg = next(iter(snap.legs.values()))
    assert leg.bid <= leg.ask and leg.open_interest >= 0 and leg.updated_at.tzinfo is not None

def test_stale_quotes_rejected():
    snap, problems = ingest.parse(load(FIX / "stale_1015.json"))
    assert snap is None and any("stale" in p for p in problems)

def test_locked_quote_is_valid():
    raw = load(FIX / "good_1015.json"); set_first_quote(raw, bid="0.10", ask="0.10")
    assert ingest.parse(raw)[1] == []

def test_crossed_quote_and_wrong_expiry_rejected():
    raw = load(FIX / "good_1015.json"); set_first_quote(raw, bid="0.12", ask="0.10")
    assert any("bid > ask" in p for p in ingest.parse(raw)[1])
    raw = load(FIX / "good_1015.json"); raw["expiry"] = "2026-11-18"
    assert any("expiry" in p for p in ingest.parse(raw)[1])

def test_ingest_writes_bad_marker(tmp_path):
    write_raw(tmp_path, "stale_1015.json", day, "1015")
    assert ingest.ingest(tmp_path, day, "1015") != []
    assert (tmp_path / "data/snapshots" / day.isoformat() / "1015.bad.json").exists()
    assert ingest.load_snapshot(tmp_path, day, "1015") is None
```

- [ ] **Step 3: Run to verify failure**, **Step 4: implement**, **Step 5: run all tests** → pass.
- [ ] **Step 6: Commit** — `feat: check and ingest logger files`

---

### Task 7: Compare logged real credits with break-even

**Files:**
- Create: `spybot/compare.py`
- Create: `tests/test_compare.py`

**Interfaces:**
- Consumes: `Snapshot`, `load_snapshot`, `Setup`, `strikes`, `trend`, `vix_band`, `calendar.remaining_fraction`.
- Produces:
  - `@dataclass(frozen=True) RealRow: day: date; setup: Setup; side: str; short: int; long: int; status: str; mid_credit: float | None; natural_credit: float | None; short_delta: float | None; leg_gaps: tuple[float, float] | None; value_1530: float | None; value_1540: float | None` — status `"ok"` or `"not logged"` or `"no 10:15 run"`.
  - `real_row(day: date, setup: Setup, snaps: dict[str, Snapshot | None], closes_before: tuple[float, ...], prev_close: float, open_price: float) -> RealRow` — uses the 10:15 snapshot's SPY and VIX for the expected move (`fraction = remaining_fraction(day, ENTRY_TIME)`), the same `strikes` rule and v2 side rule as Task 4. Mid credit = short mid − long mid; natural = short bid − long ask; leg gaps = ask − bid per leg; `value_1530`/`value_1540` = spread mid at those runs (short mid − long mid), `None` if either leg is not logged.
  - `delta_by_k(rows: list[RealRow]) -> dict[float, float]` — average absolute short delta per `k` over `ok` rows.

- [ ] **Step 1: Write the failing tests** (build `Snapshot` objects by hand)

```python
def test_mid_and_natural_credit():
    row = compare.real_row(day, Setup(5, 1.0, "baseline"), snaps_with(put726=(0.41, 0.42), put721=(0.10, 0.11)), ...)
    assert row.status == "ok" and (row.short, row.long) == (726, 721)
    assert row.mid_credit == pytest.approx(0.31) and row.natural_credit == pytest.approx(0.30)
    assert row.leg_gaps == pytest.approx((0.01, 0.01))

def test_strike_outside_logged_range_is_not_logged():
    row = compare.real_row(day, Setup(10, 2.0, "baseline"), snaps_with(put726=(0.41, 0.42)), ...)
    assert row.status == "not logged" and row.mid_credit is None

def test_missing_1015_run():
    assert compare.real_row(day, Setup(5, 1.0, "baseline"), {"1015": None}, ...).status == "no 10:15 run"

def test_delta_by_k_averages_absolute_delta():
    assert compare.delta_by_k([row_k(1.0, -0.12), row_k(1.0, -0.16)]) == {1.0: pytest.approx(0.14)}
```

  (`snaps_with` sets SPY and VIX so that `strikes(...)` lands on 726/721 for k = 1.0, width 5; compute the SPY/VIX pair in the helper from the Task 4 formula.)

- [ ] **Step 2: Run to verify failure**, **Step 3: implement**, **Step 4: run all tests** → pass.
- [ ] **Step 5: Commit** — `feat: compare logged credits with break-even`

---

### Task 8: Report and command line

**Files:**
- Create: `spybot/report.py`
- Create: `spybot/__main__.py`
- Create: `tests/test_report.py`

**Interfaces:**
- Consumes: everything above. History files are read from `data/history/*.json` (SPY daily `spy_day_*.json`, VIX daily `vix_day_*.json`, SPY 5-minute `spy_5min_*.json`); snapshots from `data/snapshots/`.
- Produces:
  - `build_report(root: Path, today: date, final: bool = False) -> tuple[str, list[dict]]` — markdown text and CSV rows.
  - Commands: `python -m spybot check-history`, `python -m spybot ingest YYYY-MM-DD HHMM`, `python -m spybot report`, `python -m spybot final`. `report` writes `reports/backtest-YYYY-MM-DD.md` and `.csv`. `final` writes `reports/final-YYYY-MM-DD.md`/`.csv` and appends a line `YYYY-MM-DDTHH:MM final run` to `reports/final-runs.log`. `check-history` prints every problem from Task 2 and exits non-zero if any.
- Report contents, in order:
  1. Limits text, exactly:
     > **What this test can and cannot show.** Past days use the day's open and close in place of the real 10:15 and 3:30 prices, except where intraday prices exist. Option credits for past days are unknown, so the test gives the credit each setup would have *needed*; real credits come only from the bot's own logs. Credits are larger on volatile days, when losses also happen, and this test captures that only through VIX bands. Any time value left at 3:30 is ignored, which flatters wins slightly. The VIX9D skip rule is not tested (no data). This test can rule a setup out; it cannot prove one works.
  2. Data coverage: date range, days scored, days missing (listed), logged days and bad runs.
  3. Stand-in error: over days with both intraday and daily bars, average absolute gap between open and the 10:15 price and between close and the 3:30 price, in dollars and in expected moves.
  4. Per variant and width, a table for k = 0.6, 0.8, …, 2.0 with: days traded/skipped, loss rate, full-loss rate, worst streak, break-even best/cautious, logged days with `ok`, average real mid credit, average real short delta, and the verdict line.
  5. Break-even by VIX band for the v2 variant at width 5.
  6. Real bid/ask gaps per leg (average and worst) and average `value_1530` for logged days.
  - Verdict line format: `Needs $X.XX a spread after cautious costs; real 10:15 credits averaged $Y.YY over N logged days → pays|does not pay.` With no logged days: `Needs $X.XX a spread after cautious costs; no logged days yet.` Real credit for the verdict = average `mid_credit` minus cautious slippage (`0.075`) minus `FEES_ROUND_TRIP / 100`, compared with the cautious break-even minus the same costs (that is, average exit value); state "pays" only if real net credit > average exit value.
  - Normal report: price-test results for training and validation shown separately; no price-test outcome (scored day, summary, stand-in gap, CSV row) from 2025-01-01 on. Verdict lines compare against the **validation** break-even. **[planner's call]** Logged real quotes are not price-test outcomes, so the logged section (items 4's logged columns and 6) is shown in the normal report: averages only, no per-day dates, CSV rows with `period = "logged"`. The `final` report adds the test period and compares verdicts against the test-period break-even.

- [ ] **Step 1: Write the failing tests** (small temp `root` with hand-made history files and two snapshots)

```python
def test_report_starts_with_limits_text(tmp_root):
    md, _ = report.build_report(tmp_root, date(2026, 11, 20))
    assert md.lstrip().startswith("**What this test can and cannot show.**")

def test_report_never_contains_sealed_days(tmp_root_with_2025_days):
    md, rows = report.build_report(tmp_root_with_2025_days, date(2026, 11, 20))
    assert "2025-" not in md and "2026-0" not in md
    assert all(r["period"] in ("train", "validation", "logged") for r in rows)
    assert all("day" not in r for r in rows if r["period"] == "logged")

def test_final_includes_test_period_and_logs_run(tmp_root_with_2025_days):
    md, rows = report.build_report(tmp_root_with_2025_days, date(2026, 11, 20), final=True)
    assert any(r["period"] == "test" for r in rows)

def test_verdict_line_without_logs(tmp_root):
    md, _ = report.build_report(tmp_root, date(2026, 11, 20))
    assert "no logged days yet." in md

def test_cli_check_history_fails_on_problems(tmp_root_with_filler, capsys):
    assert main(["check-history", "--root", str(tmp_root_with_filler)]) != 0
```

- [ ] **Step 2: Run to verify failure**, **Step 3: implement** (`main(argv: list[str]) -> int` in `__main__.py`, `--root` defaults to the project folder), **Step 4: run all tests** → pass.
- [ ] **Step 5: Commit** — `feat: backtest report and commands`

---

### Task 9: Download history and run the first report

Session work with read-only tools; no new code unless a check fails.

- [ ] **Step 1: Download** — in chunks within each tool's limits, save unchanged tool output:
  - SPY daily 2022-01-03 → latest complete day: `data/history/spy_day_<start>_<end>.json` (`get_equity_historicals`, `interval="day"`).
  - VIX daily, same range (`get_index_historicals`, `interval="day"`, ≤ 4 years per call): `data/history/vix_day_<start>_<end>.json`.
  - SPY 5-minute bars, from the earliest date that returns real (non-interpolated) bars to the latest complete day, ≤ 12 weeks per call: `data/history/spy_5min_<start>_<end>.json`. Find the earliest real date by trying monthly starts backwards from 2026-08 until bars come back `interpolated`.
- [ ] **Step 2: Check** — `.venv/bin/python -m spybot check-history` → no problems. If a day is missing, re-download that chunk once; if still missing, list it in `docs/history-notes.md` and continue (the report lists missing days).
- [ ] **Step 3: Spot check (needs owner permission first: it downloads a public file)** — ask the owner to allow reading Cboe's free VIX history CSV (`https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv`). If allowed, compare 20 random days' open and close; record matches/mismatches in `docs/history-notes.md`. If not allowed, record "spot check skipped by owner".
- [ ] **Step 4: First report** — `.venv/bin/python -m spybot report` → `reports/backtest-YYYY-MM-DD.md`. Read it end to end; confirm no 2025+ outcomes appear.
- [ ] **Step 5: Commit** — `git add docs/history-notes.md reports/` → `docs: first price-test report` (the `reports/` folder is committed so the owner can read it; raw data stays ignored).

---

### Task 10: Logger task and scheduling

**Files:**
- Create: `collector/logger-task.md`
- Modify: `tests/test_no_orders.py` (no change in logic; it already scans `collector/*.md` — confirm it fails if a forbidden word is added outside the markers, then remove it)
- Modify: `CLAUDE.md` "Current work" (only with owner approval, Step 5)
- Modify: `docs/superpowers/plans/2026-11-16-spy-bot-phase-a-plan.md` (one line at the top: "Superseded on 2026-11-17 by 2026-11-17-price-test-and-logger-plan.md.")

**Interfaces:**
- Consumes: raw file format and `python -m spybot ingest` (Task 6/8).

- [ ] **Step 1: Write `collector/logger-task.md`** — instructions a fresh session follows at one log time:
  1. Working folder is this project. Only these tools may be used: `get_equity_quotes`, `get_index_quotes`, `get_option_chains`, `get_option_instruments`, `get_option_quotes`, plus file writes under `data/raw/` and running `python -m spybot ingest`. A marked forbidden section (between `<!-- forbidden-start -->` and `<!-- forbidden-end -->`) names the order tools that must never be called.
  2. Read SPY quote and VIX. Find today's expiry in the SPY chain; stop and write a `.bad.json` note if there is none.
  3. Strikes: same-day puts from SPY − 30 to SPY − 3 and calls from SPY + 3 to SPY + 30, whole dollars (about 56 instruments; at most 3 `get_option_quotes` calls of 20). At 15:30 and 15:40, also include any strike the 10:15 run's setups chose that is outside this range.
  4. Write the raw file in the Task 6 format to `data/raw/YYYY-MM-DD/HHMM.json`, then run `.venv/bin/python -m spybot ingest YYYY-MM-DD HHMM` and report its result in one line.
  5. If anything fails: write what failed into `data/raw/YYYY-MM-DD/HHMM.error.txt`, do nothing else.
- [ ] **Step 2: Guard check** — temporarily add the word `place_` outside the markers in `logger-task.md`, run `.venv/bin/python -m pytest tests/test_no_orders.py -q` → FAIL; remove it → PASS.
- [ ] **Step 3: One hand run during market hours** — follow `logger-task.md` once in this session at a log time; confirm `data/snapshots/DAY/HHMM.json` is written. Record tokens used for the run in `docs/logger-notes.md`. If one run uses more than 50k tokens, narrow the strike range in Step 1 (for example ±25) and note it.
- [ ] **Step 4: Ask the owner to approve the scheduled tasks** — show: five local scheduled tasks on weekdays at 10:00, 10:15, 10:30, 15:30, 15:40 ET, each running `collector/logger-task.md` in this project folder; the Mac must be awake with the Claude app open; they read quotes only. Create them (scheduled-tasks tool) only after a clear yes. Check that a scheduled run uses this project folder (so the order-tool deny rules in `.claude/settings.json` apply) by reading the first run's result.
- [ ] **Step 5: Ask the owner to approve the CLAUDE.md edit** — replace "Current work" with: "Execute `docs/superpowers/plans/2026-11-17-price-test-and-logger-plan.md` task by task (TDD, frequent commits). Backtest and logging only; no paper or live trading." Edit only after a yes.
- [ ] **Step 6: After one week of logging** — run `report`, record logger tokens per day and bad runs in `docs/logger-notes.md`, and show the owner the report.
- [ ] **Step 7: Commit** — `feat: logger task, scheduling notes`

---

## Self-review notes

- Spec coverage: §5 scoring → Tasks 4–5; §5 periods/sealed → Task 5 (`run_sweep`) and Task 8 (`final`); §6 logger → Tasks 6, 7, 10; §7 download and checks → Tasks 2, 9; §8 report → Task 8; §9 layout → file lists; §11 owner items → Task 10 Steps 4–5.
- Planner's calls beyond the spec: logger strike range ±$3 to ±$30 instead of "5 to 25 delta" (deltas aren't known before quoting; the range is narrowed if token use is high); the normal report shows logged 2026 credits as plain averages (logged days fall in the sealed period); `reports/` is committed.
- Deferred by design: paper trading, news agent, live guardrails, order code.
