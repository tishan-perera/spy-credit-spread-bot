# Stage 0 findings

## Task 1, Step 0: order tools blocked (done 2026-11-17)

Answer: yes, blocked (evidence below).

- File: `.claude/settings.json` (project settings; applies to every Claude Code session opened in this folder).
- 22 deny rules: the 11 forbidden tools from the plan's Global Constraints, for each of the two Robinhood connections this machine has (`mcp__robinhood__…` and the claude.ai connector `mcp__54da6bf0-5ad5-4b1a-b2c8-3eb2d921e7d1__…`):
  `place_option_order`, `place_equity_order`, `place_advanced_order`, `place_crypto_order`, `cancel_option_order`, `cancel_equity_order`, `cancel_advanced_order`, `cancel_crypto_order`, `cancel_option_exercise`, `exercise_option`, `decline_trade_approval`.
- Evidence: the file parses as valid JSON with 22 deny rules. Right after saving it, Claude Code removed all 22 tools from the session's available tools (both connections). No order tool was called to test this.
- Limits: the rules apply only to Claude Code sessions in this project folder. They do not stop orders placed from other folders, other apps, or the Robinhood app itself. If Robinhood adds a new order tool later, it must be added here by hand.

## Task 2: feasibility spike (2026-11-17, read-only, market open)

All calls were read-only Robinhood tools plus one TradingView quote. No order was placed; the order tools are blocked (above).

### Step 1. Environment
Answer: Python 3.9.6 (macOS system Python); pytest 8.4.2 installed into the project's `.venv` with the owner's approval. (evidence: `python3 --version`, `.venv/bin/python -m pytest --version`)
Note: Python 3.9 needs `from __future__ import annotations` at the top of any module that uses `float | None` style type hints.

### Account
Answer: MCP account found (digits kept private), the only account this agent may use; options Level 3. Its type is **limited margin** (the design says "margin"). The other account is visible but marked not usable by this agent. (evidence: `get_accounts`, 09:14 CT)

### Step 2. Option chain, quotes, greeks, freshness
- Same-day (0DTE) expiry: **Answer: yes.** 2026-11-17 is listed, as are 11-18, 11-19, 11-20 (daily expiries). (evidence: `get_option_chains` SPY)
- Strikes: $1 apart near the money (e.g. puts 700 to 779 every $1), $5 apart further out. (evidence: `get_option_instruments`, expiration 2026-11-17, type put)
- Delta and IV on quotes: **Answer: yes, both present**, plus gamma, theta, vega, bid/ask sizes, open interest, volume. (evidence: `get_option_quotes`, 20 puts 718-737)
- Freshness: **Answer: seconds old.** Option quotes `updated_at` 15:14:58Z, SPY quote 15:14:37Z, both fetched about 15:14:59Z. TradingView SPY 736.92 vs Robinhood last 737.37 (0.06% apart, fetched within a few seconds; TradingView gives no timestamp). (evidence: `get_equity_quotes` SPY, `mcp-tv-get-symbol-data` AMEX:SPY)
- Robinhood's own forced close time for today's contracts: `sellout_datetime` 20:45Z = **2:45 p.m. CT**. The design's 2:00 p.m. flat cutoff is earlier, so no conflict.
- Contract list size: one expiry's put list is about 100 contracts and very large; the collector should fetch contract IDs once per morning and reuse them.

**Design-relevant finding: at 10 delta, the $1 spread pays less than the $0.10 minimum.** At 09:14 CT (SPY 737.37, VIX 22.83):

| Short put / long put | Short delta | Short bid | Long ask | Pessimistic credit |
|---|---|---|---|---|
| 728 / 727 | -0.096 | 0.32 | 0.26 | **$0.06** |
| 729 / 728 | -0.117 | 0.40 | 0.33 | $0.07 |
| 730 / 729 | -0.144 | 0.51 | 0.41 | $0.10 |
| 731 / 730 | -0.175 | 0.64 | 0.52 | $0.12 |

So "10 delta" and "at least $0.10 credit" cannot both hold on this morning; the minimum credit is only reached near 14-15 delta. This is one morning only. It is for the owner to decide (design change), not the builder.

### Step 3. Option history
Answer: **price bars exist, bid/ask history does not.** `get_option_historicals` returns OHLC bars (5-minute, 1-minute available) for today's contracts and for expired ones (checked: SPY 700 put that expired 2026-10-16). Bars are trade prices with no volume; minutes with no trade are filled in and marked `interpolated`. No historical bid/ask, so a backtest could only use trade prices and would be optimistic about fills. Exactly how far back history goes was not measured beyond one month.

### Step 4. Dry order review (`review_option_order`, nothing placed)
Order reviewed: sell 1 SPY 2026-11-17 728 put, buy 1 727 put, limit credit $0.06, MCP account.
- Alerts (`order_checks`): **none.**
- Fees to open: **$0.08** = OCC $0.04 + ORF $0.04 (each $0.02 per contract per leg). So **$0.04 per contract per leg**; a full open-and-close is about $0.16. `FEE_PER_CONTRACT_LEG` changed from the $0.03 placeholder to **0.04** in `spybot/config.py`, as the plan instructs.
- Collateral: $100 cash held (the full spread width; the credit is not netted against it).
- `customer_approval_required: false`, confirming that Robinhood's approval tap is off.
- The tool's own guidance suggested placing the order next. Ignored: Phase A never places orders.

