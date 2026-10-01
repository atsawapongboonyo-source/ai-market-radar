import math
import time

import pandas as pd
import yfinance as yf

from multi_radar import (
    _load_config,
    _rotation_confirmation,
    _score_theme,
    _series,
    _state,
    _transition_metrics,
)

_CACHE = {"ts": 0.0, "sessions": None, "payload": None}
_CACHE_TTL = 30 * 60


def _download_research(config, period="1y"):
    symbols = {config["benchmark"]}
    for theme in config["themes"].values():
        symbols.add(theme["proxy"])
        symbols.update(theme["members"])
    data = yf.download(
        sorted(symbols),
        period=period,
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=True,
        group_by="column",
        timeout=25,
    )
    if data is None or data.empty:
        raise ValueError("Multi-Radar research data unavailable")
    return data
def _forward_return(series, end_pos, sessions):
    s = series.dropna()
    if end_pos < 0 or end_pos + sessions >= len(s):
        return None
    a = float(s.iloc[end_pos])
    b = float(s.iloc[end_pos + sessions])
    if not a or not math.isfinite(a) or not math.isfinite(b):
        return None
    return (b / a - 1.0) * 100.0


def _stats(values):
    vals = [float(x) for x in values if x is not None and math.isfinite(float(x))]
    if not vals:
        return {"n": 0, "avg": None, "median": None, "positive_pct": None}
    vals_sorted = sorted(vals)
    n = len(vals_sorted)
    mid = n // 2
    median = vals_sorted[mid] if n % 2 else (vals_sorted[mid - 1] + vals_sorted[mid]) / 2.0
    return {
        "n": n,
        "avg": round(sum(vals_sorted) / n, 2),
        "median": round(median, 2),
        "positive_pct": round(sum(1 for x in vals_sorted if x > 0) / n * 100.0, 1),
    }


def _build_signal_history(data, config, sessions=90):
    benchmark = config["benchmark"]
    bench = _series(data, benchmark, "Close").dropna()
    dates = list(bench.index[-sessions:])
    history = []
    snapshots = []
    for end in dates:
        rows = []
        for key, theme in config["themes"].items():
            scored = _score_theme(data, benchmark, theme, end=end)
            if scored:
                rows.append({"key": key, "label": theme["label"], **scored})
        rows.sort(key=lambda x: x["score"], reverse=True)
        for idx, row in enumerate(rows, start=1):
            row["rank"] = idx

        simple_ranking = [
            {"key": x["key"], "label": x["label"], "score": x["score"], "rank": x["rank"]}
            for x in rows
        ]
        history.append({
            "date": pd.Timestamp(end).strftime("%Y-%m-%d"),
            "leader": rows[0]["key"] if rows else None,
            "leader_label": rows[0]["label"] if rows else None,
            "leader_score": rows[0]["score"] if rows else None,
            "ranking": simple_ranking,
        })

        if len(history) < 6:
            continue

        enriched = []
        for row in rows:
            metrics = _transition_metrics(row["key"], history)
            item = dict(row)
            item.update(metrics)
            item.update(_rotation_confirmation(item))
            item["state"], item["state_label"] = _state(item, metrics)
            enriched.append(item)
        snapshots.append({"date": end, "themes": enriched})

    return snapshots
def _cross_sectional_research(data, config, snapshots, bench, bench_pos):
    result = {}
    for horizon in (3, 5):
        records = []
        # Use a non-overlapping stride equal to the forward horizon.
        for snap in snapshots[::horizon]:
            end = snap["date"]
            if end not in bench_pos or len(snap["themes"]) < 5:
                continue
            bp = bench_pos[end]
            br = _forward_return(bench, bp, horizon)
            if br is None:
                continue

            rows = []
            for row in sorted(snap["themes"], key=lambda x: x["rank"]):
                proxy = _series(data, row["proxy"], "Close").dropna()
                if end not in proxy.index:
                    continue
                pp = int(proxy.index.get_loc(end))
                pr = _forward_return(proxy, pp, horizon)
                if pr is None:
                    continue
                rows.append({
                    "key": row["key"],
                    "rank": row["rank"],
                    "excess": pr - br,
                })
            if len(rows) < 5:
                continue

            rows.sort(key=lambda x: x["rank"])
            top1 = rows[0]["excess"]
            bottom1 = rows[-1]["excess"]
            top2 = sum(x["excess"] for x in rows[:2]) / 2.0
            bottom2 = sum(x["excess"] for x in rows[-2:]) / 2.0
            future_sorted = sorted(rows, key=lambda x: x["excess"], reverse=True)
            leader_future_rank = next(
                i + 1 for i, x in enumerate(future_sorted) if x["key"] == rows[0]["key"]
            )
            records.append({
                "date": pd.Timestamp(end).strftime("%Y-%m-%d"),
                "top1_key": rows[0]["key"],
                "bottom1_key": rows[-1]["key"],
                "top1_excess_pct": round(top1, 2),
                "bottom1_excess_pct": round(bottom1, 2),
                "top1_minus_bottom1_pct": round(top1 - bottom1, 2),
                "top2_minus_bottom2_pct": round(top2 - bottom2, 2),
                "leader_future_rank": leader_future_rank,
                "leader_top_half": leader_future_rank <= math.ceil(len(rows) / 2),
            })

        result[str(horizon)] = {
            "top1_vs_qqq": _stats([x["top1_excess_pct"] for x in records]),
            "top1_minus_bottom1": _stats([x["top1_minus_bottom1_pct"] for x in records]),
            "top2_minus_bottom2": _stats([x["top2_minus_bottom2_pct"] for x in records]),
            "leader_top_half_pct": round(
                sum(1 for x in records if x["leader_top_half"]) / len(records) * 100.0, 1
            ) if records else None,
            "records": records[-60:],
        }
    return result


