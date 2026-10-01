import time

from focus_queue import _candidate_keys
from multi_radar import _load_config, _series
from multi_radar_research import (
    _build_signal_history,
    _download_research,
    _forward_return,
    _stats,
)
from theme_stock_leaders import _rank_stocks, _stock_snapshot

_CACHE = {"ts": 0.0, "sessions": None, "payload": None}
_CACHE_TTL = 30 * 60


def _historical_stock_leader(data, config, theme_key, end, cache=None):
    cache_key = (theme_key, str(end))
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    theme = config["themes"].get(theme_key)
    if not theme:
        return None
    rows = []
    for ticker in theme["members"]:
        item = _stock_snapshot(
            data,
            ticker,
            config["benchmark"],
            theme["proxy"],
            end=end,
        )
        if item:
            rows.append(item)
    if len(rows) < 3:
        if cache is not None:
            cache[cache_key] = None
        return None

    ranked = _rank_stocks(rows)
    if not ranked:
        if cache is not None:
            cache[cache_key] = None
        return None
    best = ranked[0]
    result = {
        "ticker": best["ticker"],
        "leader_score": best["leader_score"],
        "confirmation_count": best["confirmation_count"],
        "confirmation_total": best["confirmation_total"],
        "qualified": int(best["confirmation_count"]) >= 4,
        "state": best["state"],
    }
    if cache is not None:
        cache[cache_key] = result
    return result


def _forward_excess(data, ticker, benchmark, end, horizon):
    s = _series(data, ticker, "Close").dropna()
    b = _series(data, benchmark, "Close").dropna()
    if end not in s.index or end not in b.index:
        return None
    sp = int(s.index.get_loc(end))
    bp = int(b.index.get_loc(end))
    sr = _forward_return(s, sp, horizon)
    br = _forward_return(b, bp, horizon)
    if sr is None or br is None:
        return None
    return {
        "return_pct": round(sr, 2),
        "benchmark_return_pct": round(br, 2),
        "excess_pct": round(sr - br, 2),
    }


def _robust_stats(values, cap=10.0):
    vals = sorted(float(x) for x in values if x is not None)
    if not vals:
        return {
            "n": 0,
            "trimmed_avg": None,
            "capped_avg": None,
            "winsorized_median": None,
        }

    n = len(vals)
    trim = 1 if n >= 8 else 0
    trimmed = vals[trim:n - trim] if n - trim > trim else vals
    capped = [max(-cap, min(cap, x)) for x in vals]
    mid = len(capped) // 2
    median = capped[mid] if len(capped) % 2 else (capped[mid - 1] + capped[mid]) / 2.0
    return {
        "n": n,
        "trimmed_avg": round(sum(trimmed) / len(trimmed), 2),
        "capped_avg": round(sum(capped) / len(capped), 2),
        "winsorized_median": round(median, 2),
    }


def _summarize_records(records):
    result = {}
    for priority in (1, 2, 3):
        rows = [x for x in records if x["priority"] == priority]
        qualified = [x for x in rows if x.get("stock_qualified")]
        result[str(priority)] = {
            "n": len(rows),
            "theme_vs_qqq": _stats([x["theme_excess_pct"] for x in rows]),
            "stock_vs_qqq": _stats([
                x["stock_excess_pct"] for x in rows if x.get("stock_excess_pct") is not None
            ]),
            "stock_vs_theme": _stats([
                x["stock_vs_theme_pct"] for x in rows if x.get("stock_vs_theme_pct") is not None
            ]),
            "qualified_stock_vs_qqq": _stats([
                x["stock_excess_pct"] for x in qualified if x.get("stock_excess_pct") is not None
            ]),
            "qualified_n": len(qualified),
        }
    return result


