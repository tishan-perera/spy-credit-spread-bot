# SPY Credit-Spread Bot: Design, revision 2 (DRAFT for approval)

Date: 2026-11-16. Status: **awaiting owner approval. Nothing is built until approved.**
Revision 2 adds the fixes from a hard-critic review (expiry safety, exits, benchmarks, honest gates, tool separation).
**[my call]** = a decision the planner made on the owner's behalf; the owner can change it.

## 1. Intent and why
Build an automated agent system that trades one SPY credit spread at a time, aiming to profit **long term** (the owner's stated priority), not to maximize win rate. A trade opportunity is evaluated every trading day using SPY's daily expirations (0DTE). Execution goes through the Robinhood connection. The owner is a beginner with no coding background (accounting), so the system must be understandable, auditable and safe by default.

**Honest expectation.** At this size a win is about $10 and a loss about $90 per contract, so a roughly 90% win rate is needed just to break even, and costs are a large share of profit. The design must be able to *disprove* the strategy cheaply. A finding of "no edge" is a success of the process, not a failure.

## 2. Goals / non-goals / anti-goals
**Goals**
- Evaluate a possible SPY credit spread every trading day; trade on most days.
- Positive expectancy (average profit per trade after fees and slippage), shown by evidence before size is added.
- Log everything (option snapshots, decisions, reasons, fills) so results can be audited and reconciled.
- A news agent that informs every decision.

**Non-goals**
- Other underlyings, other strategies, or multiple simultaneous positions. Later, if at all.
- Any link to the existing MGC "Manager" system.
- Free-form LLM control of trades.

**Anti-goals (failure even if it "works")**
- A high win rate whose rare losses wipe out the gains.
- Trading every day regardless of conditions.
- **Holding any position into the last hour of trading** (assignment into 100 shares of SPY).
- Any order outside the designated account, or any change to its own rules by the bot.

## 3. Constraints and facts
- Account: the Robinhood account nicknamed "MCP" (account digits kept in the private `CLAUDE.local.md`), margin type, options Level 3, the only account the bot may touch. Balance $250 today; owner plans about $2,000 more. The other account is off-limits.
- Multi-leg orders are **limit only**, priced as a net credit. Exits are bot-sent limit orders. Each order is first run through Robinhood's review step; any alert aborts it.
- Robinhood's "human must approve trades" setting is **off** (owner turned it off 2026-11-16; confirmed). Bot orders execute without a tap. Only the owner can change it and may turn it back on at any time. Anything with the Robinhood connection can place orders on this account, so the guardrails are the only safety net.
- Day-trading rule reported eliminated June 4, 2026. Robinhood's own help page still shows old wording: **owner confirms in-app before live trading.**
- SPY strikes are $1 apart, so the smallest spread risks about $85-95 (about 4% of $2,250).
- If a spread is open at the close and SPY finishes between the strikes, the short leg is assigned and the long leg expires worthless: the owner would hold 100 SPY shares (tens of thousands of dollars). $1-wide spreads make this plausible, not rare.
- The Robinhood connection works inside a Claude session. A 0DTE bot must monitor every few minutes; scheduled tasks normally run no more often than hourly. **Runner feasibility is unproven** (stage 0).
- Market hours 8:30 a.m. to 3:00 p.m. Central. Runs on the owner's MacBook for early phases (Mac awake, Claude app open).
- One trade a day takes about 1.6 years to reach 400 trades. Evidence must also come from historical data and shadow variants (section 8).

## 4. Approaches considered
**Trade frequency.** (A) every day, no exceptions; (B) evaluate every day, trade on most days; (C) slower 30-45 day spreads. **Owner chose B.**
**LLM authority.** (1) rules only; (2) hybrid with graded authority; (3) free-form. **Owner chose (2):** Stage 1 veto only; Stage 2 chooser only after evidence.
**Runner.** Local Mac, cloud scheduled runs (too coarse), hybrid. **[my call] hybrid:** early phases local; live runner decided after stage 0.
**Build size.** (Revision 2) Start with a logger and one plain rules baseline; add each agent only when logs show it helps. **[my call]**

## 5. Components
| Component | Type | Job |
|---|---|---|
| Data Logger | code | Every few minutes in session, log SPY price, VIX, near-the-money option quotes, to local files. |
| Event Calendar | code | FOMC, CPI, jobs report and similar dates from a data source, not from the LLM. Event days are skipped by default. |
| News Scanner | LLM | Looks only for surprise headlines. Returns a fixed record: `go` / `caution` / `veto` plus short reasons. **Runs in its own session with no Robinhood or file-writing tools.** |
| Bias Reader | code | Trend, overnight gap, VIX; outputs bullish / bearish / neutral / unclear. Starts as a *shadow* variant (section 8). |
| Strike Selector | code | Candidate $1-wide spreads; short strike near 10 delta; skip if credit under about $0.10. |
| Risk Manager | code | Enforces every guardrail. Final say; the LLM cannot override. |
| Executor/Monitor | code | Reviews then places the entry order; places the profit-taking order right after the fill; watches SPY against the short strike; sends the exit; flattens by the cutoff. |
| Watchdog | code | Separate small check. If the bot goes silent, or a position is still open at the second cutoff, it alerts the owner and attempts to close. |
| Reconciler | code | At open and at close, confirms the account is flat and matches the bot's log. |
| Shadow Tracker | code | Scores benchmark strategies on the same daily data (section 8). |
| Manager | code | Runs the daily sequence and records every decision with reasons. |
| Reviewer | LLM | End-of-day plain-English journal; proposes rule changes **for owner approval only**. |

## 6. Daily flow and trading rules **[my calls unless noted]**
1. Pre-market: Event Calendar and News Scanner. Event days, or a `veto`, mean skip.
2. About 9:30 a.m. Central: Bias Reader, Strike Selector, Risk Manager, then the entry order.
3. Right after the fill: a resting limit order to buy back at 50% of the credit (reduces dependence on the monitor).
4. **Loss exit is defined on SPY's price, not the option's price:** close when SPY trades through the short strike. Reason: at a $0.10 credit, a stop at 2x credit sits inside normal bid-ask noise and would trigger on quote flicker. The 2x-credit mark exit and a time exit run as shadow variants for comparison.
5. **Hard flat by 2:00 p.m. Central (one hour before the close).** Watchdog second cutoff 2:15 p.m.: alert and attempt to close; by 2:30 p.m. the owner is alerted to close by hand.
6. Exit orders are priced aggressively to ensure fills.
7. No trade is a valid outcome and is logged with its reason.

## 7. Guardrails
- One open spread; one contract; $1 wide; max loss at most 5% of account.
- One losing trade ends the day; weekly loss cap about 10%.
- Live trading halts if the account falls below about $1,800.
- Account flat check at open and close (Reconciler).
- A silent bot sends the owner an alert (Watchdog).
- Refuse to trade on stale data, unexpected account state, review-step alerts, or any error: **when unsure, do nothing.**
- Duplicate-order protection on every order. Account number hard-wired to the MCP account.
- Emergency stop switch plus a written manual runbook for cancelling orders and closing positions by hand.
- The bot cannot edit its own guardrails. Rule changes only after the owner approves.
- With approvals off, these protections replace the approval tap.
- Expect losing streaks: even at a 10% loss rate, two or more losses in a week happen about 8% of weeks, and losses cluster in volatile periods.

## 8. Data, benchmarks and evidence
- **Logging:** every few minutes during the session: SPY price, VIX, near-the-money option quotes (bid, ask, last, greeks where available), time stamped. Every decision (taken or skipped) with inputs and reasons. Every order and fill with fees. Plain files, easy to reconcile.
- **Shadow strategies** scored daily from the same logs at no extra cost: (a) always sell the 10-delta put spread; (b) bias-driven (the plan); (c) bias plus News veto; (d) $2- and $3-wide versions (to see whether costs shrink as a share of the credit); (e) alternative exits (2x-credit mark, time exit).
- **Historical check in stage 0:** find out how much option history Robinhood provides and what other history exists; if enough, run a rough backtest to try to rule the idea out early. Backtests are labeled as optimistic.
- **Evidence size:** with a per-trade swing of about $30, telling a $3-per-trade edge from zero takes on the order of 400 trades (rough calculation). The design never claims proof before then.

## 9. Gates (set before seeing results; numbers are my calls)
- **Gate 1, it works:** 20 clean trading days. The bot ran all session, was flat by the cutoff every day, logs match Robinhood, alerts arrived, and the emergency stop was tested.
- **Gate 2, early edge:** at least 60 trading days of paper results, positive after pessimistic costs, and better than the naive baseline. Owner approves going live at one contract.
- **Gate 3, real edge:** about 400 trade-equivalents (live, paper, history and shadows combined) beating the baseline after costs. Only then may size increase or the LLM move to Stage 2.
- **Risk budget:** the owner sets how much real money may be lost while proving the strategy. Suggested **$450** (the distance from $2,250 to the $1,800 floor).
- Pessimistic paper fills; the first live trades also measure real slippage versus the paper model.

## 10. Rollout stages
0. **Feasibility spike (throwaway):** can a session read option chains, log data and review test orders (no placement) all session? Which runner works? Is quote data timely, and are greeks provided? How much option history exists?
1. **Logging plus shadows:** save data daily and score the benchmark variants.
2. **Paper trading:** plain rules first; Bias Reader and News veto added as shadow variants, promoted only if the logs show value.
3. **Live, one contract,** after Gates 1 and 2, inside the risk budget.
4. **Review** against Gate 3 before more size or LLM Stage 2.

## 11. Security
News text is untrusted. The News Scanner runs in a session with no trading or file-writing tools and returns only the fixed record. Only the Executor can place orders, only in the MCP account. No agent follows instructions found in articles.

## 12. Separation
New folder, new files, no shared code, memory or state with the MGC "Manager" system.

## 13. Left to the builder
File layout, language, scheduling mechanism, exact delta and credit thresholds within the ranges above, log format, alert method, data source for the event calendar.

## 14. Open items for the owner
- Approve this design (revision 2).
- Set the risk budget (suggested $450).
- Choose how to be alerted (phone push or other).
- Confirm in the Robinhood app that day-trade restrictions are gone.
- Ask a CPA about wash-sale treatment for daily SPY option trading (the planner is not a tax advisor).
