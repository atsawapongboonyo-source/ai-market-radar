"""
AI MARKET RADAR V4.8.2

Calibration patch on top of V4.8.1.
- one-stock groups are neutral for sector confirmation
- sanitize Top Pick reasons so UI cannot imply false sector breadth
- align visible V4.7/V4.7.1 labels with active V4.8 runtime
"""

import scanner_v481 as v481
import scanner as base

app = v481.app

_prev_derive_context = base._derive_context
_prev_build_top_picks = base.build_top_picks


def _derive_context_v482(results):
    ctx = dict(_prev_derive_context(results) or {})
    groups = dict(ctx.get("groups") or {})

    for name, raw in list(groups.items()):
        info = dict(raw or {})
        count = int(info.get("count") or 0)

        if count < 2:
            info["raw_state"] = info.get("state", "unknown")
            info["state"] = "neutral"
            info["relative_state"] = "neutral"
            info["effective_relative_strength"] = 0
            info["sector_confidence"] = "low"
            info["sector_confidence_weight"] = 0.0

        groups[name] = info

    ctx["groups"] = groups
    ctx["version"] = "4.8.2"
    return ctx


def _build_top_picks_v482(force=False):
    payload = dict(_prev_build_top_picks(force=force) or {})

    for x in payload.get("top_picks", []) or []:
        count = int(x.get("sector_member_count") or 0)
        confidence = str(x.get("sector_confidence") or "low")

        reasons = list(x.get("pick_reasons") or [])

        if count < 2 or confidence == "low":
            blocked = {
                "กลุ่มหุ้นแข็งแรง",
                "กลุ่มหุ้นอ่อน",
                "กลุ่มแข็งกว่าภาพรวม",
                "กลุ่มอ่อนกว่าภาพรวม",
            }
            reasons = [r for r in reasons if r not in blocked]

            marker = "Sector sample น้อย — ยังไม่ใช้ยืนยัน"
            if marker not in reasons:
                reasons.append(marker)

            x["group_state"] = "neutral"
            x["sector_relative_state"] = "neutral"
            x["sector_effective_relative_strength"] = 0

        x["pick_reasons"] = reasons[:4]

    payload["version"] = "4.8.2"
    payload["note"] = (
        "V4.8.2: one-stock sectors are neutral for confirmation; "
        "Top Pick still requires Premarket Gate and Opening Confirmation."
    )
    return payload


base._derive_context = _derive_context_v482
base.build_top_picks = _build_top_picks_v482


@app.after_request
def _v482_ui_labels(response):
    try:
        if "text/html" not in (response.content_type or "").lower():
            return response

        body = response.get_data(as_text=True)

        replacements = {
            "AI Market Radar V4.7.1": "AI Market Radar V4.8.2",
            "AI Market Radar V4.7": "AI Market Radar V4.8.2",
            "V4.7.1 • Multi-Level Reclaim Engine": "V4.8.2 • Leading Signal + Multi-Level Reclaim",
            "V4.7 • Position Engine": "V4.8.2 • Leading Signal + Position Engine",
            "<b>V4.7</b> เพิ่ม Position Engine ": "<b>V4.8.2</b> Leading Signal + Position Engine ",
            "<b>V4.6</b> เพิ่ม Opening Confirmation หลังตลาดเปิด": "<b>V4.8.2</b> Leading Signal + Opening Confirmation",
        }

        for old, new in replacements.items():
            body = body.replace(old, new)

        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
    except Exception:
        pass

    return response
