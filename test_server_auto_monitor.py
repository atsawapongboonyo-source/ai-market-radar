from datetime import datetime
from zoneinfo import ZoneInfo

from server_auto_monitor import _market_window


ET = ZoneInfo("America/New_York")


def et(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=ET)


def test_weekend_is_closed():
    assert _market_window(et(2026, 10, 10, 10, 0)) == "CLOSED_WEEKEND"


def test_premarket_before_open():
    assert _market_window(et(2026, 10, 8, 8, 0)) == "PREMARKET"


def test_opening_range_is_fail_closed():
    assert _market_window(et(2026, 10, 8, 9, 40)) == "OPENING_RANGE"


def test_rth_monitor_starts_after_15_minutes():
    assert _market_window(et(2026, 10, 8, 9, 45)) == "RTH_MONITOR"


def test_after_close():
    assert _market_window(et(2026, 10, 8, 16, 1)) == "AFTER_CLOSE"
