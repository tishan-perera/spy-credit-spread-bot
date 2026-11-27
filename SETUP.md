# SETUP: rebuild this system on a new Mac

## For the owner: the only thing you do to start

1. Install the **Claude desktop app** and sign in. Open the **Code** tab and start a new session (any folder is fine).
2. Paste this message:

```text
Set up my SPY bot on this computer from https://github.com/tishan-perera/spy-credit-spread-bot. Clone it and follow SETUP.md in that repo exactly, step by step.
```

Claude does the rest and stops when it needs you. You will be asked to:
- click "Install" if macOS offers developer tools;
- type the account's last four digits into a private file;
- sign in to Robinhood;
- approve the edit that blocks order tools;
- approve the scheduled runs.

It takes about an hour. If anything is interrupted, open a Claude session in `~/SPY-Credit-Spread-Bot` and say "continue SETUP.md". Progress is saved in `data/setup-progress.md`.

---

## For Claude Code: instructions

You are rebuilding a read-only SPY options research system for a non-technical owner (accounting background). Explain each step in one or two plain sentences, show evidence (command output) for every check, and stop and ask whenever something doesn't match what this file expects.

### Rules for the whole setup
1. **Never place, change, cancel or preview an order.** Robinhood's "approve trades" setting is off on the account, so an order tool would trade for real. Never call any tool whose name contains `place_`, `cancel_`, `exercise_option`, `decline_trade_approval`, `review_` + `order` or `preview_crypto_order`, on any server.
2. **Call no Robinhood tool at all until step 8.** Only from step 8 on, and only read tools.
3. **Never read, copy or touch `~/MGC-Trading-Agent`** or any other trading folder. This project is separate.
4. **The owner does every sign-in and types every private value.** Never ask them to paste a password, code or account number into the chat.
5. **Ask before creating scheduled tasks or background services** (steps 5 and 10), even though this file describes them.
6. **Keep a progress log.** After each step, add one line to `data/setup-progress.md` (git-ignored): the step number, done or skipped, and the evidence in one line. When resuming, read it first and continue at the first step not marked done.
7. **Don't push to GitHub** and don't change any rule, threshold or design file. If something seems to need that, stop and ask.
8. Once the repo is cloned, read `CLAUDE.md`. Its hard rules apply on top of this file.

### Step 1. Check the computer
Run and report:
```bash
sw_vers -productVersion; python3 --version; git --version; date "+%Z %z"; ls -d ~/SPY-Credit-Spread-Bot 2>/dev/null
```
- `python3` or `git` missing: run `xcode-select --install` and ask the owner to click Install, then check again. Python must be 3.9 or newer.
- `~/SPY-Credit-Spread-Bot` already exists: stop and ask the owner whether to resume (read `data/setup-progress.md`) or move the old folder aside. Never delete it.
- Note the time zone. The scheduled times in step 10 are Eastern, and you'll convert them to this zone.

### Step 2. Get the code and prove it works
```bash
git clone https://github.com/tishan-perera/spy-credit-spread-bot.git ~/SPY-Credit-Spread-Bot
```
```bash
cd ~/SPY-Credit-Spread-Bot && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
```
```bash
cd ~/SPY-Credit-Spread-Bot && .venv/bin/python -m pytest -q
```
**Expected:** every test passes. One dashboard test may be skipped with "no local price history"; that's fine until step 9. Any failure: stop and show the owner the failing test names. Then create `data/setup-progress.md` and record steps 1–2.

### Step 3. Private files (owner types the digits)
```bash
cd ~/SPY-Credit-Spread-Bot && cp CLAUDE.local.example.md CLAUDE.local.md && touch .private-patterns
```
- Open both files for the owner, using the app's open-in-editor tool if available, or `open -e <file>`. Ask them to type the Robinhood "MCP" account's last four digits:
  - in `CLAUDE.local.md`, where it shows `____`;
  - alone on the first line of `.private-patterns`.
