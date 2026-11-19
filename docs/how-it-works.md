# How it works, in plain words

Words in *italics* are explained in the [glossary](glossary.md).

## 1. The strategy (from [plan v2](plan-v2.md))

Each trading day at about 10:15 AM Eastern:

1. **Check the skip rules.** No trade on Fed decision days, CPI (inflation report) days, jobs-report days, or when SPY opens more than 1% below yesterday's close.
2. **Check the trend.** If yesterday's close is more than 0.5% above its 20-day average, the trend is *up*, so sell a *put spread* (a bet SPY won't fall far). If it's more than 0.5% below, the trend is *down*, so sell a *call spread*. In between, skip the day.
3. **Pick the strikes.** The *VIX* tells us how much SPY usually moves in a day. The short strike goes about one *expected move* away from the price, and the protective strike goes $2, $5 or $10 further out (the *width*).
4. **Close at 3:30 PM**, before the market's last half hour. Never hold to the close.

Every cost counts: about $0.16 in fees per round trip, plus *slippage*. Pass or fail is judged on the cautious slippage figure (about $0.055 per share on entry and $0.02 on exit).

## 2. The price test (the backtest)

Historical option prices aren't free, but historical **SPY and VIX prices** are. So for every trading day from 2022 onward, the price test:

1. takes that morning's SPY price and VIX;
2. places the strikes by the rule above;
3. checks where SPY actually was at 3:30 PM and works out what the spread would have cost to close;
4. averages that over hundreds of days and adds the costs.

The result is the **break-even credit**: the payment a setup must collect on average just to break even. It tests 144 setups: 3 rule versions × 3 widths × 16 strike distances.

To stay honest:
- Data is split into **training** (2022–23), **validation** (2024) and a **sealed test** period (2025–26). The sealed period can only be opened with a separate `final` command that logs every use, so the settings can't be tuned to it by accident.
- VIX prices are cross-checked against Cboe's own published history. Days that disagree are left out.
- Only information available at 10:15 that morning is used, with no peeking at later prices. Automated tests check this.

## 3. The logger (real prices, collected daily)

The backtest knows what each setup **needs** to collect. The logger records what the market actually **pays**.

At 10:00, 10:15, 10:30, 3:30 and 3:40 each trading day, a scheduled Claude session:

1. reads SPY, VIX and about 150 same-day option prices (bid, ask, midpoint, *delta*, volume…) from Robinhood, using read-only tools;
2. saves Robinhood's answer exactly as received;
3. runs a checker (`python -m spybot assemble`) that rejects anything doubtful: wrong expiry date, missing fields, a strike label that doesn't match the price, quotes more than 60 seconds old, or a run more than 5 minutes off schedule. Rejected runs are kept and marked bad, never quietly fixed.

## 4. The report

`python -m spybot report` combines the two halves. For each setup it shows the break-even credit next to the average real credit seen in the logs, grouped by how nervous the market was (VIX band), and gives a verdict. For example: *"Needs $0.13 a spread after cautious costs; real 10:15 credits averaged $0.11 over 23 logged days → does not pay."*

## The parts of the code

| File | What it does |
|---|---|
| `spybot/config.py` | Every setting in one place: times, widths, costs, skip rules |
| `spybot/calendar.py` | Trading days, early closes, same-day expiry days, Fed/CPI/jobs days |
| `spybot/history.py` | Loads and checks the price history; cross-checks VIX against Cboe |
| `spybot/pricetest.py` | Scores one day and sweeps all 144 setups |
| `spybot/ingest.py` | Checks each logger run and saves a clean snapshot |
| `spybot/compare.py` | Applies the same strike rule to the real logged prices |
| `spybot/report.py` | Writes the plain-English report and a CSV file |
| `spybot/dashboard.py` | A local status page |
| `collector/logger-task.md` | The step-by-step instructions each logger run follows |
| `tests/` | 100+ automated tests, including the two safety tests |
