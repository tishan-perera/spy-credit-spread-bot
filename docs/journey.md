# The journey so far, and what I learned

A short timeline of how the project got here, including the mistakes. Full detail is in the linked notes.

## Nov 16: the first design
The first design traded a $1-wide spread every morning: check every 5 minutes, take profit at 50%, exit if SPY touched the short strike. A 5-step rollout went from "log only" to "fully automatic". ([original design](../2026-11-16-spy-credit-spread-bot-design.md))

## Nov 17: test the idea before building it ("stage 0")
Before writing the bot, a half-day test ran on live data, with **all order tools blocked first**. ([stage-0 findings](stage0-findings.md))

- **The money didn't add up.** The planned 10-delta, $1-wide spreads paid only $0.03–$0.06 all morning, never reaching the design's $0.10 minimum.
- **A real example of the risk.** A spread sold for $0.06 would have hit its exit about 40 minutes later, for a loss of about $40 after fees. That's several weeks of wins gone in one trade.
- **The tools had limits.** An AI session couldn't watch the market all day without running out of memory, and Python code can't read the connector's answers directly.
- **One process slip.** An order-*preview* tool was called once by mistake. It can't place orders, but the plan forbade it, so it was added to the blocked list with a test that keeps it there.

**Lesson:** a cheap test on real data before building saves the cost of building the wrong thing.

## Nov 17: plan v2 and the "no paid data" decision
With those findings and my own research, I rewrote the strategy as [plan v2](plan-v2.md):
- fixed times (enter 10:15, exit 3:30);
- costs counted in every number;
- skip rules for risky days;
- trend-following direction;
- an "edge gate" that only trades when the numbers clear a bar.

Historical option data costs $80–$99 a month, and I chose not to pay. So the design became a **free price test plus a daily logger**, and every report states openly what that method can't prove.

## Nov 17: building it, test-first
The price test, data checks and logger were built in 10 planned tasks. Every piece started with a failing test. Then a fresh reviewer read the whole build and found real problems, including one **critical** one: the skip rules weren't applied to the logged real prices, so the comparison would have flattered the strategy. Each fix also started with a failing test.

Data checks caught problems a casual backtest would have missed:
- Robinhood's 5-minute price history is only real from March 2026. Older bars are filler, so the test uses the day's open and close instead and reports how far off those stand-ins are.
- 3 VIX days held impossible values (for example 76 when the real value was 22). A cross-check against **Cboe's own published history** compared 1,244 days: 1,238 matched, and 6 were wrong or shifted. Those 6 are now excluded automatically. ([history notes](history-notes.md))

**Lesson:** check the data against a second source. Bad data looks just like good data until you compare.

## Nov 17–18: the logger meets real life
- **A labeling slip, caught.** In a hand-made test run, put strikes were labeled one dollar off. A new check (does the strike match Robinhood's break-even price?) caught it and now runs on every file.
- **It worked, but cost too much.** The first scheduled run passed every check but used about 38,000 output tokens, mostly because the AI retyped about 47 KB of prices. I asked for that cost to come down first.
- **Cost cut by about 5×.** The run now asks for about 150 contracts at once. An answer that large is saved to a file automatically, so nothing is retyped, and a tested helper builds the record from that file. The next run used about 6,800 output tokens in 5 steps instead of 14.
- **A checker bug found on live data.** The strike-label check assumed Robinhood's break-even is based on the ask price. Real data showed Robinhood uses its adjusted midpoint instead. The two only differ on in-the-money options, which is why earlier tests missed it. Fixed test-first, and the real files were re-checked.
- **A judgment call.** Dropping the in-the-money contracts would have been easy, but on a losing day the trade's short leg *is* in the money at 3:30, and that's the price the report needs. So they stay, and only their empty greek fields are allowed.

([logger notes](logger-notes.md))

**Lesson:** "it passed" isn't the end. Measure the cost, and read the real output, not just the green tick.

## What I'd tell someone starting a project like this
1. **Write the rules down before the code.** The AI built exactly what the written plan said, so the plan had to be right.
2. **Make safety mechanical.** "Don't place orders" lives in rules, permissions, a test and a runbook, not just in a prompt.
3. **Ask "how would we know if this is wrong?"** That question found the bad VIX days, the mislabeled strikes and the checker bug.
4. **Be honest about limits.** A report that admits what it can't show is worth more than one that looks certain.
