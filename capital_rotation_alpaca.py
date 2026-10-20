"""Opt-in Alpaca historical daily-bar snapshot for offline rotation research.

Only GET https://data.alpaca.markets/v2/stocks/bars; never trading endpoints.
Credentials are read from process environment, never logged or serialized.
No fallback to partial/synthetic market data. A verified completed NYSE
session must be provided by the operator; the provider does not infer holidays.
"""
from datetime import date, datetime, timedelta, timezone
import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from capital_rotation_offline import SECTORS, AI_PROXIES
from capital_rotation_calendar import CalendarError, trailing_sessions, session_close

SYMBOLS = ("SPY",) + AI_PROXIES + SECTORS
HOST = "https://data.alpaca.markets/v2/stocks/bars"


class MarketDataError(Exception):
    pass


def _daily_close_snapshot(payload, *, expected_session):
    if not isinstance(payload, dict) or payload.get("next_page_token"):
        raise MarketDataError("INVALID_OR_PAGINATED_RESPONSE")
    bars = payload.get("bars")
    if not isinstance(bars, dict):
        raise MarketDataError("MISSING_BARS")
    snapshot = {"5d": {}, "20d": {}, "_observations": {}}
    try:
        required_sessions = trailing_sessions(expected_session)
    except CalendarError:
        raise MarketDataError('CALENDAR_UNAVAILABLE') from None
    reference_sessions = None
    for symbol in SYMBOLS:
        history = bars.get(symbol)
        if not isinstance(history, list):
            raise MarketDataError("MISSING_SYMBOL_DATA")
        by_date = {}
        for bar in history:
            if not isinstance(bar, dict):
                raise MarketDataError("INVALID_BAR")
            try:
                timestamp = datetime.fromisoformat(bar["t"].replace("Z", "+00:00"))
                close = float(bar["c"])
            except (ValueError, TypeError, KeyError, AttributeError):
                raise MarketDataError("INVALID_BAR") from None
            if timestamp.tzinfo is None or not (0 < close < float("inf")):
                raise MarketDataError("INVALID_BAR")
            day = timestamp.astimezone(timezone.utc).date()
            if day <= expected_session:
                if day in by_date:
                    raise MarketDataError("DUPLICATE_SESSION")
                by_date[day] = (close, timestamp)
        sessions = sorted(by_date)
        if len(sessions) < 21 or sessions[-1] != expected_session:
            raise MarketDataError("INSUFFICIENT_COMPLETED_SESSIONS")
        if reference_sessions is None:
            reference_sessions = sessions[-21:]
        elif sessions[-21:] != reference_sessions:
            raise MarketDataError("MISALIGNED_SYMBOL_SESSIONS")
        if sessions[-21:] != required_sessions:
            raise MarketDataError('MISSING_EXCHANGE_SESSIONS')
        close_now, asof = by_date[sessions[-1]]
        snapshot['_observations'][symbol] = [
            {'session': day.isoformat(), 'close': by_date[day][0],
             'bar_timestamp_utc': by_date[day][1].isoformat()}
            for day in sessions[-21:]]
        for window, offset in (("5d", 5), ("20d", 20)):
            earlier = by_date[sessions[-1 - offset]][0]
            snapshot[window][symbol] = {
                "return_pct": (close_now / earlier - 1.0) * 100,
                # Daily-bar timestamps mark the START of the NY day, not close.
                "asof_utc": session_close(expected_session).isoformat(),
                "bar_timestamp_utc": asof.isoformat(),
                "session_date": expected_session.isoformat(),
            }
    return snapshot


def fetch_alpaca_snapshot(*, expected_session, api_key, secret_key,
                          feed="iex", opener=urlopen):
    """One bounded read-only daily-bar request. Missing symbols fail closed.

    IEX is a partial-market feed; it may omit some ETFs. Never describe
    its volume/coverage as consolidated SIP data.
    """
    if not isinstance(expected_session, date) or isinstance(expected_session, datetime):
        raise ValueError("expected_session must be date")
    if feed not in ("iex", "sip"):
        raise ValueError("unsupported feed")
    if not api_key or not secret_key:
        raise MarketDataError("MISSING_CREDENTIALS")
    params = urlencode({
        "symbols": ",".join(SYMBOLS), "timeframe": "1Day",
        "start": (expected_session - timedelta(days=55)).isoformat(),
        "end": (expected_session + timedelta(days=1)).isoformat(),
        "adjustment": "split", "feed": feed, "limit": 10000,
        "sort": "asc",
    })
    request = Request(HOST + "?" + params, headers={
        "APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key,
        "Accept": "application/json",
    }, method="GET")
    try:
        with opener(request, timeout=12) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise MarketDataError("RESPONSE_TOO_LARGE")
        payload = json.loads(raw)
    except MarketDataError:
        raise
    except HTTPError as exc:
        # Only a fixed classification is exposed; never response bodies/headers.
        reason = {401: "AUTHENTICATION_FAILED", 403: "FEED_ACCESS_DENIED",
                  429: "RATE_LIMITED"}.get(exc.code, "PROVIDER_UNAVAILABLE")
        raise MarketDataError(reason) from None
    except Exception:
        # Never leak exception text (HTTP errors may contain provider metadata).
        raise MarketDataError("PROVIDER_UNAVAILABLE") from None
    return _daily_close_snapshot(payload, expected_session=expected_session)


def fetch_from_environment(*, expected_session, feed="iex"):
    return fetch_alpaca_snapshot(
        expected_session=expected_session,
        api_key=os.environ.get("ALPACA_DATA_KEY_ID"),
        secret_key=os.environ.get("ALPACA_DATA_SECRET_KEY"),
        feed=feed,
    )
