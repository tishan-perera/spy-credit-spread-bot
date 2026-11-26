from datetime import datetime
from zoneinfo import ZoneInfo

from spybot import alerts

ET = ZoneInfo("America/New_York")


def status(action="trade", day="2026-12-01"):
    return {"paper": {"today": {"date": day, "action": action, "spread": "Put 700/695",
                                "text": "Sell 1 SPY 700/695 put credit spread ...", "limit": 0.17}}}


def at(h, m):
    return datetime(2026, 12, 1, h, m, tzinfo=ET)


def test_ticket_alert_once_when_a_trade_ticket_appears():
    due = alerts.due(status(), at(10, 20), sent=set())
    assert [k for k, _, _ in due] == ["2026-12-01:ticket"]
    assert "700/695" in due[0][2]
    assert alerts.due(status(), at(10, 21), sent={"2026-12-01:ticket"}) == []


def test_close_reminder_between_325_and_345():
    sent = {"2026-12-01:ticket"}
    assert alerts.due(status(), at(15, 24), sent) == []
    due = alerts.due(status(), at(15, 25), sent)
    assert [k for k, _, _ in due] == ["2026-12-01:close"] and "3:30" in due[0][2]
    assert alerts.due(status(), at(15, 46), sent) == []


def test_no_alerts_for_skip_days_or_other_days():
    assert alerts.due(status("skip"), at(10, 20), set()) == []
    assert alerts.due(status(day="2026-11-30"), at(15, 30), set()) == []
    assert alerts.due({"paper": {"today": None}}, at(10, 20), set()) == []


def test_sent_keys_persist(tmp_path):
    path = tmp_path / "data" / "paper" / "notified.json"
    alerts.save_sent(path, {"2026-12-01:ticket"})
    assert alerts.load_sent(path) == {"2026-12-01:ticket"}
    assert alerts.load_sent(tmp_path / "missing.json") == set()


def test_step_sends_due_alerts_and_remembers_only_successes(tmp_path):
    shown = []
    sent_path = tmp_path / "notified.json"
    alerts.step(status(), at(15, 30), sent_path, send=lambda t, m: shown.append(t) or False)
    assert shown == ["SPY paper ticket", "SPY close reminder"] and alerts.load_sent(sent_path) == set()
    alerts.step(status(), at(15, 30), sent_path, send=lambda t, m: True)
    assert alerts.load_sent(sent_path) == {"2026-12-01:ticket", "2026-12-01:close"}


def test_close_reminder_follows_early_close_days():
    t = {"paper": {"today": {"date": "2026-11-27", "action": "trade", "spread": "Put 700/695",
                             "text": "x", "limit": 0.17}}}
    fri = lambda h, m: datetime(2026, 11, 27, h, m, tzinfo=ET)       # 1 PM close: exit 12:30
    sent = {"2026-11-27:ticket"}
    assert [k for k, _, _ in alerts.due(t, fri(12, 25), sent)] == ["2026-11-27:close"]
    assert "12:30" in alerts.due(t, fri(12, 25), sent)[0][2]
    assert alerts.due(t, fri(15, 25), sent) == []
