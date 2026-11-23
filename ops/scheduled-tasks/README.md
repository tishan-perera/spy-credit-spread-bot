# Scheduled logger runs

Each logger run is a scheduled task in the Claude desktop app (Scheduled section). It follows [collector/logger-task.md](../../collector/logger-task.md), using read-only tools.

| Time (US Eastern) | Label | Notes |
|---|---|---|
| 10:00 | `1000` | First run of the day: also lists the day's contracts (`instruments.json`) |
| 10:15 | `1015` | The entry-time snapshot the price test compares against |
| 10:30 | `1030` | |
| 15:30 | `1530` | Exit-time snapshot |
| 15:40 | `1540` | Fallback exit snapshot |

Status (2026-11-23): the five daily runs are scheduled (owner approved 2026-11-23), weekdays, task IDs `spy-logger-1000` … `spy-logger-1540`, saved in Auto mode, no completion notifications (results show on the dashboard). Their prompt is [daily-logger.md](daily-logger.md).

The app adds a fixed per-task delay to recurring tasks (seen: 2 to 13 minutes), so the cron times were set so each run actually starts 8 to 10 minutes before its label: 9:50, 10:05, 10:22, 15:22 and 15:30 ET. Each run waits until 2 minutes before its label for the quotes. Holidays are skipped and early-close days skip the afternoon runs, using `spybot.calendar`.

How to create one:
1. Claude app → Scheduled → new task (or ask a session to create it).
2. Paste the prompt from `daily-logger.md` and replace `HHMM` with the label above.
3. Schedule: weekdays, a few minutes before the label time (the first run of the day needs about 3 minutes to list contracts). Cron times are in the computer's **local** time zone, so convert from Eastern.
4. The Mac must be awake with the Claude app open. A run that starts more than 5 minutes from its label is marked bad by design.

Test runs so far, with their results, are in [docs/logger-notes.md](../../docs/logger-notes.md).
