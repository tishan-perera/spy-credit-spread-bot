# History data notes

Downloaded 2026-11-17 from Robinhood (read-only tools), saved unchanged under `data/history/` (git-ignored).

| File | Range | Bars |
|---|---|---|
| spy_day_2021-12-01_2026-11-16.json | 2021-12-01 to 2026-11-16 | 1245 daily |
| vix_day_2021-12-01_2024-05-31.json, vix_day_2024-06-01_2026-11-16.json | same | daily (index) |
| spy_5min_*.json (4 files) | 2026-03-02 to 2026-11-16 | 5-minute |

History starts 2021-12-01 so the 20-day trend rule has data on the first scored day (2022-01-03).
Robinhood intraday bars before about March 2026 come back as `interpolated` filler (seen for 2026-01-06, 2026-02-02 and all of 2025), so real 10:15 / 3:30 prices exist only from 2026-03-02.

## `check-history` result (20 problems)

Every remaining line is explained below.

- **Known bad VIX bars, excluded** (listed in `spybot/reference/bad_bars.json`; those days count as missing):
  2023-01-09 (VIX shown as ~76, real ~22), 2023-11-02 (~84, real ~16), 2025-05-07 (~14, real ~23).
- **VIX 2026-10-22: missing.** Robinhood returns a filler bar. The day is left out.
- **VIX close-to-close jumps over 25%** on the other dates are real market moves (for example 2024-08-05, 2024-12-18, 2025-04-03/04/09). The 25% rule is a prompt to look, not proof of bad data.
- No problems in SPY daily bars. No filler in the intraday files.

## Cross-check against Cboe (done 2026-11-17, owner approved)

Cboe's free VIX history (`https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv`, which redirects to `cdn-api.cboe.com`; 474,910 bytes) is saved at `data/cboe/VIX_History.csv` (git-ignored).

- **1,244 Robinhood VIX days compared; 1,238 match Cboe within $0.05 on both open and close.**
- **6 differ, in a pattern:** next to each junk bar, Robinhood also has the real values on the wrong day.

| Day | Robinhood open/close | Cboe open/close | What happened |
|---|---|---|---|
| 2023-01-06 | 21.75 / 21.97 | 22.69 / 21.13 | holds 2023-01-09's real values |
| 2023-01-09 | 75.87 / 77.27 | 21.75 / 21.97 | junk |
| 2023-11-01 | 16.59 / 15.66 | 18.02 / 16.87 | holds 2023-11-02's real values |
| 2023-11-02 | 83.91 / 83.24 | 16.59 / 15.66 | junk |
| 2025-05-07 | 14.05 / 14.02 | 24.56 / 23.55 | junk |
| 2026-10-21 | 18.29 / 19.03 | 17.25 / 16.68 | likely 2026-10-22's values (Robinhood has no 10-22 bar) |

- Every Cboe date that Robinhood lacks is a stock-market holiday, except 2026-10-22.
- **Now automatic:** whenever `data/cboe/VIX_History.csv` is present, every VIX day that differs from Cboe by more than $0.05 is left out of the price test and listed by `check-history`. Refresh the Cboe file whenever the history is refreshed.
- Excluded days count as missing. Using Cboe's values for them instead would add 6 days back; that would change the design's data source, so it is left for the owner to decide.
