"""
AI MARKET RADAR V4.8 - Leading Signal Layer

Append-only runtime extension for the existing scanner.py.
Goals:
- keep V4.7/V4.7.1 entry, opening and position engines intact
- improve ranking quality with market regime + sector confidence
- avoid self-reinforcing sector bonuses for one-stock groups (e.g. PLTR/software)
- expose catalyst freshness/impact metadata
- expose a Leading Signal Score in final confirmation (NOT win probability)
"""

import time
import scanner as base

app = base.app

# A modest expansion keeps Catalyst coverage broader without turning the
# free data source into the bottleneck.
base._TOP_PICK_NEWS_LIMIT = max(getattr(base, "_TOP_PICK_NEWS_LIMIT", 5), 8)

_orig_derive_context = base._derive_context
_orig_get_catalyst = base._get_catalyst
_orig_top_pick_score = base._top_pick_score
_orig_build_top_picks = base.build_top_picks
_orig_auto_confirm = base._auto_confirm


def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, float(v)))


def _derive_context_v48(results):
    """Add breadth/regime + group relative-strength confidence metadata."""
    ctx = _orig_derive_context(results)
    ctx = dict(ctx or {})

    groups = ctx.get("groups") or {}
    market_score = float(ctx.get("market_score") or 0)

    usable = [
        x for x in (results or [])
        if x.get("confidence_code") != "CACHED"
    ]

    positive_actions = sum(
        1 for x in usable
        if x.get("action_code") in ("ENTER", "SCALE")
    )
    defensive_actions = sum(
        1 for x in usable
        if x.get("action_code") in ("DONT_CHASE", "AVOID")
    )

    breadth_pct = (
        round(positive_actions / len(usable) * 100, 1)
        if usable else 0.0
    )
    defensive_pct = (
        round(defensive_actions / len(usable) * 100, 1)
        if usable else 0.0
    )

    bull_groups = 0
    bear_groups = 0

    for name, raw in groups.items():
        info = dict(raw or {})
        strength = float(info.get("strength") or 0)
        count = int(info.get("count") or 0)
        relative = round(strength - market_score, 2)

        # Important calibration: a one-stock group is not independent sector
        # confirmation. It should not double-count the same stock's signal.
        if count >= 4:
            confidence = "high"
            confidence_weight = 1.0
        elif count >= 2:
            confidence = "medium"
            confidence_weight = 0.65
        else:
            confidence = "low"
            confidence_weight = 0.0

        effective_relative = round(relative * confidence_weight, 2)
        relative_state = (
            "outperform"
            if effective_relative >= 0.12
            else "underperform"
            if effective_relative <= -0.12
            else "neutral"
        )

        info.update({
            "relative_strength": relative,
            "effective_relative_strength": effective_relative,
            "relative_state": relative_state,
            "sector_confidence": confidence,
            "sector_confidence_weight": confidence_weight,
        })
        groups[name] = info

        # Count group breadth only when there are at least two members.
        if count >= 2:
            if info.get("state") == "bull":
                bull_groups += 1
            elif info.get("state") == "bear":
                bear_groups += 1

    raw_regime_score = (
        market_score * 62
        + (bull_groups - bear_groups) * 5
        + (breadth_pct - defensive_pct) * 0.12
    )
    regime_score = round(_clamp(raw_regime_score, -100, 100), 1)

    if (
        market_score >= 0.18
        and bull_groups >= 2
        and bear_groups <= 1
        and breadth_pct >= 25
    ):
        regime = "risk_on"
        regime_label = "🟢 Risk-On"
    elif (
        market_score <= -0.18
        or (bear_groups >= 3 and bull_groups <= 1)
        or defensive_pct >= 45
    ):
        regime = "risk_off"
        regime_label = "🔴 Risk-Off"
    else:
        regime = "mixed"
        regime_label = "🟡 Mixed"

    ctx.update({
        "groups": groups,
        "regime": regime,
        "regime_label": regime_label,
        "regime_score": regime_score,
        "breadth_pct": breadth_pct,
        "defensive_pct": defensive_pct,
        "bull_groups": bull_groups,
        "bear_groups": bear_groups,
        "usable_count": len(usable),
        "version": "4.8",
    })
    return ctx


