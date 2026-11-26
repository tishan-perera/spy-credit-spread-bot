from datetime import date

from spybot import config, paper
from spybot.compare import RealRow
from spybot.pricetest import Setup

SETUP = Setup(5, 1.0, "v2")


def row(day, mid=0.17, v1530=0.0, v1540=None, status="ok", skipped=()):
    ok = status == "ok"
    return RealRow(day, SETUP, "put", 700, 695, status, mid if ok else None, (mid - 0.01) if ok else None,
                   -0.1, (0.01, 0.01), v1530 if ok else None, v1540 if ok else None, "20-30", tuple(skipped))


def day_input(day, **kw):
    close = kw.pop("close", None)
    return paper.DayIn(day=day, row=row(day, **kw), need=0.144, spy_close=close)


def test_guardrail_settings_are_the_owner_approved_values():
    assert config.LOSS_STREAK_HALT == 3
    assert config.WEEKLY_LOSS_LIMIT_MAX_LOSSES == 1


def test_win_uses_cautious_costs():
    led = paper.ledger([day_input(date(2026, 11, 24))])
    e = led[0]
    assert (e.action, e.exit_source, e.result) == ("trade", "3:30", 9.34)   # (0.17 - 0 - 0.0766) x 100


def test_full_loss_equals_minus_max_loss():
    e = paper.ledger([day_input(date(2026, 11, 24), v1530=5.0)])[0]
    assert e.result == -e.max_loss == -490.66


def test_fallback_exit_then_settlement_from_close():
    a = paper.ledger([day_input(date(2026, 11, 24), v1530=None, v1540=0.05)])[0]
    assert (a.exit_source, a.result) == ("3:40", 4.34)
    b = paper.ledger([day_input(date(2026, 11, 24), v1530=None, close=697.5)])[0]
    assert b.exit_source == "close (3:30 and 3:40 missed)" and b.result == round((0.17 - 2.5 - 0.0766) * 100, 2)
    c = paper.ledger([day_input(date(2026, 11, 24), v1530=None)])[0]
    assert (c.exit_source, c.result) == ("missing", None)


def test_skips_and_missing_entries_are_not_trades():
    led = paper.ledger([day_input(date(2026, 11, 24), mid=0.15),
                        day_input(date(2026, 11, 25), status="skipped", skipped=("gap down",))])
    assert [e.action for e in led] == ["skip", "skip"] and all(e.result is None for e in led)


def test_three_losses_in_a_row_halt_the_rest_of_the_week():
    days = [date(2026, 11, 30), date(2026, 12, 1), date(2026, 12, 2), date(2026, 12, 3), date(2026, 12, 7)]
    led = paper.ledger([day_input(d, v1530=0.2) for d in days])        # small losses each day
    assert [e.action for e in led] == ["trade", "trade", "trade", "skip", "trade"]
    assert "3 losses in a row" in led[3].reason


def test_one_max_loss_in_a_week_halts_the_week():
    days = [date(2026, 11, 30), date(2026, 12, 1), date(2026, 12, 7)]
    led = paper.ledger([day_input(days[0], v1530=5.0), day_input(days[1]), day_input(days[2])])
    assert [e.action for e in led] == ["trade", "skip", "trade"]
    assert "weekly loss limit" in led[1].reason


def test_summary_counts_paper_days_and_total():
    led = paper.ledger([day_input(date(2026, 11, 24)), day_input(date(2026, 11, 25), mid=0.15)])
    s = paper.summary(led)
    assert (s["days"], s["trades"], s["wins"], s["losses"], s["total"]) == (2, 1, 1, 0, 9.34)


def test_go_live_gate_lists_every_check_and_fails_today():
    led = paper.ledger([day_input(date(2026, 11, 24))])
    checks = paper.go_live_gate(logged_days=4, target_days=60, ledger=led, leg_gap=0.01,
                                account_rule_met=False)
    names = [c["check"] for c in checks]
    assert names == ["Logged days", "Paper-trading days", "Paper result after cautious costs",
                     "Real bid/ask gaps within the cost assumption", "Account size rule (owner)"]
    assert not paper.gate_passes(checks)
    assert [c["ok"] for c in checks] == [False, False, True, True, False]


def test_go_live_gate_passes_only_when_everything_passes():
    days = []
    d = date(2027, 1, 4)
    while len(days) < 30:
        if d.weekday() < 5:
            days.append(d)
        d = date.fromordinal(d.toordinal() + 1)
    led = paper.ledger([day_input(x) for x in days])
    checks = paper.go_live_gate(logged_days=60, target_days=60, ledger=led, leg_gap=0.01, account_rule_met=True)
    assert paper.gate_passes(checks)
    checks = paper.go_live_gate(logged_days=60, target_days=60, ledger=led, leg_gap=0.06, account_rule_met=True)
    assert not paper.gate_passes(checks)
