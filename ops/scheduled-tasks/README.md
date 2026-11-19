# Scheduled logger runs

Each logger run is a scheduled task in the Claude desktop app (Scheduled section). It follows [collector/logger-task.md](../../collector/logger-task.md), using read-only tools.

| Time (US Eastern) | Label | Notes |
|---|---|---|
| 10:00 | `1000` | First run of the day: also lists the day's contracts (`instruments.json`) |
| 10:15 | `1015` | The entry-time snapshot the price test compares against |
| 10:30 | `1030` | |
| 15:30 | `1530` | Exit-time snapshot |
| 15:40 | `1540` | Fallback exit snapshot |

Status (2026-11-18): only one-time **test** runs have been made so far. The five daily runs wait for the owner's approval. Their prompt is [daily-logger.md](daily-logger.md).

How to create one:
1. Claude app → Scheduled → new task (or ask a session to create it).
2. Paste the prompt from `daily-logger.md` and replace `HHMM` with the label above.
3. Schedule: weekdays, a few minutes before the label time (the first run of the day needs about 3 minutes to list contracts). Cron times are in the computer's **local** time zone, so convert from Eastern.
4. The Mac must be awake with the Claude app open. A run that starts more than 5 minutes from its label is marked bad by design.

Test runs so far, with their results, are in [docs/logger-notes.md](../../docs/logger-notes.md).
