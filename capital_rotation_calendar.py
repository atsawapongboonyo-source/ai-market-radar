"""Bounded NYSE core-session calendar for local research, reviewed 2026-10-20.

Source: https://www.nyse.com/trade/hours-calendars (2026-2028 table).
This pinned calendar cannot discover unscheduled closures. Unknown years fail
closed; refresh the source before extending coverage. No network or broker API.
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SOURCE = 'https://www.nyse.com/trade/hours-calendars'
REVIEWED = '2026-10-20'
HOLIDAYS = {
    2026: '01-01 01-19 02-16 04-03 05-25 06-19 07-03 09-07 11-26 12-25',
    2027: '01-01 01-18 02-15 03-26 05-31 06-18 07-05 09-06 11-25 12-24',
    2028: '01-17 02-21 04-14 05-29 06-19 07-04 09-04 11-23 12-25',
}
EARLY_CLOSES = {date(2026, 11, 27), date(2026, 12, 24),
                date(2027, 11, 26), date(2028, 7, 3), date(2028, 11, 24)}


class CalendarError(ValueError):
    pass


def ny_timezone():
    try:
        return ZoneInfo('America/New_York')
    except ZoneInfoNotFoundError:
        raise CalendarError('TIMEZONE_DATA_UNAVAILABLE') from None


def is_session(day):
    if not isinstance(day, date) or isinstance(day, datetime) or day.year not in HOLIDAYS:
        raise CalendarError('UNSUPPORTED_CALENDAR_DATE')
    return day.weekday() < 5 and day.strftime('%m-%d') not in HOLIDAYS[day.year].split()


def session_close(day):
    if not is_session(day):
        raise CalendarError('NOT_EXCHANGE_SESSION')
    hour = 13 if day in EARLY_CLOSES else 16
    return datetime.combine(day, time(hour), ny_timezone()).astimezone(timezone.utc)


def last_completed_session(now_utc):
    """Wait 20 minutes after core close for this delayed historical pilot.

    This is a readiness buffer, not a guarantee the provider finalized its bar.
    Provider completeness checks still apply.
    """
    if not isinstance(now_utc, datetime) or now_utc.tzinfo is None:
        raise CalendarError('INVALID_NOW')
    day = now_utc.astimezone(ny_timezone()).date()
    for _ in range(10):
        if is_session(day) and now_utc >= session_close(day) + timedelta(minutes=20):
            return day
        day -= timedelta(days=1)
    raise CalendarError('NO_COMPLETED_SESSION')


def trailing_sessions(end, count=21):
    if not is_session(end):
        raise CalendarError('NOT_EXCHANGE_SESSION')
    days = []
    day = end
    while len(days) < count:
        if is_session(day):
            days.append(day)
        day -= timedelta(days=1)
    return list(reversed(days))


def calendar_age_limit(session, now_utc):
    """Closure allowance anchored to verified close, never an older session."""
    if session != last_completed_session(now_utc):
        raise CalendarError('NOT_LATEST_COMPLETED_SESSION')
    age = (now_utc - session_close(session)).total_seconds() / 3600
    if not 0 <= age <= 119:
        raise CalendarError('UNSUPPORTED_CLOSURE_GAP')
    return max(36, age + 1)
