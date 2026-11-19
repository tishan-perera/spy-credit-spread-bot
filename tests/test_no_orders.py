"""Guard: project code and runbooks must never name an order tool.

Robinhood approvals are OFF on the account, so any order tool executes a real
trade. The only allowed mention is inside the runbook's marked
"Forbidden tools" section.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = ("place_", "cancel_", "exercise_option", "decline_trade_approval")
START, END = "<!-- forbidden-start -->", "<!-- forbidden-end -->"


def _checked_files():
    yield from sorted((ROOT / "spybot").rglob("*.py"))
    yield from sorted((ROOT / "collector").glob("*.md"))


def _lines_outside_forbidden_section(text):
    inside = False
    for number, line in enumerate(text.splitlines(), start=1):
        if START in line:
            inside = True
            continue
        if END in line:
            inside = False
            continue
        if not inside:
            yield number, line


def test_source_never_references_order_tools():
    hits = []
    for path in _checked_files():
        for number, line in _lines_outside_forbidden_section(path.read_text()):
            for word in FORBIDDEN:
                if word in line:
                    hits.append(f"{path.relative_to(ROOT)}:{number}: {word}")
    assert hits == [], "order tool names found:\n" + "\n".join(hits)


# Order-preview tools cannot place orders, but the plan forbids them and they
# were once called by mistake (Nov 17), so project settings must block them.
PREVIEW_TOOLS = ("review_option_order", "review_equity_order",
                 "review_advanced_order", "preview_crypto_order")
SERVERS = ("mcp__robinhood__", "mcp__54da6bf0-5ad5-4b1a-b2c8-3eb2d921e7d1__")


def test_project_settings_block_order_preview_tools():
    import json
    deny = set(json.loads((ROOT / ".claude" / "settings.json").read_text())["permissions"]["deny"])
    missing = [s + t for s in SERVERS for t in PREVIEW_TOOLS if s + t not in deny]
    assert missing == [], "preview tools not blocked:\n" + "\n".join(missing)
