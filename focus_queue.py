import time

from multi_radar import build_multi_radar
from theme_stock_leaders import build_theme_stock_leaders

_CACHE = {"ts": 0.0, "payload": None}
_CACHE_TTL = 5 * 60


def _theme_map(radar):
    return {row["key"]: row for row in radar.get("themes", [])}


def _candidate_keys(radar):
    themes = sorted(
        list(radar.get("themes", [])),
        key=lambda x: x.get("rank", 99),
    )
    if not themes:
        return []

    selected = []
    leader = themes[0]
    selected.append({
        "key": leader["key"],
        "focus_type": "CURRENT_LEADER",
        "focus_label": "Current Leader",
        "reason": "อันดับ 1 ของ Multi-Radar ตอนนี้",
    })

    next_ranked = next(
        (row for row in themes if row["key"] != leader["key"]),
        None,
    )
    if next_ranked:
        is_rotation = next_ranked.get("state") in {"EARLY_ROTATION", "ACCELERATING"}
        selected.append({
            "key": next_ranked["key"],
            "focus_type": "NEXT_RANKED",
            "focus_label": "Next Ranked Theme",
            "reason": (
                f'อันดับ {next_ranked.get("rank")} ของ Multi-Radar • '
                f'{next_ranked.get("state_label")}'
                + (" • Rotation state" if is_rotation else "")
            ),
        })

    transition = [
        row for row in themes
        if row.get("state") in {"EARLY_ROTATION", "ACCELERATING"}
        and not any(x["key"] == row["key"] for x in selected)
    ]
    transition.sort(
        key=lambda x: (
            x.get("rank", 99),
            -float(x.get("score_change_5d") or 0),
        )
    )
    if transition and len(selected) < 3:
        row = transition[0]
        selected.append({
            "key": row["key"],
            "focus_type": "ROTATION_MONITOR",
            "focus_label": "Rotation Monitor",
            "reason": (
                f'{row.get("state_label")} • 5D '
                f'{row.get("score_change_5d", 0):+.1f} • '
                f'Rank5 {row.get("rank_change_5d", 0):+d}'
            ),
        })

    for row in themes:
        if len(selected) >= 3:
            break
        if any(x["key"] == row["key"] for x in selected):
            continue
        selected.append({
            "key": row["key"],
            "focus_type": "RANK_BACKUP",
            "focus_label": "Rank Backup",
            "reason": f'อันดับ {row.get("rank")} ของ Multi-Radar • {row.get("state_label")}',
        })

    return selected[:3]


def _stock_focus(stock_payload):
    top = list(stock_payload.get("top3", []))
    if not top:
        return None
    best = top[0]
    qualified = int(best.get("confirmation_count") or 0) >= 4
    return {
        "ticker": best.get("ticker"),
        "rank": best.get("rank"),
        "leader_score": best.get("leader_score"),
        "confirmation_count": best.get("confirmation_count"),
        "confirmation_total": best.get("confirmation_total"),
        "qualified": qualified,
        "state": best.get("state"),
        "state_label": best.get("state_label"),
        "relative_proxy_5d_pct": best.get("relative_proxy_5d_pct"),
        "relative_proxy_20d_pct": best.get("relative_proxy_20d_pct"),
        "volume_ratio": best.get("volume_ratio"),
        "above_ema20": best.get("above_ema20"),
    }


def build_focus_queue(force=False):
    now = time.time()
    if not force and _CACHE["payload"] and now - _CACHE["ts"] < _CACHE_TTL:
        payload = dict(_CACHE["payload"])
        payload["cached"] = True
        return payload
    radar = build_multi_radar(force=force)
    themes = _theme_map(radar)
    slots = _candidate_keys(radar)
    queue = []

    for priority, slot in enumerate(slots, start=1):
        key = slot["key"]
        theme = themes.get(key) or {}
        stock_error = None
        try:
            stocks = build_theme_stock_leaders(key, force=force)
            stock = _stock_focus(stocks)
        except Exception as exc:
            stock = None
            stock_error = str(exc)

        if stock and stock["qualified"]:
            stock_note = "Qualified Group Leader"
        elif stock:
            stock_note = "Top relative stock • confirmation ยังไม่ครบ"
        elif stock_error:
            stock_note = "Stock Leader data unavailable"
        else:
            stock_note = "ยังไม่มี stock data"

        queue.append({
            "priority": priority,
            **slot,
            "theme_label": theme.get("label"),
            "theme_rank": theme.get("rank"),
            "theme_score": theme.get("score"),
            "theme_state": theme.get("state"),
            "theme_state_label": theme.get("state_label"),
            "theme_score_change_5d": theme.get("score_change_5d"),
            "theme_rank_change_5d": theme.get("rank_change_5d"),
            "theme_confirmation_count": theme.get("rotation_confirmation_count"),
            "theme_confirmation_total": theme.get("rotation_confirmation_total"),
            "stock": stock,
            "stock_note": stock_note,
            "stock_error": stock_error,
        })

    payload = {
        "version": "5.1-focus-queue",
        "queue": queue,
        "current_leader": radar.get("leader"),
        "rotation_summary": radar.get("rotation_summary"),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "cached": False,
        "note": (
            "Focus Queue is an attention-priority layer only. It combines Multi-Radar "
            "theme ranking with the selected theme's Stock Leader Bridge. It does not "
            "replace the existing Top Pick, Premarket, Opening or Position decision flow."
        ),
    }
    _CACHE["ts"], _CACHE["payload"] = now, payload
    return payload
