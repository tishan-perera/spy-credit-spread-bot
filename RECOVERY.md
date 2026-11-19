# Rebuilding the bot on a new computer

A checklist for rebuilding everything from this repo if the original Mac is lost. It takes about an hour, plus waiting for the first logger run. Steps marked **(you)** need the owner, because they involve signing in. A Claude session can do the rest if you ask it to "follow RECOVERY.md".

What is **not** in this repo (on purpose) and how it comes back:

| Missing piece | Why it's not here | How it comes back |
|---|---|---|
| `CLAUDE.local.md`, `.private-patterns` | Private (account digits) | Step 4, from the example file |
| `data/history/`, `data/cboe/` | Market data, large, re-downloadable | Step 6 |
| `data/raw/`, `data/snapshots/` (logged quotes) | Collected live each day | Lost with the computer; logging restarts at step 8. Back these folders up separately if they matter |
| Scheduled tasks | Live in the Claude app | Step 8, from `ops/scheduled-tasks/` |
| Robinhood connector login | A login, never written down | Step 3 **(you)** |

## 1. Install the tools
- **Claude desktop app**, signed in to your Claude account **(you)**. Use the Code tab.
- **Python 3.9 or newer.** On a Mac, `python3 --version` checks it; installing Apple's Command Line Tools (`xcode-select --install`) provides it.
- **git** and the **GitHub CLI** (`gh`), then `gh auth login` **(you)**.

## 2. Get the code and check it
```bash
git clone https://github.com/tishan-perera/spy-credit-spread-bot.git ~/SPY-Credit-Spread-Bot
```
```bash
cd ~/SPY-Credit-Spread-Bot && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
```
```bash
.venv/bin/python -m pytest -q
```
Every test should pass, except one dashboard test that is skipped until the price history is downloaded in step 6 ("no local price history"). The tests use small saved samples in `tests/fixtures/`, so they need no market data and no internet.

## 3. Connect Robinhood and lock out order tools **(you, then Claude)**
1. In the Claude app, add the **Robinhood** connector and sign in to Robinhood yourself. Never paste a password into a chat.
2. Install the **superpowers** plugin from the Claude plugin marketplace. It's needed only for building new features, not for running the bot.
3. Open a Claude session in `~/SPY-Credit-Spread-Bot`. Ask it to list the Robinhood tools it can see, then follow "Connector names change on a new computer" in [ops/claude-setup.md](ops/claude-setup.md):
   - update `.claude/settings.json` and `tests/test_no_orders.py` for every server name;
   - run `.venv/bin/python -m pytest -q tests/test_no_orders.py`.
4. **Do not continue until that test passes.** Robinhood's "approve trades" setting is off on the account, so an unblocked order tool could trade for real.

## 4. Restore the private files
```bash
cp CLAUDE.local.example.md CLAUDE.local.md
```
- Fill in the account's last four digits in `CLAUDE.local.md`.
- Create `.private-patterns` with the same digits on one line (plus any other private strings).
- Run the tests again. `test_public_safety.py` now also blocks those strings from ever being committed.

## 5. Read the rules
Read `CLAUDE.md` (the hard rules), [docs/plan-v2.md](docs/plan-v2.md) (the strategy) and the design in `docs/superpowers/specs/`. Any Claude session reads `CLAUDE.md` and `CLAUDE.local.md` automatically.

## 6. Download the price history again
Ask a Claude session to do this using **read-only** Robinhood tools, saving each answer **unchanged** as JSON in `data/history/`:

| File name pattern | Tool and settings | Range |
|---|---|---|
| `spy_day_<start>_<end>.json` | `get_equity_historicals`, SPY, daily bars | 2021-12-01 to the last full trading day |
| `vix_day_<start>_<end>.json` | `get_index_historicals`, VIX, daily bars (at most 4 years per call, so use 2 files) | same |
| `spy_5min_<start>_<end>.json` | `get_equity_historicals`, SPY, 5-minute bars (at most 5,000 bars per call, so split the range) | 2026-03-02 onwards. Older intraday bars are filler |

Then get Cboe's free VIX history, used to cross-check Robinhood's VIX:
```bash
mkdir -p data/cboe && curl -L -o data/cboe/VIX_History.csv https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv
```
What the files should look like, and which problems are expected, is in [docs/history-notes.md](docs/history-notes.md).

## 7. Check the data and rebuild the report
```bash
.venv/bin/python -m spybot check-history
```
```bash
.venv/bin/python -m spybot report
```
- `check-history` lists data problems. The expected ones are explained in `docs/history-notes.md`.
- `report` writes `reports/backtest-<today>.md`. Its numbers for 2022–2024 should match the committed report closely.
- Don't run `final`. It opens the sealed 2025–26 test period, and every run is logged.

## 8. Restart logging
- Make one test run first. Create a one-time scheduled task from [ops/scheduled-tasks/daily-logger.md](ops/scheduled-tasks/daily-logger.md) with label `1015`, set for about 10:11 Eastern on a trading day.
- Check its output: `data/raw/<day>/1015.notes.txt` should end with `ok`, and `data/snapshots/<day>/1015.json` should exist.
- Then create the five daily runs listed in [ops/scheduled-tasks/README.md](ops/scheduled-tasks/README.md) **(you approve)**.
- The Mac has to be awake with the Claude app open at those times.

## 9. Optional: the dashboard
```bash
.venv/bin/python -m spybot dashboard
```
This shows the project's status page at http://127.0.0.1:8790.

## Final checklist
- [ ] All tests pass, including `test_no_orders` and `test_public_safety`
- [ ] Order tools are denied for every Robinhood server name
- [ ] `CLAUDE.local.md` and `.private-patterns` exist and are git-ignored (`git status` doesn't show them)
- [ ] `check-history` shows only the expected problems; `report` runs
- [ ] One test logger run ended with `ok`
- [ ] Daily runs created after the owner's approval
