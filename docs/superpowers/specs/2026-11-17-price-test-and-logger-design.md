# Price test and logger: design

Date: 2026-11-17. Status: **draft for owner approval.** Nothing is built until approved.
Based on [plan v2](../../plan-v2.md) (owner-approved 2026-11-17) and the owner's choices on 2026-11-17: backtest only for now, no paid data, approach "price test + logging".
**[my call]** marks a decision the designer made; the owner can change it.

## 1. Intent and why

Plan v2 says nothing goes live until a backtest shows the strategy makes money after the cautious costs. The owner will not pay for historical option data, so no free source of past option bid/ask prices exists (checked 2026-11-17). This design builds the strongest test possible for free:

- **Price test:** years of real SPY and VIX daily prices answer "how often, and by how much, would the spread have lost?" From that it computes the **break-even credit**: the credit each spread would need to collect, after cautious costs, to make money.
- **Logger:** collects real Robinhood option quotes at plan v2's fixed times each trading day. Those real credits are compared with the break-even credit. Over time the logs also measure real bid/ask gaps (slippage evidence).

The honest promise: this can show with confidence that an idea **does not** work. It can only weakly suggest that one does. Plan v2 stage 2 ("proves the edge") cannot be fully met without paid data; this design says so in every report.

## 2. Goals / non-goals / anti-goals

**Goals**
- Break-even credit for every tested setup, after the cautious costs (best case shown beside it), split into plan v2's periods.
- Compare plan v2's rules (direction + skip rules) against the plain baseline "sell the same put spread every day".
- A daily logger of real option quotes at 10:00, 10:15, 10:30, 3:30 and 3:40 PM ET, with every field plan v2 lists.
- A plain-English report the owner can read: needed credit vs. real credit seen, per setup.

**Non-goals (later stages, not built now)**
- Paper trading, live trading, order code, order state machine, news agent, health check, live guardrails.
- Paid data adapters.
- Charts or a dashboard.

**Anti-goals (failure even if it "works")**
- Any order tool called, ever (hard rule; the guard test and deny rules stay).
- A report that looks more certain than the data allows. Every report states the method's limits.
- Tuning settings on the 2025-26 test period. It stays sealed until the final run.
- Using information a trader would not have had at 10:15 that morning (look-ahead).

## 3. Constraints and facts (checked 2026-11-17)