- Then check both files are git-ignored and run the leak guard:
```bash
cd ~/SPY-Credit-Spread-Bot && git check-ignore CLAUDE.local.md .private-patterns && .venv/bin/python -m pytest -q tests/test_public_safety.py
```
**Expected:** both file names are printed, and the tests pass.

### Step 4. Restore the backed-up data
The old Mac's background watcher copied the logged quotes and price history to iCloud Drive every 15 minutes.
```bash
B="$HOME/Library/Mobile Documents/com~apple~CloudDocs/SPY-bot-backup"; ls "$B" 2>/dev/null && du -sh "$B"/* 2>/dev/null
```
- **Found:** copy it in. This only adds files and never deletes:
  ```bash
  B="$HOME/Library/Mobile Documents/com~apple~CloudDocs/SPY-bot-backup"; mkdir -p ~/SPY-Credit-Spread-Bot/data && rsync -a "$B"/ ~/SPY-Credit-Spread-Bot/data/
  ```
  Then report how many logged days came back: `ls ~/SPY-Credit-Spread-Bot/data/snapshots | wc -l`.
- **Not found:** iCloud may still be downloading, so ask the owner to check Finder → iCloud Drive → `SPY-bot-backup`. If there's truly no backup, say plainly that the logged option prices from the old Mac are lost (they can't be downloaded again) and continue. Price history comes back in step 9.

### Step 5. Background services (ask first)
Two services keep running outside Claude:
- the **dashboard** at http://127.0.0.1:8790;
- the **watcher**: every 15 minutes it sends a Mac notification for missed or failed runs, and copies `data/` to iCloud Drive.

After the owner says yes:
```bash
cd ~/SPY-Credit-Spread-Bot && sh ops/dashboard-service.sh install && sh ops/watch-service.sh install
```
```bash
cd ~/SPY-Credit-Spread-Bot && sh ops/dashboard-service.sh status; sh ops/watch-service.sh status
```
**Expected:** both show `state = active`. If the sandbox hides them ("Not installed"), run the status commands outside the sandbox. Ask the owner to allow notifications from "Script Editor" / Terminal if macOS asks.

### Step 6. Gate: continue only in a session inside the project folder
The order-tool blocks (`.claude/settings.json`) apply **only to sessions whose working folder is `~/SPY-Credit-Spread-Bot`.** If this session started anywhere else, stop here:
- record steps 1–5 in `data/setup-progress.md`;
- tell the owner: "Please start a new Claude Code session with the folder `~/SPY-Credit-Spread-Bot`, switch it to Auto permission mode (so the scheduled runs can be saved to run unattended), and say: continue SETUP.md."

If this session already runs in that folder, go on.

### Step 7. Connect Robinhood and block every order tool
1. **Add the connector.** Check `claude mcp list`. If `robinhood` is missing:
   ```bash
   claude mcp add --transport http --scope user robinhood https://agent.robinhood.com/mcp/trading
   ```
   The owner then signs in to Robinhood when the app asks, or in a Terminal: run `claude`, type `/mcp`, choose robinhood, then Authenticate. The Robinhood connector may also be switched on for the owner's Claude account. Its tools then show up a second time under an ID such as `mcp__54da6bf0-…__`.
2. **Find every server name.** Search your tools (for example ToolSearch for "robinhood option quotes") and list every distinct prefix `mcp__<server>__` that offers Robinhood tools.
3. **Block them all.** `.claude/settings.json` already denies the order and preview tools for `mcp__robinhood__` and `mcp__54da6bf0-5ad5-4b1a-b2c8-3eb2d921e7d1__`. For each **new** prefix:
   - copy one existing block of 15 deny lines and change only the prefix;
   - add the prefix to `SERVERS` in `tests/test_no_orders.py`.

   The app asks the owner to approve the settings edit. Explain that it *removes* power, so it's safe.
