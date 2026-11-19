# Daily logger run: prompt template

Replace `HHMM` with `1000`, `1015`, `1030`, `1530` or `1540`. `DAY` is worked out by the run itself.

---

Work in the folder ~/SPY-Credit-Spread-Bot (cd there first). Read that project's CLAUDE.md and CLAUDE.local.md hard rules and follow them: this is READ-ONLY. Never call any order or order-preview tool on any server. Do not open any other trading folder. Do not edit code, settings or git.

Task: do exactly one logger run by following collector/logger-task.md, with DAY = today's date in US Eastern time (YYYY-MM-DD) and HHMM = HHMM. If today is not a trading day, or has no same-day SPY expiry, write data/raw/DAY/HHMM.error.txt saying so and stop. If data/raw/DAY/instruments.json does not exist, do step 1 first. The step 2 tool calls must happen within 4 minutes of HHMM; if you are early, wait (for example with a short sleep in Bash). Keep it short: as few turns as possible, no planning, no re-reading files, never retype a large tool answer that was saved to a file.

After step 5, write data/raw/DAY/HHMM.notes.txt with: run_et, number of contracts quoted, whether the get_option_quotes answer was saved to a file automatically (yes/no), whether you had to split the call, and the one-line assemble result. Only write files inside data/raw/DAY/. Finish with a 3-line summary.