- Robinhood daily SPY bars go back years (2022-01-03 returned real prices). Intraday SPY bars exist only for recent months (2026-08-03 real; 2026-01-05 and earlier came back as `interpolated: true` filler at today's price). Robinhood index history gives daily VIX bars (up to 4 years per call).
- Robinhood option history has trade prices only, no bid/ask. Not used for the price test.
- VIX9D is **not** on Robinhood (`not_found`). That skip rule is left out of the price test and noted in reports.
- Same-day option IV is far above VIX. Example at 2:07 PM ET today: 726 put IV 0.445 while VIX was 26.1. So a strike placed "one VIX expected move" away is **not** a 10-delta strike. The price test places strikes by VIX expected-move multiples, and the logger's real deltas translate those multiples into real deltas (section 6).
- `get_option_quotes` returns bid, ask, sizes, mark, IV, delta, open interest, volume and timestamp: all fields plan v2 wants.
- Robinhood data reaches code only through a Claude session (MCP). Code cannot call Robinhood itself. The session writes the tool output to files; code reads and checks them.
- SPY had same-day expiries only on Monday, Wednesday and Friday until late 2022, when Tuesday and Thursday were added (designer's recollection: around 2022-11-14; **builder must verify**). The price test only counts days that had a real same-day expiry.
- Hard rules from CLAUDE.md apply in full: no order tools, MCP account only (and only read tools), separate from MGC.
- Times are US Eastern, as in plan v2. **[my call]** The settings file moves from Central to Eastern.

## 4. Approaches considered

1. **Price test plus real credits from logs (chosen by the owner).** Years of real prices for outcomes; real credits from the logs. Weak spots: daily bars stand in for 10:15 and 3:30 prices; credit is not known for past days and is larger on volatile days, when losses also happen; can rule out, cannot prove.
2. **Estimate past option prices with a pricing formula.** Gives a credit for every past day, but same-day options (especially far-out puts) are priced very differently from any simple formula. Rejected: looks precise without being trustworthy.
3. **Logging only, test forward as data builds.** Fully real but slow (about 60 trading days in three months), which plan v2 itself says is too few to prove an edge. Kept as the second half of approach 1, not alone.

## 5. Price test: how one day is scored

For each trading day with a same-day SPY expiry, from 2022-01-03 to the latest complete day:

1. **Entry price.** Use SPY's price at 10:15 ET where intraday bars exist; elsewhere the day's open. **Exit price:** the 3:30 PM price where intraday bars exist; elsewhere the close. On early-close days (1 PM), the exit is 30 minutes before the close (12:30), or the close where no intraday bar exists. Over the months where both exist, the report shows how far the open/close stand-ins differ from the real 10:15/3:30 prices.
2. **Expected move.** Uses VIX at that day's open (known by 10:15): `move = entry × VIX/100 × sqrt(f / 252)`, where `f` is the share of the trading day left after 10:15 until the exit (5.25/6.5 on normal days).
3. **Strikes.** Put spread: short strike = entry − k × move, rounded to the nearest whole dollar; long strike = short − width. Call spread: mirror image above. `k` (distance in expected moves) and `width` are settings swept by the test.
4. **Direction (plan v2 rules variant).** Uptrend → put spread; downtrend → call spread; unclear → skip. **[my call]** Default trend rule: previous close vs. its 20-day average of closes; more than 0.5% above = up, more than 0.5% below = down, otherwise unclear. Both numbers are settings. Uses only closes from before the trade day.
5. **Skip rules (plan v2 rules variant).**
   - Fed decision, CPI and jobs-report days. **[my call]** Dates come from a file the builder fills from the official calendars (federalreserve.gov, bls.gov) for 2022 through 2026, checked into the repo with its sources.
   - Large gap-down: open below the previous close by more than a setting. **[my call]** Default 1.0%.
   - VIX9D rule: not available; recorded as "not tested" in the report.
   - Quote-quality rules (stale quote, wide bid/ask) can't be tested on past prices; they are applied only to logged days.
   - Every skipped day is still scored as if traded, so each rule's value can be measured.
6. **Value at exit.** Put spread: `value = clip(short − exit_price, 0, width)`; call spread: `clip(exit_price − short, 0, width)`. This ignores any time value left at 3:30, which flatters wins a little; the report says so.
7. **Costs per contract.** Fees $0.16 (open and close, two legs) plus slippage × 100: best case $0.01 + $0.01, cautious $0.055 + $0.02 (plan v2 cost rule). Settings, not code.

**Break-even credit** for a setup = average value at exit (per share) + costs per share. If the spread collects more than that on average, it made money in this test.

The report also shows, per setup: number of days traded and skipped, how often the spread finished with any value (loss days), how often it lost the full width, the worst run of losing days, and the break-even credit **by VIX band** (under 15, 15-20, 20-30, 30 and up) **[my call]**, because real credits grow with VIX.

### Setups tested

- Widths $2, $5, $10 (plan v2).
- `k` from 0.5 to 2.0 in steps of 0.1 **[my call]**.
- Variants: (a) baseline, put spread every day, no skips; (b) put only with skip rules; (c) plan v2 rules: direction + skip rules.

### Periods and the sealed test

- Training 2022-23, validation 2024, test 2025 to now (plan v2).
- Normal runs show training and validation only. The test period is reported only by a separate `final` command, which writes a dated record each time it is run, so any peeking is on the record. **[my call]**

## 6. Logger

- **When:** 10:00, 10:15, 10:30, 3:30 and 3:40 PM ET on trading days (shifted earlier on early-close days). **[my call]** Each run is a local scheduled Claude task (the Mac must be awake with the Claude app open). The owner approves creating these tasks before they exist.
- **What it reads (read-only tools only):** SPY quote, VIX, the same-day put and call strikes around the money, and their option quotes.
- **Strikes:** short candidates from about 5 to 25 delta on each side, plus the long legs $2, $5 and $10 further out. The 3:30 and 3:40 runs also re-read the legs that the 10:15 run would have chosen. **[my call]** Token budget target: under about 250k tokens per trading day, measured in the first week; the strike list shrinks if it runs over.
- **Saving:** the session writes each run's tool output to `data/raw/YYYY-MM-DD/HHMM.json`, then runs `python -m spybot ingest YYYY-MM-DD HHMM`. Code checks the file (expiry is today, timestamps within 60 seconds of the run, no missing fields, bid ≤ ask) and writes a clean snapshot to `data/snapshots/`. A failed check marks the run bad; it is never silently fixed.
- **Missed runs:** a day with a missing 10:15 run is left out of the credit comparison and listed in the report.
- **No orders:** the scheduled task's instructions list only read tools; the project's deny rules block all order tools; the guard test scans the task instructions too.

### Using the logs in the price test

For each logged day the code applies the same strike rule (`k`, width, direction) using that morning's 10:15 SPY price and VIX, then reads the **real** midpoint credit and bid/ask for those exact strikes. It records:
- real credit vs. break-even credit for each setup, per VIX band;
- which real delta each `k` corresponds to (so "10 to 16 delta" in plan v2 can be mapped to `k`);
- real bid/ask gaps per leg (slippage evidence for the cost rule);
- the real 3:30 and 3:40 spread value, to check the "no time value left at 3:30" assumption.

If a setup's strikes fall outside the strikes logged that day, that setup is marked "not logged" for the day, never filled in. Live guardrails that depend on the credit (three losses in a row, weekly loss limit) are not simulated, because the credit for past days is unknown; the report shows losing streaks instead.

## 7. Historical data download

- SPY daily bars 2022-01-03 to now and daily VIX bars over the same range, from Robinhood, saved by a session in chunks to `data/history/`. Recent-months intraday SPY bars (5-minute) saved the same way.
- Code checks every file: no `interpolated` bars, no missing trading days against the exchange calendar, prices within sane limits, and SPY splits/dividends handled consistently (split-adjusted, as Robinhood returns by default). **[my call]**
- A one-time spot check compares 20 random days with a second free public source (for example Cboe's published VIX history) and reports any mismatch. **[my call]**

## 8. Report

`python -m spybot report` writes `reports/backtest-YYYY-MM-DD.md` (plain English, with tables) and a CSV with every setup's numbers. The top of every report states the method's limits (section 1 and the weak spots in section 4). The verdict line per setup reads like: "Needs $0.42 a spread after cautious costs; real 10:15 credits for this setup averaged $0.31 over 23 logged days → does not pay."

## 9. Code layout **[my call]**

Builds on the existing project (Python 3.9, pytest, `spybot/`):
- `spybot/config.py`: plan v2 values (widths, costs, times in ET, trend and gap defaults).
- `spybot/history.py`: load and check historical bars.
- `spybot/calendar.py`: trading days, early closes, same-day-expiry days, event days.
- `spybot/pricetest.py`: scoring one day, sweeping setups, break-even credit.
- `spybot/ingest.py`: check raw logger files, write clean snapshots.
- `spybot/compare.py`: logged real credits vs. break-even.
- `spybot/report.py` and `spybot/__main__.py` (commands `ingest`, `report`, `final`).
- `collector/logger-task.md`: the scheduled task's instructions (read-only tools only).
- Tests for every module (TDD), including look-ahead tests and a test that `report` never prints the sealed period.

The old Phase A plan (5-minute checks, 50% profit-taking, $1 width, strike-touch exit) is replaced. The existing guard test, deny rules, fee figure and saved Task 2 samples are kept.

## 10. Left to the builder

File formats, exact chunk sizes for downloads, exact strike list for the logger within the budget, how the scheduled task is worded, and the exchange-calendar source.

## 11. Open items for the owner

- Approve this design.
- Approve creating the five daily scheduled logger tasks (asked again when they are ready).
- CLAUDE.md "Current work" still points at the old Phase A plan; it should point at the new plan once written (owner edits or approves the edit).