4. **Prove it:**
   ```bash
   cd ~/SPY-Credit-Spread-Bot && .venv/bin/python -m pytest -q tests/test_no_orders.py
   ```
   **Do not continue until this passes.** If you changed `.claude/settings.json`, ask the owner to start a fresh session in the project folder and say "continue SETUP.md". That guarantees the new blocks are loaded before any Robinhood call.
5. If you changed tracked files, commit them locally (`git commit -am "ops: block order tools for this computer's connector names"`). Pushing is the owner's choice.

### Step 8. First read-only call
Call `get_equity_quotes` with symbols `["SPY"]`, and nothing else. **Expected:** a price. That proves the connector works. Never call `get_accounts`, `get_portfolio` or any order-related tool during setup.

### Step 9. Price history
1. Work out what's needed:
   ```bash
   cd ~/SPY-Credit-Spread-Bot && ls data/history 2>/dev/null; .venv/bin/python -m spybot check-history | tail -5
   ```
2. **History restored in step 4:** run the daily refresh once, exactly as [ops/scheduled-tasks/history-refresh.md](ops/scheduled-tasks/history-refresh.md) describes. Follow the prompt below its `---` line yourself. It brings the files up to date and refreshes the Cboe file.
3. **No history at all:** download from scratch with read-only tools. Each answer is saved to a file automatically; never retype one. Pass the saved file to `save-history`.

   | Kind | Tool call | Range |
   |---|---|---|
   | `spy_day` | `get_equity_historicals`, symbols `["SPY"]`, interval `day` | 2021-12-01 to tomorrow |
   | `vix_day` | `get_index_historicals`, instrument_ids `["3b912aa2-88f9-4682-8ae3-e39520bdf4db"]`, interval `day` | two calls, 2021-12-01 → 2024-05-31 and 2024-06-01 → tomorrow (at most 4 years each) |
   | `spy_5min` | `get_equity_historicals`, symbols `["SPY"]`, interval `5minute` | 2026-03-02 to tomorrow, split into ranges of at most 5,000 bars (about 2.5 months each). Older intraday bars are filler |

   ```bash
   cd ~/SPY-Credit-Spread-Bot && .venv/bin/python -m spybot save-history <kind> <saved file> [<saved file>...]
   ```
   Then get the Cboe VIX file:
   ```bash
   mkdir -p ~/SPY-Credit-Spread-Bot/data/cboe && curl -sSfL -o ~/SPY-Credit-Spread-Bot/data/cboe/VIX_History.csv https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv
   ```
4. Check and rebuild:
   ```bash
   cd ~/SPY-Credit-Spread-Bot && .venv/bin/python -m spybot check-history; .venv/bin/python -m spybot report; .venv/bin/python -m pytest -q
   ```
   **Expected:**
   - `check-history` shows only the problems explained in [docs/history-notes.md](docs/history-notes.md).
   - `report` writes `reports/backtest-<today>.md`.
   - All tests pass with no skips.
   - **Never run `python -m spybot final`.** It opens the sealed test period.

### Step 10. Scheduled runs (show the owner this table, then ask)
These are Claude app scheduled tasks. Create them only after the owner says yes, from a session in **Auto** permission mode (otherwise each run stops to ask for permission). Turn notifications on completion off; the dashboard and push alerts report problems.

