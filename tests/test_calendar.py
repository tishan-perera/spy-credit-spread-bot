from datetime import date, time

import pytest

from spybot import calendar


def test_holidays_and_weekends_are_not_trading_days():
    days = calendar.trading_days(date(2024, 12, 23), date(2024, 12, 27))
    assert days == [date(2024, 12, 23), date(2024, 12, 24), date(2024, 12, 26), date(2024, 12, 27)]


def test_early_close_moves_exit_to_1230():
    assert calendar.close_time(date(2024, 12, 24)) == time(13, 0)
    assert calendar.exit_time(date(2024, 12, 24)) == time(12, 30)
    assert calendar.exit_time(date(2024, 12, 23)) == time(15, 30)


def test_remaining_fraction():
    assert calendar.remaining_fraction(date(2024, 12, 23), time(10, 15)) == pytest.approx(315 / 390)
    assert calendar.remaining_fraction(date(2024, 12, 24), time(10, 15)) == pytest.approx(135 / 390)


def test_0dte_days_before_and_after_tue_thu_start():
    assert calendar.has_0dte(date(2022, 1, 3))        # Monday
    assert not calendar.has_0dte(date(2022, 1, 4))    # Tuesday, before the start
    assert calendar.has_0dte(date(2022, 11, 15))      # first Tuesday expiry
    assert calendar.has_0dte(date(2024, 1, 2))        # Tuesday, after
    assert not calendar.has_0dte(date(2024, 12, 25))  # holiday


def test_unscheduled_closure_2025_01_09():
    assert date(2025, 1, 9) not in calendar.trading_days(date(2025, 1, 8), date(2025, 1, 10))


def test_event_days_counts_per_year():
    ev = calendar.event_days()
    for year in (2022, 2023, 2024, 2025):
        days = [d for d in ev if d.year == year]
        assert sum("fomc" in ev[d] for d in days) == 8


def test_known_event_day():
    assert "fomc" in calendar.event_days()[date(2024, 9, 18)]
    assert set(calendar.event_days()[date(2022, 4, 12)]) == {"cpi"}


def test_event_days_are_trading_days():
    for d in calendar.event_days():
        assert calendar.is_trading_day(d), d
    assert date(2026, 4, 3) not in calendar.event_days()   # jobs report on Good Friday


def test_2021_christmas_observed_closure():
    # History downloads start 2021-12-01 so the 20-day trend has data on 2022-01-03.
    assert not calendar.is_trading_day(date(2021, 12, 24))


# --- which logger runs a day has (early-close days exit at 12:30 / 12:40) ---

def test_log_runs_on_a_normal_day():
    assert calendar.log_runs(date(2026, 11, 25)) == ("1000", "1015", "1030", "1530", "1540")
    assert calendar.exit_runs(date(2026, 11, 25)) == ("1530", "1540")


def test_log_runs_on_an_early_close_day():
    assert calendar.log_runs(date(2026, 11, 27)) == ("1000", "1015", "1030", "1230", "1240")
    assert calendar.exit_runs(date(2026, 12, 24)) == ("1230", "1240")


def test_no_log_runs_on_a_holiday():
    assert calendar.log_runs(date(2026, 11, 26)) == ()
    assert calendar.log_runs(date(2026, 11, 28)) == ()      # Saturday


# --- the calendar must reach far enough ahead ---

def test_calendar_knows_2027_holidays():
    assert not calendar.is_trading_day(date(2027, 1, 1))     # New Year's Day
    assert not calendar.is_trading_day(date(2027, 11, 25))   # Thanksgiving 2027
    assert calendar.close_time(date(2027, 11, 26)) == time(13, 0)


def test_calendar_covers_at_least_60_days_from_today():
    from datetime import date as d, timedelta
    assert calendar.covered_until() >= d.today() + timedelta(days=60)


def test_event_list_covers_at_least_60_days_from_today():
    from datetime import date as d, timedelta
    assert calendar.events_covered_until() >= d.today() + timedelta(days=60)
