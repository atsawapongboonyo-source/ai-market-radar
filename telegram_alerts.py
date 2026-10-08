"""
Telegram ENTRY SIGNAL notifier for AI Market Radar.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
import urllib.request

_LOCK = threading.Lock()
_LAST_SENT = {}
_COOLDOWN_SECONDS = 15 * 60


def telegram_configured():
    return bool(os.getenv("TELEGRAM_BOT_TOKEN")) and bool(os.getenv("TELEGRAM_CHAT_ID"))


def _dedupe_key(ticker, entry):
    try:
        rounded = round(float(entry), 2)
    except Exception:
        rounded = str(entry)
    return f"{str(ticker or '').upper()}:{rounded}"


def _should_send(key, now=None):
    now = time.time() if now is None else float(now)
    with _LOCK:
        last = _LAST_SENT.get(key)
        if last is not None and now - last < _COOLDOWN_SECONDS:
            return False
        _LAST_SENT[key] = now
        stale = [k for k, ts in _LAST_SENT.items() if now - ts > 6 * 3600]
        for k in stale:
            _LAST_SENT.pop(k, None)
        return True


def build_entry_message(payload):
    ticker = str(payload.get("ticker") or "").upper()

    def money(v):
        try:
            return chr(36) + f"{float(v):,.2f}"
        except Exception:
            return "—"

    lines = [
        "🟢 AI RADAR — ENTRY SIGNAL",
        ticker or "—",
        f"Entry: {money(payload.get('entry'))}",
        f"Buy Zone: {money(payload.get('buy_low'))}–{money(payload.get('buy_high'))}",
    ]
    if payload.get("score") is not None:
        lines.append(f"Decision Score: {payload.get('score')}/100")
    if payload.get("opening"):
        lines.append(f"Opening: {payload.get('opening')}")
    parts = []
    if payload.get("market"):
        parts.append(f"Market {payload.get('market')}")
    if payload.get("group"):
        parts.append(f"Group {payload.get('group')}")
    if parts:
        lines.append(" • ".join(parts))
    if payload.get("time_label"):
        lines.append(f"Time: {payload.get('time_label')}")
    lines.append("เปิด Scanner เพื่อตรวจรายละเอียดก่อนส่งคำสั่งซื้อ")
    return "\n".join(lines)


def send_entry_alert(payload, force=False):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        return {"ok": False, "configured": False, "reason": "telegram_not_configured"}

    ticker = str(payload.get("ticker") or "").upper()
    entry = payload.get("entry")
    if not ticker or entry is None:
        return {"ok": False, "configured": True, "reason": "missing_ticker_or_entry"}

    key = _dedupe_key(ticker, entry)
    if not force and not _should_send(key):
        return {"ok": True, "configured": True, "sent": False, "deduped": True}

    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": build_entry_message(payload),
        "disable_web_page_preview": "true",
    }).encode("utf-8")

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as exc:
        return {"ok": False, "configured": True, "reason": f"telegram_send_failed: {exc}"}

    if not body.get("ok"):
        return {"ok": False, "configured": True, "reason": "telegram_api_rejected"}

    return {
        "ok": True,
        "configured": True,
        "sent": True,
        "deduped": False,
        "message_id": (body.get("result") or {}).get("message_id"),
    }


def send_test_message():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return {"ok": False, "configured": False, "reason": "telegram_not_configured"}

    text = "🧪 AI RADAR — TELEGRAM TEST\nเชื่อมต่อ Telegram สำเร็จแล้ว\nระบบจะส่งเฉพาะ ENTRY SIGNAL ที่ผ่านเงื่อนไข"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "true",
    }).encode("utf-8")

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as exc:
        return {"ok": False, "configured": True, "reason": f"telegram_send_failed: {exc}"}
    return {"ok": bool(body.get("ok")), "configured": True}