| Task ID | Title | Prompt | Repeats | Should **start** at (Eastern) |
|---|---|---|---|---|
| `spy-logger-1000` | SPY logger 10:00 ET (weekdays) | daily-logger, `HHMM = 1000` | weekdays | 9:50 |
| `spy-logger-1015` | SPY logger 10:15 ET (weekdays) | daily-logger, `HHMM = 1015` | weekdays | 10:05 |
| `spy-logger-1030` | SPY logger 10:30 ET (weekdays) | daily-logger, `HHMM = 1030` | weekdays | 10:22 |
| `spy-logger-1530` | SPY logger 3:30 PM ET (weekdays) | daily-logger, `HHMM = 1530` | weekdays | 15:22 |
| `spy-logger-1540` | SPY logger 3:40 PM ET (weekdays) | daily-logger, `HHMM = 1540` | weekdays | 15:30 |
| `spy-history-refresh` | SPY price history refresh (weekdays after close) | history-refresh | weekdays | about 16:25 |
| `spy-logger-1230-<date>` | SPY logger 12:30 ET exit (early close, <date>) | daily-logger, `HHMM = 1230` | once | 12:22 on that date |
| `spy-logger-1240-<date>` | SPY logger 12:40 ET fallback exit (early close, <date>) | daily-logger, `HHMM = 1240` | once | 12:30 on that date |

How to fill each one in:
- **Prompt:** take the text below the `---` line of [ops/scheduled-tasks/daily-logger.md](ops/scheduled-tasks/daily-logger.md) and change only `HHMM = HHMM` to `HHMM = 1015` (etc.). Leave every other `HHMM` as it is; the run fills those in itself. For the history task, use the text below the `---` line of [ops/scheduled-tasks/history-refresh.md](ops/scheduled-tasks/history-refresh.md) unchanged.
- **Times:** cron times are in this Mac's **local** zone (from step 1), so convert from Eastern. For example, Central time is one hour earlier.
- **Recurring tasks start late on purpose.** The app adds a fixed delay to each recurring task (seen: 1 to 13 minutes). Create the task with cron = start time minus 5 minutes. Then call list_scheduled_tasks, read its `jitterSeconds`, and update the cron so that cron + jitter is 8 to 10 minutes before the label (within a minute of the start time in the table). One-time tasks have no delay: use the table time exactly.
- **Early-close days:** list them with
  ```bash
  cd ~/SPY-Credit-Spread-Bot && .venv/bin/python -c "from datetime import date, timedelta as t; from spybot import calendar as c; d=date.today(); print([str(x) for x in c.trading_days(d+t(days=1), min(d+t(days=365), c.covered_until())) if c.exit_runs(x)[0]!='1530' and c.log_runs(x)])"
  ```
  Make a 1230 and a 1240 one-time task for each date printed.
- After creating them, show the owner `list_scheduled_tasks`, with each task's next start time in Eastern.

### Step 11. Final check, then report
```bash
cd ~/SPY-Credit-Spread-Bot && .venv/bin/python -m pytest -q && .venv/bin/python -m spybot health; git status --short
```
Tell the owner, in plain words, with evidence for each:
- [ ] all tests pass, including `test_no_orders` and `test_public_safety`
- [ ] order tools are blocked for every Robinhood server name found in step 7
- [ ] `CLAUDE.local.md` and `.private-patterns` exist and `git status` doesn't list them
- [ ] logged data restored (or plainly reported as lost), and price history is current
- [ ] the dashboard opens at http://127.0.0.1:8790 and the watcher is active
- [ ] every scheduled task is created and saved in Auto mode, with correct start times
- [ ] `spybot health` lists no problems, except runs that were due before setup finished

Remind the owner of three things:
1. The Mac must be **awake with the Claude app open** at run times. Suggest System Settings → Battery/Energy → "Prevent automatic sleeping when the display is off" on power; the choice is theirs.
2. Turn on notifications for the Claude app, so missed runs reach them.
3. Optional:
   - `gh auth login` if they want to push changes to GitHub;
   - the **superpowers** plugin (Claude plugin marketplace), only needed for building new features.

Record step 11 in `data/setup-progress.md`. Setup is finished.

---

*More background: [README.md](README.md) (what this is), [ops/claude-setup.md](ops/claude-setup.md) (how the pieces fit and the safety net), [ops/scheduled-tasks/README.md](ops/scheduled-tasks/README.md) (the schedule's history and timing notes).*
