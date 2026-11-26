from datetime import date

from spybot import config
from spybot.compare import RealRow
from spybot.pricetest import Setup
from spybot.ticket import Ticket, make_ticket

DAY = date(2026, 11, 24)
SETUP = Setup(5, 1.0, "v2")


def row(status="ok", mid=0.17, natural=0.16, skipped=(), side="call", short=730, long=735, band="20-30"):
    return RealRow(DAY, SETUP, side, short, long, status, mid if status == "ok" else None,
                   natural if status == "ok" else None, 0.08, (0.01, 0.01), None, None, band, tuple(skipped))


def test_edge_margin_is_the_owner_approved_two_cents():
    assert config.EDGE_MARGIN == 0.02


def test_trade_when_credit_clears_need_plus_margin():
    t = make_ticket(row(mid=0.17), need=0.144)
    assert isinstance(t, Ticket)
    assert (t.action, t.side, t.short, t.long, t.width) == ("trade", "call", 730, 735, 5)
    assert (t.limit, t.floor) == (0.17, 0.17)           # floor = 0.144 + 0.02 rounded up to a cent
    assert t.max_loss == 490.66                         # (5 - 0.17 + 0.0766) x 100
    assert "Sell 1 SPY" in t.text and "730/735 call" in t.text and "$0.17" in t.text


def test_skip_when_credit_below_need_plus_margin():
    t = make_ticket(row(mid=0.16), need=0.144)
    assert t.action == "skip" and "below" in t.reason and "$0.17" in t.reason


def test_skip_rules_carry_through():
    t = make_ticket(row(status="skipped", skipped=("gap down",)), need=0.144)
    assert t.action == "skip" and "gap down" in t.reason


def test_no_data_when_entry_missing():
    for status in ("no 10:15 run", "not logged"):
        assert make_ticket(row(status=status), need=0.144).action == "no data"
    assert make_ticket(None, need=0.144).action == "no data"


def test_skip_without_a_break_even_for_the_band():
    t = make_ticket(row(), need=None)
    assert t.action == "skip" and "break-even" in t.reason


def test_halt_reason_blocks_the_trade():
    t = make_ticket(row(mid=0.30), need=0.144, halted="3 losses in a row: halted until next week")
    assert t.action == "skip" and "halted" in t.reason


def test_ticket_text_never_names_an_order_tool():
    t = make_ticket(row(mid=0.30), need=0.144)
    assert "place_" not in t.text and "cancel_" not in t.text and "you place" in t.text.lower()