def build_rotation_research(force=False, sessions=90):
    now = time.time()
    if not force and _CACHE["payload"] and _CACHE["sessions"] == sessions and now - _CACHE["ts"] < _CACHE_TTL:
        payload = dict(_CACHE["payload"])
        payload["cached"] = True
        return payload

    config = _load_config()
    data = _download_research(config)
    benchmark = config["benchmark"]
    bench = _series(data, benchmark, "Close").dropna()
    bench_pos = {idx: i for i, idx in enumerate(bench.index)}
    snapshots = _build_signal_history(data, config, sessions=sessions)
    cross_sectional = _cross_sectional_research(data, config, snapshots, bench, bench_pos)

    events = []
    entries = []
    previous_state = {}
    last_entry_pos = {}
    cooldown_sessions = 5

    for snap in snapshots:
        end = snap["date"]
        if end not in bench_pos:
            continue
        bp = bench_pos[end]
        current_keys = set()
        for row in snap["themes"]:
            key = row["key"]
            current_keys.add(key)
            state = row["state"]
            prior = previous_state.get(key)
            previous_state[key] = state

            if state not in {"EARLY_ROTATION", "ACCELERATING"}:
                continue
            if prior == state:
                continue
            if key in last_entry_pos and bp - last_entry_pos[key] < cooldown_sessions:
                continue

            proxy = _series(data, row["proxy"], "Close").dropna()
            if end not in proxy.index:
                continue
            pp = int(proxy.index.get_loc(end))
            last_entry_pos[key] = bp
            entry = {
                "date": pd.Timestamp(end).strftime("%Y-%m-%d"),
                "key": key,
                "label": row["label"],
                "state": state,
                "score": row["score"],
                "confirmation": row.get("rotation_confirmation_count"),
            }
            entries.append(entry)

            for horizon in (3, 5):
                pr = _forward_return(proxy, pp, horizon)
                br = _forward_return(bench, bp, horizon)
                if pr is None or br is None:
                    continue
                events.append({
                    **entry,
                    "horizon": horizon,
                    "proxy_return_pct": round(pr, 2),
                    "benchmark_return_pct": round(br, 2),
                    "excess_return_pct": round(pr - br, 2),
                })

        for key in list(previous_state):
            if key not in current_keys:
                previous_state.pop(key, None)
    handoff_events = []
    previous_leader = None
    for snap in snapshots:
        if not snap["themes"]:
            continue
        leader = min(snap["themes"], key=lambda x: x["rank"])
        end = snap["date"]
        key = leader["key"]
        if previous_leader is not None and key != previous_leader and end in bench_pos:
            proxy = _series(data, leader["proxy"], "Close").dropna()
            if end in proxy.index:
                bp = bench_pos[end]
                pp = int(proxy.index.get_loc(end))
                for horizon in (3, 5):
                    pr = _forward_return(proxy, pp, horizon)
                    br = _forward_return(bench, bp, horizon)
                    if pr is None or br is None:
                        continue
                    handoff_events.append({
                        "date": pd.Timestamp(end).strftime("%Y-%m-%d"),
                        "from": previous_leader,
                        "to": key,
                        "to_label": leader["label"],
                        "score": leader["score"],
                        "confirmation": leader.get("rotation_confirmation_count"),
                        "horizon": horizon,
                        "proxy_return_pct": round(pr, 2),
                        "benchmark_return_pct": round(br, 2),
                        "excess_return_pct": round(pr - br, 2),
                    })
        previous_leader = key

    handoff_summary = {}
    for horizon in (3, 5):
        xs = [x["excess_return_pct"] for x in handoff_events if x["horizon"] == horizon]
        handoff_summary[str(horizon)] = _stats(xs)

    leader_sequence = []
    for snap in snapshots:
        if not snap["themes"]:
            continue
        leader = min(snap["themes"], key=lambda x: x["rank"])
        leader_sequence.append({"date": snap["date"], "row": leader})

    persistence_tests = {}
    for label, required_streak, strong_gate in (
        ("streak2", 2, False),
        ("streak2_strong", 2, True),
        ("streak3_strong", 3, True),
    ):
        persistent_events = []
        streak = 0
        prior_key = None
        for item in leader_sequence:
            row = item["row"]
            key = row["key"]
            streak = streak + 1 if key == prior_key else 1
            prior_key = key
            if streak != required_streak:
                continue
            if strong_gate and (
                float(row.get("score") or 0) < 12
                or int(row.get("rotation_confirmation_count") or 0) < 4
            ):
                continue
            end = item["date"]
            if end not in bench_pos:
                continue
            proxy = _series(data, row["proxy"], "Close").dropna()
            if end not in proxy.index:
                continue
            bp = bench_pos[end]
            pp = int(proxy.index.get_loc(end))
            for horizon in (3, 5):
                pr = _forward_return(proxy, pp, horizon)
                br = _forward_return(bench, bp, horizon)
                if pr is None or br is None:
                    continue
                persistent_events.append({
                    "date": pd.Timestamp(end).strftime("%Y-%m-%d"),
                    "key": key,
                    "label": row["label"],
                    "score": row["score"],
                    "confirmation": row.get("rotation_confirmation_count"),
                    "streak": required_streak,
                    "horizon": horizon,
                    "excess_return_pct": round(pr - br, 2),
                })
        persistence_tests[label] = {
            "3": _stats([x["excess_return_pct"] for x in persistent_events if x["horizon"] == 3]),
            "5": _stats([x["excess_return_pct"] for x in persistent_events if x["horizon"] == 5]),
            "events": persistent_events[-40:],
        }

    summary = {}
    for state in ("EARLY_ROTATION", "ACCELERATING"):
        summary[state] = {}
        for horizon in (3, 5):
            xs = [x["excess_return_pct"] for x in events if x["state"] == state and x["horizon"] == horizon]
            summary[state][str(horizon)] = _stats(xs)

    confirmation_split = {}
    for label, predicate in (
        ("confirmed_4plus", lambda x: int(x.get("confirmation") or 0) >= 4),
        ("low_confirmation", lambda x: int(x.get("confirmation") or 0) < 4),
    ):
        confirmation_split[label] = {}
        for horizon in (3, 5):
            xs = [
                x["excess_return_pct"] for x in events
                if x["state"] == "ACCELERATING"
                and x["horizon"] == horizon
                and predicate(x)
            ]
            confirmation_split[label][str(horizon)] = _stats(xs)

    by_theme = {}
    for key, theme in config["themes"].items():
        by_theme[key] = {"label": theme["label"]}
        for horizon in (3, 5):
            xs = [
                x["excess_return_pct"] for x in events
                if x["key"] == key and x["horizon"] == horizon
                and x["state"] in {"EARLY_ROTATION", "ACCELERATING"}
            ]
            by_theme[key][str(horizon)] = _stats(xs)

    payload = {
        "version": "5.1-research",
        "sessions_requested": sessions,
        "summary": summary,
        "cross_sectional": cross_sectional,
        "confirmation_split": confirmation_split,
        "handoff_summary": handoff_summary,
        "handoff_events": handoff_events[-80:],
        "persistence_tests": persistence_tests,
        "by_theme": by_theme,
        "entries": entries[-60:],
        "entry_count": len(entries),
        "events": events[-120:],
        "event_count": len(events),
        "cooldown_sessions": cooldown_sessions,
        "cached": False,
        "note": (
            "Research-only historical diagnostic using the current theme universe and Yahoo data. "
            "Forward excess returns are measured versus QQQ and are not used by the live signal engine."
        ),
        "limitations": [
            "Current-universe / survivorship bias is possible.",
            "Small samples can be unstable.",
            "ETF proxies may not perfectly represent every member stock.",
        ],
    }
    _CACHE["ts"], _CACHE["sessions"], _CACHE["payload"] = now, sessions, payload
    return payload