def _get_catalyst_v48(ticker, force=False):
    """Keep existing sentiment logic and add freshness/impact confidence."""
    data = dict(_orig_get_catalyst(ticker, force) or {})
    items = data.get("items") or []

    known_ages = [
        float(x.get("age_hours"))
        for x in items
        if x.get("age_hours") is not None
    ]
    newest_age = min(known_ages) if known_ages else None
    fresh_24h = sum(
        1 for x in items
        if x.get("age_hours") is not None
        and float(x.get("age_hours")) <= 24
    )
    fresh_72h = sum(
        1 for x in items
        if x.get("age_hours") is not None
        and float(x.get("age_hours")) <= 72
    )
    high_impact_count = sum(1 for x in items if x.get("high_impact"))

    if not items:
        freshness_score = 30
        impact_score = 25
    else:
        if newest_age is None:
            freshness_score = 45
        elif newest_age <= 12:
            freshness_score = 100
        elif newest_age <= 24:
            freshness_score = 90
        elif newest_age <= 72:
            freshness_score = 72
        elif newest_age <= 168:
            freshness_score = 50
        else:
            freshness_score = 28

        impact_score = min(
            100,
            35 + high_impact_count * 20 + min(len(items), 5) * 5,
        )

    sentiment = str(data.get("sentiment") or "unknown").lower()
    direction = {
        "positive": 1,
        "negative": -1,
        "neutral": 0,
        "unknown": 0,
    }.get(sentiment, 0)

    base_score = float(data.get("score") or 50)
    directional_strength = abs(base_score - 50) / 50
    reliability = (
        freshness_score * 0.55
        + impact_score * 0.30
        + (100 if items else 20) * 0.15
    ) / 100

    catalyst_edge = round(
        direction * directional_strength * reliability * 15,
        2,
    )

    data.update({
        "freshness_score": round(freshness_score),
        "impact_score": round(impact_score),
        "newest_news_age_hours": (
            round(newest_age, 1) if newest_age is not None else None
        ),
        "fresh_24h_count": fresh_24h,
        "fresh_72h_count": fresh_72h,
        "high_impact_count": high_impact_count,
        "catalyst_edge": catalyst_edge,
        "catalyst_confidence": (
            "high"
            if freshness_score >= 80 and impact_score >= 60
            else "medium"
            if freshness_score >= 50
            else "low"
        ),
        "version": "4.8",
    })
    return data


def _top_pick_score_v48(item, ctx, catalyst):
    """Calibrate existing Watch Score; still NOT a probability."""
    score = float(_orig_top_pick_score(item, ctx, catalyst))

    group_info = (
        (ctx.get("groups") or {})
        .get(item.get("group"), {})
        or {}
    )
    group_count = int(group_info.get("count") or 0)
    group_state = str(group_info.get("state") or "unknown")

    # Remove the old group-state bonus when the "sector" is only this stock.
    # This prevents PLTR/software (1 member) from confirming itself twice.
    if group_count < 2:
        legacy_group_bonus = min(
            5,
            max(-5, base._context_bonus(group_state) * 0.75),
        )
        score -= legacy_group_bonus

    regime = str(ctx.get("regime") or "mixed")
    if regime == "risk_on":
        score += 3.0
    elif regime == "risk_off":
        score -= 5.0

    effective_relative = float(
        group_info.get("effective_relative_strength") or 0
    )
    if effective_relative >= 0.25:
        score += 4.0
    elif effective_relative >= 0.12:
        score += 2.0
    elif effective_relative <= -0.25:
        score -= 4.0
    elif effective_relative <= -0.12:
        score -= 2.0

    cat_edge = float(catalyst.get("catalyst_edge") or 0)
    # Catalyst sentiment is already in V4.5/V4.7 score; only a small
    # freshness/reliability calibration is added here.
    score += max(-4.0, min(3.0, cat_edge * 0.25))

    if (
        catalyst.get("negative_high_impact")
        and (catalyst.get("newest_news_age_hours") is None
             or catalyst.get("newest_news_age_hours") <= 72)
    ):
        score -= 2.0

    return round(_clamp(score, 0, 94), 1)


