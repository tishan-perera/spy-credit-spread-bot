# Private details (template)

Copy this file to `CLAUDE.local.md` (git-ignored) and fill it in. Claude Code reads it together with `CLAUDE.md`.

- Robinhood account nicknamed "MCP": number ends in `____`. This is the only account the bot may read. Never touch the other account.

Also create `.private-patterns` (git-ignored) with one private string per line (for example the account's last four digits), so `tests/test_public_safety.py` can block them from ever being committed.