def _summarize_focus_types(records):
    result = {}
    focus_types = sorted({x["focus_type"] for x in records})
    for focus_type in focus_types:
        rows = [x for x in records if x["focus_type"] == focus_type]
        result[focus_type] = {
            "n": len(rows),
            "theme_vs_qqq": _stats([x["theme_excess_pct"] for x in rows]),
            "stock_vs_qqq": _stats([
                x["stock_excess_pct"] for x in rows if x.get("stock_excess_pct") is not None
            ]),
            "stock_vs_theme": _stats([
                x["stock_vs_theme_pct"] for x in rows if x.get("stock_vs_theme_pct") is not None
            ]),
        }
    return result


def _winner_stats(records):
    by_date = {}
    for row in records:
        by_date.setdefault(row["date"], []).append(row)

    theme_wins = {1: 0, 2: 0, 3: 0}
    stock_wins = {1: 0, 2: 0, 3: 0}
    theme_windows = 0
    stock_windows = 0

    for rows in by_date.values():
        eligible_theme = [x for x in rows if x.get("theme_excess_pct") is not None]
        if len(eligible_theme) >= 2:
            best = max(eligible_theme, key=lambda x: x["theme_excess_pct"])
            theme_wins[best["priority"]] += 1
            theme_windows += 1

        eligible_stock = [x for x in rows if x.get("stock_excess_pct") is not None]
        if len(eligible_stock) >= 2:
            best = max(eligible_stock, key=lambda x: x["stock_excess_pct"])
            stock_wins[best["priority"]] += 1
            stock_windows += 1

    return {
        "theme": {
            "windows": theme_windows,
            "win_pct": {
                str(k): round(v / theme_windows * 100.0, 1) if theme_windows else None
                for k, v in theme_wins.items()
            },
        },
        "stock": {
            "windows": stock_windows,
            "win_pct": {
                str(k): round(v / stock_windows * 100.0, 1) if stock_windows else None
                for k, v in stock_wins.items()
            },
        },
    }


def _secondary_reorder_research(records):
    by_date = {}
    for row in records:
        if row["priority"] in {2, 3}:
            by_date.setdefault(row["date"], []).append(row)

    samples = []
    for date, rows in by_date.items():
        p2 = next((x for x in rows if x["priority"] == 2), None)
        p3 = next((x for x in rows if x["priority"] == 3), None)
        if not p2 or not p3:
            continue

        quality_pick = max(
            (p2, p3),
            key=lambda x: (
                1 if x.get("stock_qualified") else 0,
                float(x.get("stock_score") or -1),
                -int(x.get("theme_rank") or 99),
            ),
        )
        rank_pick = min((p2, p3), key=lambda x: int(x.get("theme_rank") or 99))

        samples.append({
            "date": date,
            "actual_p2_stock_excess": p2.get("stock_excess_pct"),
            "actual_p2_theme_excess": p2.get("theme_excess_pct"),
            "quality_pick_priority": quality_pick["priority"],
            "quality_pick_stock_excess": quality_pick.get("stock_excess_pct"),
            "quality_pick_theme_excess": quality_pick.get("theme_excess_pct"),
            "rank_pick_priority": rank_pick["priority"],
            "rank_pick_stock_excess": rank_pick.get("stock_excess_pct"),
            "rank_pick_theme_excess": rank_pick.get("theme_excess_pct"),
        })

    return {
        "n": len(samples),
        "actual_p2_stock": _stats([
            x["actual_p2_stock_excess"] for x in samples
            if x["actual_p2_stock_excess"] is not None
        ]),
        "quality_pick_stock": _stats([
            x["quality_pick_stock_excess"] for x in samples
            if x["quality_pick_stock_excess"] is not None
        ]),
        "rank_pick_stock": _stats([
            x["rank_pick_stock_excess"] for x in samples
            if x["rank_pick_stock_excess"] is not None
        ]),
        "actual_p2_theme": _stats([x["actual_p2_theme_excess"] for x in samples]),
        "quality_pick_theme": _stats([x["quality_pick_theme_excess"] for x in samples]),
        "rank_pick_theme": _stats([x["rank_pick_theme_excess"] for x in samples]),
        "quality_selected_p3_pct": round(
            sum(1 for x in samples if x["quality_pick_priority"] == 3)
            / len(samples) * 100.0, 1
        ) if samples else None,
        "rank_selected_p3_pct": round(
            sum(1 for x in samples if x["rank_pick_priority"] == 3)
            / len(samples) * 100.0, 1
        ) if samples else None,
    }


