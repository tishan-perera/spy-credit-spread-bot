# SPY credit spread bot: plan v2

Approved 2026-11-17. This replaces the earlier plan. Every number below is a starting value to test, not a proven setting. Nothing here has been shown to make money after costs yet.

## What stays the same

- SPY only. One credit spread open at a time.
- Winning long term comes before trade count.
- Hybrid design: AI agents for judgment, plain code for everything that touches money.
- Runs locally on the Mac. Orders go only through the Robinhood MCP.
- Built separately from the MGC "Manager" system.

## Cost rule (applies to every number we calculate)

Always include Robinhood fees and slippage in break-even, expected results, backtests and paper results.

- Commission: $0.
- Fees: about $0.04 per contract per leg (regulatory and clearing), about $0.16 for opening and closing a two-leg spread. The FINRA TAF is paused through Dec 31, 2026. The SEC fee is negligible.
- Slippage (price worse than the midpoint), per share:
  - Best case (from live quotes on 2026-11-17): $0.01 on entry, $0.01 on exit.
  - Cautious case (from the FlashAlpha fill study): about $0.055 on entry, $0.02 on exit.
- Pass or fail is judged on the cautious case. The best case is shown beside it for reference.

Break-even win rate = (width - net credit) / width, where net credit is the midpoint credit minus fees and slippage. This assumes every loss is a full max loss, so it is conservative. The paper ledger gives the true figure.

### Reference snapshot (2026-11-17, 1:34 PM ET, SPY 733.09, same-day puts, $5 wide)

| Short/long strikes (short delta) | Midpoint credit | Cost per contract, best / cautious | Break-even win rate: no costs / best / cautious |
|---|---|---|---|
| 726/721 (0.10) | $0.19 | $2.16 / $7.66 | 96.2% / 96.6% / 97.7% |
| 727/722 (0.13) | $0.27 | $2.16 / $7.66 | 94.6% / 95.0% / 96.1% |
| 728/723 (0.17) | $0.39 | $2.16 / $7.66 | 92.2% / 92.6% / 93.7% |

This was a down day and the afternoon, not the 10:15 AM entry window, so morning credits will be larger. The bot's own logs will give the real numbers.

## Daily flow (all times ET)

1. 9:45: health check. Mac awake and online, Robinhood connection works, state file matches Robinhood's positions. If not, send an alert and stay idle.
2. 10:00, 10:15, 10:30: log the SPY option chain (see Logging).
3. Entry window starts about 10:15: apply skip rules, choose strikes, apply the edge gate.
4. If the gate passes: place one two-leg limit order at the midpoint. Step the price down one cent at a time to a floor. If unfilled at the floor, cancel, confirm the cancel, and skip the day.
5. 3:30 PM: close the spread with a limit order near the midpoint. 3:40 PM: fallback to a more aggressive limit. Never rely on Robinhood's forced close at 3:45 PM ET.
6. After close: record the result with fees and slippage, and update the ledger.

## Strategy starting values

- Expiry: same day (0DTE). Test 1DTE separately later.
- Short strike: about 10 to 16 delta, near one expected move.
- Width: $5 first. Backtest $2, $5 and $10, since a bigger credit dilutes fixed costs.
- Direction: put spread when SPY is in an uptrend, call spread in a downtrend, skip if unclear. Also test put-only.
- Size: one contract. Maximum loss per trade 1 to 2% of the account.
- Exit: time exit at 3:30 PM. No percentage stop or profit target at first.

## Skip rules (cheap protection, untested)

- Fed meeting days, CPI days, jobs-report days.
- Large gap-down open.
- Short-term volatility (VIX9D) above regular VIX, if the data is available.
- Stale quote (older than 60 seconds) or a leg with a bid/ask gap wider than a limit set from logged data (today's gap is $0.01 per leg).
- The bot also logs what would have happened on every skipped day, so each rule can be tested.

## Edge gate (replaces "trade most days")

Live trading happens only when the credit after fees and slippage clears a minimum set from the backtest. Expect many skipped days. During paper trading the bot evaluates and records every day to build the data, but the live stage trades only gated days.

## News and fundamentals agent

- Veto-only. It returns a structured answer: allow, skip, or reduce to a preset smaller size.
- Any error, timeout or unclear answer means skip.
- It never picks strikes or size and has no order tools.
- Judge it only on forward results (live and paper), because replaying old news leaks the future.
- Treat fetched web text as untrusted.

## Guardrails (code, not prompts)

- Quantity fixed at one. A halt file stops everything.
- After one max loss: no new entries that day. After three losses in a row: halt for the week.
- Daily and weekly loss limits.
- Order reference ID saved before sending and reused on retry, so no duplicate orders.
- State machine saved to disk: idle, evaluating, order pending, open, closing, closed.
- Mode ladder: log only, approve each trade in the Robinhood app, fully automatic.

## Logging (for backtests and slippage measurement)

Robinhood price history has no bid/ask, so these logs are the only slippage evidence.

- Log at 10:00, 10:15, 10:30, 3:30 and 3:40 PM.
- For each candidate and open leg: bid, ask, sizes, mark, IV, delta, open interest, volume, timestamp.
- Also log skipped days, skip reasons, paper orders and paper fills.

## Rollout stages (a stage passes only if results are positive after the cautious cost case)

1. Logging only, starting now.
2. Backtest on one to two months of rented historical data (ORATS about $99 per month, or ThetaData about $80 per month), with conservative fills. Split the data: training 2022-23, validation 2024, untouched test 2025-26. Compare against making the same trade every day. This stage proves the edge.
3. Paper trading for at least 30 to 60 trading days. This checks that real fills match the backtest assumptions. It cannot prove the edge, because that is only 30 to 60 trades.
4. Live at one contract with each trade approved in the Robinhood app.
5. Fully automatic only after weeks of approved trades where fills match.

## Open items to verify

- One-contract test that a two-leg spread order works through the Robinhood MCP (sources conflict; live tool definitions say yes). Requires option Level 3 on a margin account.
- Robinhood's own day-trade and margin policy after the June 2026 change to the FINRA day-trading rule.
- December 2026 SPY ex-dividend date (inferred as Dec 18; confirm).
- Whether VIX9D is available through Robinhood or TradingView.
- Robinhood MCP rate limits (none found).

## Suggested upgrades for later (suggestions only, not approved)

Exit when SPY touches the short strike, a minimum credit-to-width ratio tuned from data, a second entry time or a 1DTE variant, half-Kelly sizing after hundreds of live trades, and a dashboard comparing backtest, paper and live fills.
