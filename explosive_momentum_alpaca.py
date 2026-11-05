"""Bounded read-only Alpaca intraday market-data adapter.

Explicit symbol allowlist, GET-only data.alpaca.markets, no redirects,
no account/order endpoints, no secrets in output. Not a full-market scanner.
"""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request
from urllib.error import HTTPError
import json
import re

from capital_rotation_alpaca import _readonly_urlopen, MarketDataError

HOST = "https://data.alpaca.markets/v2/stocks"


def _get(path, params, *, api_key, secret_key, opener=None):
    if not api_key or not secret_key:
        raise MarketDataError("MISSING_CREDENTIALS")
    req = Request(HOST + path + "?" + urlencode(params), headers={
        "APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key,
        "Accept": "application/json"}, method="GET")
    try:
        with (opener or _readonly_urlopen)(req, timeout=12) as response:
            raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raise MarketDataError("RESPONSE_TOO_LARGE")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except HTTPError as e:
        raise MarketDataError({401:"AUTHENTICATION_FAILED",403:"FEED_ACCESS_DENIED",
                               429:"RATE_LIMITED"}.get(e.code,"PROVIDER_UNAVAILABLE")) from None
    except MarketDataError:
        raise
    except Exception:
        raise MarketDataError("PROVIDER_UNAVAILABLE") from None


def fetch_intraday(symbol, *, start_utc, end_utc, api_key, secret_key,
                   feed="iex", opener=None):
    """Fetch completed 1-minute bars and latest quote for ONE symbol.

    The caller must independently verify the quote timestamp is contemporaneous
    with the evaluation time. The returned quote is NOT historical as-of data.
    """
    if not isinstance(symbol,str) or not re.fullmatch(r"[A-Z]{1,5}(?:[.-][A-Z])?",symbol):
        raise ValueError("INVALID_SYMBOL")
    if feed not in ("iex","sip"):
        raise ValueError("INVALID_FEED")
    if any(not isinstance(t,datetime) or t.tzinfo is None for t in (start_utc,end_utc)):
        raise ValueError("INVALID_TIME")
    start = start_utc.astimezone(timezone.utc)
    end = end_utc.astimezone(timezone.utc)
    if not timedelta(0) < end-start <= timedelta(hours=8):
        raise ValueError("INVALID_WINDOW")
    params = {"start":start.isoformat().replace("+00:00","Z"),
              "end":end.isoformat().replace("+00:00","Z"),
              "timeframe":"1Min","feed":feed,"adjustment":"split",
              "limit":1000,"sort":"asc"}
    payload = _get("/"+symbol+"/bars",params,api_key=api_key,secret_key=secret_key,opener=opener)
    if payload.get("next_page_token") is not None:
        raise MarketDataError("PAGINATED_RESPONSE")
    raw_bars = payload.get("bars")
    if not isinstance(raw_bars,list):
        raise MarketDataError("MISSING_BARS")
    try:
        bars = [{"timestamp_utc":b["t"],"close":b["c"],"volume":b["v"]} for b in raw_bars]
    except (KeyError,TypeError):
        raise MarketDataError("INVALID_BARS") from None
    quote = _get("/"+symbol+"/quotes/latest",{"feed":feed},
                 api_key=api_key,secret_key=secret_key,opener=opener).get("quote")
    if not isinstance(quote,dict) or any(k not in quote for k in ("bp","ap","t")):
        raise MarketDataError("MISSING_QUOTE")
    return {"symbol":symbol,"feed":feed.upper(),"bars":bars,
            "latest_quote":{"bid":quote["bp"],"ask":quote["ap"],
                            "timestamp_utc":quote["t"]},
            "coverage":"PARTIAL_IEX" if feed=="iex" else "SIP_ENTITLEMENT_REQUIRED",
            "historical_quote_asof":False}