def _rotation_quality_research(records):
    rotation = [x for x in records if x.get("focus_type") == "ROTATION_WATCH"]

    def pack(rows):
        return {
            "n": len(rows),
            "theme_vs_qqq": _stats([
                x["theme_excess_pct"] for x in rows
                if x.get("theme_excess_pct") is not None
            ]),
            "stock_vs_qqq": _stats([
                x["stock_excess_pct"] for x in rows
                if x.get("stock_excess_pct") is not None
            ]),
            "stock_vs_theme": _stats([
                x["stock_vs_theme_pct"] for x in rows
                if x.get("stock_vs_theme_pct") is not None
            ]),
            "stock_robust": _robust_stats([
                x["stock_excess_pct"] for x in rows
                if x.get("stock_excess_pct") is not None
            ]),
        }

    dual = [
        x for x in rotation
        if int(x.get("theme_confirmation") or 0) >= 4
        and bool(x.get("stock_qualified"))
    ]
    top3_dual = [
        x for x in dual
        if int(x.get("theme_rank") or 99) <= 3
    ]
    strong_5d = [
        x for x in top3_dual
        if float(x.get("theme_score_change_5d") or 0) >= 8.0
    ]
    early_only = [
        x for x in top3_dual
        if x.get("theme_state") == "EARLY_ROTATION"
    ]
    accel_only = [
        x for x in top3_dual
        if x.get("theme_state") == "ACCELERATING"
    ]

    return {
        "all": pack(rotation),
        "dual_confirmed": pack(dual),
        "top3_dual": pack(top3_dual),
        "top3_dual_strong5d": pack(strong_5d),
        "top3_dual_early": pack(early_only),
        "top3_dual_accelerating": pack(accel_only),
    }


def _candidate_forward_record(data, config, theme_row, end, horizon, strategy, leader_cache):
    key = theme_row["key"]
    theme = config["themes"].get(key)
    if not theme:
        return None

    theme_forward = _forward_excess(data, theme["proxy"], config["benchmark"], end, horizon)
    if not theme_forward:
        return None

    stock = _historical_stock_leader(
        data, config, key, end, cache=leader_cache
    )
    stock_forward = None
    if stock:
        stock_forward = _forward_excess(
            data, stock["ticker"], config["benchmark"], end, horizon
        )

    return {
        "date": end.strftime("%Y-%m-%d"),
        "strategy": strategy,
        "theme_key": key,
        "theme_rank": theme_row.get("rank"),
        "theme_state": theme_row.get("state"),
        "theme_confirmation": theme_row.get("rotation_confirmation_count"),
        "theme_score_change_5d": theme_row.get("score_change_5d"),
        "theme_rank_change_5d": theme_row.get("rank_change_5d"),
        "theme_excess_pct": theme_forward["excess_pct"],
        "stock_ticker": stock.get("ticker") if stock else None,
        "stock_qualified": stock.get("qualified") if stock else False,
        "stock_excess_pct": stock_forward["excess_pct"] if stock_forward else None,
    }