def _build_top_picks_v48(force=False):
    payload = dict(_orig_build_top_picks(force=force) or {})
    scan = base.scan_watchlist(force=False)
    ctx = scan.get("auto_context") or {}

    for x in payload.get("top_picks", []) or []:
        g = (
            (ctx.get("groups") or {})
            .get(x.get("group"), {})
            or {}
        )
        cat = x.get("catalyst") or {}

        # Older base payloads only keep a subset of Catalyst fields. Re-fetch
        # is normally served from cache, so this does not add meaningful load.
        full_cat = _get_catalyst_v48(x.get("ticker"), False)
        cat.update({
            "freshness_score": full_cat.get("freshness_score"),
            "impact_score": full_cat.get("impact_score"),
            "newest_news_age_hours": full_cat.get("newest_news_age_hours"),
            "fresh_24h_count": full_cat.get("fresh_24h_count"),
            "high_impact_count": full_cat.get("high_impact_count"),
            "catalyst_edge": full_cat.get("catalyst_edge"),
            "catalyst_confidence": full_cat.get("catalyst_confidence"),
        })
        x["catalyst"] = cat

        x["market_regime"] = ctx.get("regime", "mixed")
        x["market_regime_label"] = ctx.get("regime_label", "🟡 Mixed")
        x["market_regime_score"] = ctx.get("regime_score", 0)
        x["market_breadth_pct"] = ctx.get("breadth_pct", 0)
        x["sector_relative_strength"] = g.get("relative_strength", 0)
        x["sector_effective_relative_strength"] = g.get(
            "effective_relative_strength", 0
        )
        x["sector_relative_state"] = g.get("relative_state", "neutral")
        x["sector_confidence"] = g.get("sector_confidence", "low")
        x["sector_member_count"] = g.get("count", 0)
        x["leading_signal_score"] = x.get("watch_score")
        x["leading_signal_note"] = "คะแนนจัดลำดับสัญญาณ ไม่ใช่โอกาสชนะ"

        reasons = list(x.get("pick_reasons") or [])
        if x["sector_confidence"] == "low":
            reasons.append("Sector sample น้อย — ไม่ใช้ยืนยันซ้ำ")
        elif x["sector_relative_state"] == "outperform":
            reasons.append("กลุ่มแข็งกว่าภาพรวม")
        elif x["sector_relative_state"] == "underperform":
            reasons.append("กลุ่มอ่อนกว่าภาพรวม")
        if x["market_regime"] == "risk_on":
            reasons.append("Market Regime = Risk-On")
        elif x["market_regime"] == "risk_off":
            reasons.append("Market Regime = Risk-Off")
        x["pick_reasons"] = reasons[:5]

    payload.update({
        "version": "4.8",
        "market_regime": ctx.get("regime", "mixed"),
        "market_regime_label": ctx.get("regime_label", "🟡 Mixed"),
        "market_regime_score": ctx.get("regime_score", 0),
        "market_breadth_pct": ctx.get("breadth_pct", 0),
        "note": (
            "V4.8 Leading Signal Layer: Technical + Catalyst freshness + "
            "Market Regime + Sector Relative Strength. "
            "Leading Signal Score ใช้จัดลำดับ ไม่ใช่เปอร์เซ็นต์โอกาสชนะ; "
            "ยังต้องผ่าน Premarket Gate + Opening Confirmation ก่อนเข้า"
        ),
        "updated_v48_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    return payload


def _auto_confirm_v48(p):
    result = dict(_orig_auto_confirm(p) or {})

    try:
        price = float(p.get("price"))
        lo = float(p.get("buy_low"))
        hi = float(p.get("buy_high"))
    except (TypeError, ValueError):
        price = lo = hi = None

    market = str(p.get("market") or "unknown").lower()
    sector = str(p.get("sector") or "unknown").lower()
    catalyst = str(p.get("catalyst") or "unknown").lower()

    try:
        pm = None if p.get("premarket_pct") in (None, "") else float(p.get("premarket_pct"))
    except (TypeError, ValueError):
        pm = None
    try:
        rv = None if p.get("rel_volume") in (None, "") else float(p.get("rel_volume"))
    except (TypeError, ValueError):
        rv = None

    score = 35.0
    confirms = []
    cautions = []

    if price is not None and lo is not None and hi is not None and lo <= price <= hi:
        score += 18
        confirms.append("ราคาอยู่ใน Buy Zone")
    elif price is not None and hi is not None and price > hi:
        score -= 8
        cautions.append("ราคาเหนือ Buy Zone")

    if market == "bull":
        score += 10
        confirms.append("Market สนับสนุน")
    elif market == "bear":
        score -= 12
        cautions.append("Market อ่อน")

    if sector == "bull":
        score += 10
        confirms.append("Sector สนับสนุน")
    elif sector == "bear":
        score -= 12
        cautions.append("Sector อ่อน")

    if catalyst == "positive":
        score += 8
        confirms.append("Catalyst บวก")
    elif catalyst == "negative":
        score -= 12
        cautions.append("Catalyst ลบ")

    if pm is None:
        cautions.append("ยังไม่มี Premarket")
    elif 1 <= pm < 5:
        score += 10
        confirms.append("Premarket อยู่ในช่วงดี")
    elif pm >= 5:
        score -= 7
        cautions.append("Premarket ร้อนเกินไป")
    elif pm < -5:
        score -= 20
        cautions.append("Premarket ต่ำกว่า -5%")

    if rv is not None:
        if 1.2 <= rv <= 3.0:
            score += 9
            confirms.append("RVOL ยืนยัน Momentum")
        elif rv > 3.0:
            score += 3
            cautions.append("RVOL สูงมาก/ผันผวน")
        elif rv < 0.8:
            score -= 6
            cautions.append("RVOL เบา")

    score = round(_clamp(score), 0)
    label = (
        "🟢 Strong Stack"
        if score >= 78
        else "🟦 Good Stack"
        if score >= 65
        else "🟡 Mixed Stack"
        if score >= 48
        else "🔴 Weak Stack"
    )

    result["leading_signal"] = {
        "score": int(score),
        "label": label,
        "confirmations": confirms,
        "cautions": cautions,
        "confirmation_count": len(confirms),
        "note": "Leading Signal Score ไม่ใช่ win probability และไม่แทน Opening Confirmation",
        "version": "4.8",
    }
    result["version"] = "4.8"
    return result


# Runtime monkey patches. Existing routes keep working because scanner.py
# resolves these names from its module globals when each request executes.
base._derive_context = _derive_context_v48
base._get_catalyst = _get_catalyst_v48
base._top_pick_score = _top_pick_score_v48
base.build_top_picks = _build_top_picks_v48
base._auto_confirm = _auto_confirm_v48
