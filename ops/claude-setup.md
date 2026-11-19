# Claude setup for this project

The bot's "agents" are Claude Code sessions. This page lists everything outside the code that has to exist on a computer for them to work. The step-by-step rebuild is in [RECOVERY.md](../RECOVERY.md).

## What runs where

| Piece | What it is | Where it lives |
|---|---|---|
| Claude desktop app (Code tab) | Runs Claude Code sessions and the scheduled logger runs | Installed app, signed in to the owner's Claude account |
| Robinhood connector (MCP server) | The only way market data reaches the project. Claude calls its read tools (quotes, option chains, price history) and saves the answers as files | Added in the Claude app's connector settings; the owner signs in to Robinhood themselves |
| superpowers plugin | Working method used to build the project: brainstorm → design → plan → test-first build → review | Claude plugin marketplace |
| Project rules | `CLAUDE.md` (published) and `CLAUDE.local.md` (private, git-ignored) | This repo |
| Project permissions | `.claude/settings.json`: blocks every order tool | This repo |
| Scheduled logger runs | One-time or daily Claude tasks that follow `collector/logger-task.md` | Claude app → Scheduled; prompts kept in [scheduled-tasks/](scheduled-tasks/) |

Code never talks to Robinhood directly. A Claude session calls the read tools, writes the answer to `data/raw/`, and plain Python (`spybot`) checks and scores it.

## The no-orders safety net (four layers)

Robinhood's "approve trades" setting is off on the account, so any order tool would trade for real. Nothing in this project may place, change or cancel an order.

1. **Rules.** `CLAUDE.md` forbids order tools, and every scheduled prompt repeats it.
2. **Permissions.** `.claude/settings.json` denies every `place_*`, `cancel_*`, `exercise_option`, `decline_trade_approval` and order-preview tool, on each name the Robinhood connector has on this computer.
3. **Guard test.** `tests/test_no_orders.py` fails if any code or runbook names an order tool, or if the settings stop blocking the preview tools.
4. **Read-only runbook.** `collector/logger-task.md` lists the five read tools it may use, and nothing else.

### Connector names change on a new computer
A connector's tools are named `mcp__<server name>__<tool>`. The server name can be a readable name (`robinhood`) or an ID (for example `mcp__54da6bf0-…__`). On a new computer, list the Robinhood tools a session can see. Then, for **every** server name found:
- add its order and preview tools to `deny` in `.claude/settings.json` (copy the existing block and change the prefix);
- add the prefix to `SERVERS` in `tests/test_no_orders.py`;
- run `.venv/bin/python -m pytest -q tests/test_no_orders.py`, which must pass.

## Privacy rules for the public repo
- Account numbers, balances, emails and tokens never go into tracked files. `tests/test_public_safety.py` checks every tracked file on each test run.
- Private details go in `CLAUDE.local.md` (copy from `CLAUDE.local.example.md`).
- Private strings to block go one per line in `.private-patterns`. Both files are git-ignored.
- Market data (`data/`) is git-ignored. It can be downloaded again (see RECOVERY.md).