### Step 5. Data sources for the collector
- (a) Yesterday's SPY close: **Answer: `get_equity_quotes` SPY**, field `close.price` (2026-11-16: 739.95, official close).
- (b) SPY 1-minute bars: **Answer: Robinhood `get_equity_historicals`**, interval `minute`, with high and low per minute; complete bars about 1 minute behind; up to about 2 weeks of minute bars per request. TradingView is not needed for this.
- (c) VIX: **Answer: Robinhood `get_index_quotes` VIX** (22.83 at 10:14:31 ET, timestamped).
- TradingView warned after one call that **more than half of today's tool-call quota is already used.** The collector should not depend on TradingView during the day; all of the above come from Robinhood.

### Step 6. Runner test (15 cycles, 09:18 to 10:20 CT, one session)
Answer: **every cycle worked; a full trading day will not fit in one session the way it was run today.**

- 15 cycles about every 4-5 minutes over 62 minutes, all in this one session. Each cycle = SPY quote + VIX + 20 put quotes + 20 call quotes (4 tool calls, run in parallel), then saving a record. **No errors, no rate limits, no stale quotes**: every option quote was under 2 seconds old when received. A cycle took 15-30 seconds end to end. Waiting between cycles used a background timer, which worked reliably.
- **Size per cycle:** the two 20-contract quote responses are about 45,000 characters together, roughly 12,000-14,000 tokens of session memory per cycle, before any writing. A full day is about 78 cycles, roughly 1 million tokens, far more than one session holds without being summarised. Cutting to about 6 strikes per side and dropping unneeded fields would still be about 300,000 tokens a day.
- **Saving raw responses is not possible as planned.** Python code cannot read tool results; only the Claude session sees them. To save anything, the session must re-type it into a file. Cycle 1 was saved in Robinhood's own layout (only the fields the bot needs); cycles 2-15 were saved as a compact table typed by the session. This is still transcription, which the plan's fix was meant to avoid. **This changes Task 3 and Task 8 and needs an owner decision** (options below).
- **The strike window must move with SPY.** SPY fell about $9 during the test, and the 10-delta put drifted to the edge of the quoted strikes by 09:45. At 09:50 the window was moved down using contract IDs already looked up in the morning (no new lookup needed). The collector must re-centre each cycle.
- **Locked quotes exist:** three times an option showed bid equal to ask (put 735 at 09:41, put 729 and call 733 at 10:12), with Robinhood's fill-rate fields empty. Task 5 and Task 6 need a test for bid = ask.
- **1-minute bars caught a strike touch the snapshots missed.** SPY first went below 728 in the 09:51 bar (low 727.69), between the 09:50 snapshot (729.48) and the 09:54 snapshot (727.64). Lowest point in the window: 727.00 (09:54 bar). This confirms the plan's 1-minute-bar fix.
- **A real example of the risk.** A 728/727 put spread sold at 09:14 for $0.06 would have hit the strike-touch exit at about 09:51-09:54, buying back at about $0.46: a loss of about **$40** after fees (the $6 win it was aiming for, versus a $40 loss). SPY then bounced back above 728 by 09:56 (whipsaw): five minutes later the same spread cost only $0.27 to close.
- **10-delta credits all morning:** across all 15 cycles the 10-delta $1 put spread paid **$0.03-$0.06** and the call spread **$0.05-$0.07** at pessimistic prices. It never reached the design's $0.10 minimum, even as VIX rose from 22.8 to 27.1.

**Options for the runner (owner's decision, not made here):**
1. Fewer, smaller cycles in one session: about 6 strikes per side, every 10 minutes. Still large; the session would be summarised during the day.
2. A fresh short session for each cycle, started by a scheduler on this Mac. Each session does one cycle and exits, so memory never builds up. Needs a scheduler that runs every 5-10 minutes; cloud scheduled tasks run at most hourly.
3. Collect only at a few fixed times (entry time, every 30 minutes, cutoff) plus the 1-minute SPY bars at the end of the day. Much smaller; strike-touch exits come from the bars, take-profit checks are coarser.

### Step 7. Test data saved
`tests/fixtures/raw/`: `cycle_0918.json` (one full cycle: SPY with previous close, VIX, 20 puts, 20 calls), `ids-2026-11-17.json` (strike-to-contract map), `bars-2026-11-17.json` (66 one-minute SPY bars, 09:14-10:19 CT). Checked: no account numbers in any fixture. All 15 cycle records are in `data/stage0/` (git-ignored).

### Step 8. Verification
- `get_option_orders` for the MCP account since 2026-11-16: **no orders.** No order tool was called at any point; they are blocked.
- `pytest -q`: 2 passed (see commit).

## Summary for the owner (decisions needed before Task 3)
1. **10 delta vs $0.10 minimum credit.** Today they never met. Options: accept a lower minimum (e.g. $0.05), move to about 14-17 delta, use $2-wide spreads, or keep both rules and trade far less often. Design change: owner's call.
2. **Runner.** Today's single-session approach will not last a full day. Choose one of the three options above.
3. **Saving raw data.** Not possible as planned; the session must type what it saves. Accept typed compact records (with a validation check), or pick option 2 or 3 above to keep each record small.
4. **Account type:** the MCP account is "limited margin", not "margin" as the design says. Spreads still work (Level 3, review passed). Just a correction to the design text.
5. **Fees:** real cost is $0.04 per contract per leg ($0.16 per round trip), already applied.
