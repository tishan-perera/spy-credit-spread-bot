# Daily logger run: prompt template

Replace `HHMM` with `1000`, `1015`, `1030`, `1530` or `1540`. `DAY` is worked out by the run itself.

---

Work in the folder ~/SPY-Credit-Spread-Bot (cd there first). Read that project's CLAUDE.md and CLAUDE.local.md hard rules and follow them: this is READ-ONLY. Never call any order or order-preview tool on any server. Do not open any other trading folder. Do not edit code, settings or git.

Task: do exactly one logger run by following collector/logger-task.md, with DAY = today's date in US Eastern time (YYYY-MM-DD) and HHMM = HHMM. First check the market calendar with `.venv/bin/python -c "from datetime import date; from spybot import calendar as c; d=date.fromisoformat('DAY'); print(c.is_trading_day(d), c.has_0dte(d), c.close_time(d))"`. If today is not a trading day or has no same-day SPY expiry, write data/raw/DAY/HHMM.error.txt saying so and stop. If HHMM is 1530 or 1540 and the close is earlier than 16:00 (early-close day), write HHMM.error.txt saying "early close, afternoon run skipped" and stop. If data/raw/DAY/instruments.json does not exist and HHMM is not 1000, another run may be building it: wait 60 seconds and check again, up to 3 times, before doing step 1 yourself. The run starts about 10 minutes early on purpose (the app may delay recurring tasks by a few minutes). Start the step 2 tool calls 2 minutes before HHMM ET, never earlier than 4 minutes before it; if you are early, wait with a short sleep in Bash. If it is already more than 4 minutes past HHMM, still do the run; the check will mark it late, which is the honest record. Keep it short: as few turns as possible, no planning, no re-reading files, never retype a large tool answer that was saved to a file.

After step 5, write data/raw/DAY/HHMM.notes.txt with: run_et, number of contracts quoted, whether the get_option_quotes answer was saved to a file automatically (yes/no), whether you had to split the call, and the one-line assemble result. Only write files inside data/raw/DAY/. Finish with a 3-line summary.
