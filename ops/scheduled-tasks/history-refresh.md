# Daily history refresh: prompt template

Scheduled task `spy-history-refresh`, weekdays after the close (cron `25 15 * * 1-5` local Central time, so with the app's delay it starts about 16:25-16:40 ET). It keeps the SPY and VIX price history current, so logged days count in the report. Read-only.

---

Work in the folder ~/SPY-Credit-Spread-Bot (cd there first). Read that project's CLAUDE.md and CLAUDE.local.md hard rules and follow them: this is READ-ONLY. Never call any order or order-preview tool on any server. Do not open any other trading folder. Do not edit code, settings or git.

Task: refresh the price history once. First run `.venv/bin/python -c "from datetime import date, timedelta as t; from spybot import calendar as c; d=date.today(); print(c.is_trading_day(d), date(d.year-2,1,1), (d.replace(day=1)-t(days=1)).replace(day=1), d+t(days=1))"`. It prints: trading day (True/False), DAILY_START, INTRADAY_START, END. If the first value is False, stop without writing anything.

In one turn, call: `get_equity_historicals` with symbols ["SPY"], interval "day", start_time DAILY_START, end_time END; `get_index_historicals` with instrument_ids ["3b912aa2-88f9-4682-8ae3-e39520bdf4db"] (VIX), interval "day", start_time DAILY_START, end_time END; and `get_equity_historicals` with symbols ["SPY"], interval "5minute", start_time INTRADAY_START, end_time END. Each answer is large and is saved to a file automatically; never retype an answer. If any answer comes back inline instead of as a saved file, do not save it: write data/raw/TODAY/history.error.txt (TODAY = today's date) saying which one, and skip it.

Then run `.venv/bin/python -m spybot save-history spy_day <SPY day file>`, `.venv/bin/python -m spybot save-history vix_day <VIX file>` and `.venv/bin/python -m spybot save-history spy_5min <SPY 5-minute file>`. Then refresh the Cboe VIX file: `curl -sSfL -o data/cboe/VIX_History.csv.new https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv && mv data/cboe/VIX_History.csv.new data/cboe/VIX_History.csv` (if it fails, say so and go on). Then run `.venv/bin/python -m spybot health`. If any save-history line starts with "BAD", or health prints a line about price history, send one push notification (PushNotification tool) starting "SPY bot: history refresh problem:" (under 200 characters). Only write inside data/. Finish with a 3-line summary.
