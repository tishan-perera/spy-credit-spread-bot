# SPY Credit-Spread Bot

Automated SPY credit-spread bot, built with its owner's approved design (`2026-11-16-spy-credit-spread-bot-design.md`, revision 2). Owner is a non-coder (accounting background): explain in plain words, show evidence, ask before changing the design.

## Hard rules (always)
- **Do not place, cancel or exercise any order.** Robinhood "approve trades" is OFF on the account, so any order tool executes real trades. Phase A is read-only. Never call `place_option_order`, `cancel_option_order`, `exercise_option` or any `place_*` / `cancel_*` tool.
- The only trading account is the Robinhood account nicknamed "MCP" (its last digits are in the git-ignored `CLAUDE.local.md`). Never touch the other account.
- This project is fully separate from the MGC "Manager" system. Do not read, edit or reuse anything in `~/MGC-Trading-Agent` or other trading folders.
- Never change guardrails, thresholds or the design without the owner's approval. Suggest first.
- When unsure, do nothing and ask.

## Current work
Execute `docs/superpowers/plans/2026-11-17-price-test-and-logger-plan.md` task by task (TDD, frequent commits). Backtest and logging only; no paper or live trading.

## Public repo
This repo is published on GitHub. Never commit account numbers, balances, emails or tokens; `tests/test_public_safety.py` checks every tracked file. Private details go in `CLAUDE.local.md` (git-ignored).