def _slot2_strategy_research(data, config, snapshots, horizon, leader_cache):
    records = []
    for snap in snapshots[::horizon]:
        themes = sorted(snap["themes"], key=lambda x: x.get("rank", 99))
        if len(themes) < 2:
            continue
        end = snap["date"]
        leader_key = themes[0]["key"]

        next_ranked = next((x for x in themes if x["key"] != leader_key), None)
        rotation = [
            x for x in themes
            if x["key"] != leader_key
            and x.get("state") in {"EARLY_ROTATION", "ACCELERATING"}
        ]
        rotation.sort(key=lambda x: (x.get("rank", 99), -float(x.get("score_change_5d") or 0)))
        rotation_pick = rotation[0] if rotation else None

        if next_ranked:
            item = _candidate_forward_record(
                data, config, next_ranked, end, horizon, "NEXT_RANKED", leader_cache
            )
            if item:
                records.append(item)
        if rotation_pick:
            item = _candidate_forward_record(
                data, config, rotation_pick, end, horizon, "ROTATION_WATCH", leader_cache
            )
            if item:
                records.append(item)

    result = {}
    for strategy in ("NEXT_RANKED", "ROTATION_WATCH"):
        rows = [x for x in records if x["strategy"] == strategy]
        result[strategy] = {
            "n": len(rows),
            "theme_vs_qqq": _stats([x["theme_excess_pct"] for x in rows]),
            "stock_vs_qqq": _stats([
                x["stock_excess_pct"] for x in rows if x.get("stock_excess_pct") is not None
            ]),
            "qualified_stock_vs_qqq": _stats([
                x["stock_excess_pct"] for x in rows
                if x.get("stock_excess_pct") is not None and x.get("stock_qualified")
            ]),
        }

    paired_dates = sorted({
        x["date"] for x in records if x["strategy"] == "ROTATION_WATCH"
    })
    paired = []
    for date in paired_dates:
        nr = next((x for x in records if x["date"] == date and x["strategy"] == "NEXT_RANKED"), None)
        rw = next((x for x in records if x["date"] == date and x["strategy"] == "ROTATION_WATCH"), None)
        if not nr or not rw:
            continue
        if nr["theme_key"] == rw["theme_key"]:
            continue
        paired.append({
            "date": date,
            "next_ranked_theme": nr["theme_key"],
            "rotation_theme": rw["theme_key"],
            "next_ranked_stock": nr.get("stock_ticker"),
            "rotation_stock": rw.get("stock_ticker"),
            "next_ranked_stock_qualified": nr.get("stock_qualified"),
            "rotation_stock_qualified": rw.get("stock_qualified"),
            "next_ranked_theme_excess_pct": nr["theme_excess_pct"],
            "rotation_theme_excess_pct": rw["theme_excess_pct"],
            "next_ranked_stock_excess_pct": nr.get("stock_excess_pct"),
            "rotation_stock_excess_pct": rw.get("stock_excess_pct"),
            "theme_diff_rotation_minus_ranked": round(
                rw["theme_excess_pct"] - nr["theme_excess_pct"], 2
            ),
            "stock_diff_rotation_minus_ranked": (
                round(rw["stock_excess_pct"] - nr["stock_excess_pct"], 2)
                if rw.get("stock_excess_pct") is not None and nr.get("stock_excess_pct") is not None
                else None
            ),
        })

    result["paired"] = {
        "n": len(paired),
        "records": paired[-40:],
        "theme_rotation_minus_ranked": _stats([
            x["theme_diff_rotation_minus_ranked"] for x in paired
        ]),
        "stock_rotation_minus_ranked": _stats([
            x["stock_diff_rotation_minus_ranked"] for x in paired
            if x["stock_diff_rotation_minus_ranked"] is not None
        ]),
        "theme_robust": _robust_stats([
            x["theme_diff_rotation_minus_ranked"] for x in paired
        ]),
        "stock_robust": _robust_stats([
            x["stock_diff_rotation_minus_ranked"] for x in paired
            if x["stock_diff_rotation_minus_ranked"] is not None
        ]),
    }
    return result


def build_focus_queue_research(force=False, sessions=220):
    now = time.time()
    if (
        not force
        and _CACHE["payload"]
        and _CACHE["sessions"] == sessions
        and now - _CACHE["ts"] < _CACHE_TTL
    ):
        payload = dict(_CACHE["payload"])
        payload["cached"] = True
        return payload

    config = _load_config()
    data_period = "5y" if sessions > 440 else ("2y" if sessions > 220 else "1y")
    data = _download_research(config, period=data_period)
    benchmark = config["benchmark"]
    snapshots = _build_signal_history(data, config, sessions=sessions)
    leader_cache = {}

    results = {}
    for horizon in (3, 5):
        records = []
        # Non-overlapping forward windows reduce repeated-outcome dependence.
        for snap in snapshots[::horizon]:
            end = snap["date"]
            radar = {"themes": snap["themes"]}
            slots = _candidate_keys(radar)
            if not slots:
                continue
            theme_map = {x["key"]: x for x in snap["themes"]}

            for priority, slot in enumerate(slots, start=1):
                key = slot["key"]
                theme = config["themes"].get(key)
                theme_row = theme_map.get(key)
                if not theme or not theme_row:
                    continue
                theme_forward = _forward_excess(
                    data, theme["proxy"], benchmark, end, horizon
                )
                if not theme_forward:
                    continue

                stock = _historical_stock_leader(
                    data, config, key, end, cache=leader_cache
                )
                stock_forward = None
                stock_vs_theme = None
                if stock:
                    stock_forward = _forward_excess(
                        data, stock["ticker"], benchmark, end, horizon
                    )
                    if stock_forward:
                        stock_vs_theme = round(
                            stock_forward["return_pct"] - theme_forward["return_pct"], 2
                        )

                records.append({
                    "date": end.strftime("%Y-%m-%d"),
                    "horizon": horizon,
                    "priority": priority,
                    "focus_type": slot["focus_type"],
                    "theme_key": key,
                    "theme_label": theme["label"],
                    "theme_rank": theme_row.get("rank"),
                    "theme_state": theme_row.get("state"),
                    "theme_score": theme_row.get("score"),
                    "theme_confirmation": theme_row.get("rotation_confirmation_count"),
                    "theme_score_change_5d": theme_row.get("score_change_5d"),
                    "theme_rank_change_5d": theme_row.get("rank_change_5d"),
                    "theme_excess_pct": theme_forward["excess_pct"],
                    "stock_ticker": stock.get("ticker") if stock else None,
                    "stock_score": stock.get("leader_score") if stock else None,
                    "stock_confirmation": stock.get("confirmation_count") if stock else None,
                    "stock_qualified": stock.get("qualified") if stock else False,
                    "stock_excess_pct": stock_forward["excess_pct"] if stock_forward else None,
                    "stock_vs_theme_pct": stock_vs_theme,
                })

        results[str(horizon)] = {
            "by_priority": _summarize_records(records),
            "by_focus_type": _summarize_focus_types(records),
            "winner_stats": _winner_stats(records),
            "rotation_quality": _rotation_quality_research(records),
            "secondary_reorder": _secondary_reorder_research(records),
            "slot2_strategy": _slot2_strategy_research(
                data, config, snapshots, horizon, leader_cache
            ),
            "records": records[-180:],
        }
    payload = {
        "version": "5.1-focus-research",
        "sessions_requested": sessions,
        "data_period": data_period,
        "results": results,
        "cached": False,
        "note": (
            "Research-only replay of Focus Queue using historical Multi-Radar states "
            "and the same Stock Leader ranking logic. Results are diagnostic only and "
            "do not modify live Focus Queue weights."
        ),
        "limitations": [
            "Current-universe / survivorship bias is possible.",
            "Historical Yahoo data can contain gaps or adjustments.",
            "Non-overlapping windows reduce but do not eliminate dependence.",
            "This is attention-ranking validation, not a trading backtest with entries, slippage or exits.",
        ],
    }
    _CACHE["ts"], _CACHE["sessions"], _CACHE["payload"] = now, sessions, payload
    return payload
