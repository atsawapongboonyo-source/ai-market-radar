"""
AI MARKET RADAR V4.8.1 - UI + Sector Reason Calibration

Small runtime patch on top of V4.8:
- keep the V4.8 scoring/ranking engine unchanged
- remove misleading single-stock sector confirmation text
- show the active V4.8 version in rendered HTML
"""

import scanner_v48 as v48
import scanner as base

app = v48.app

_v48_build_top_picks = base.build_top_picks


def _build_top_picks_v481(force=False):
    payload = dict(_v48_build_top_picks(force=force) or {})

    for x in payload.get("top_picks", []) or []:
        reasons = list(x.get("pick_reasons") or [])

        if x.get("sector_confidence") == "low":
            # A one-stock group is not independent sector confirmation.
            reasons = [
                r for r in reasons
                if r not in (
                    "กลุ่มหุ้นแข็งแรง",
                    "กลุ่มหุ้นอ่อน",
                    "กลุ่มแข็งกว่าภาพรวม",
                    "กลุ่มอ่อนกว่าภาพรวม",
                )
            ]

            marker = "Sector sample น้อย — ไม่ใช้ยืนยันซ้ำ"
            if marker not in reasons:
                reasons.append(marker)

        # UI currently renders only a short reason list, so keep the calibrated
        # sector note visible instead of letting it fall beyond the cut-off.
        x["pick_reasons"] = reasons[:4]

    payload["version"] = "4.8.1"
    payload["note"] = (
        "V4.8.1 = V4.8 Leading Signal scoring + calibrated sector explanation. "
        "Single-stock groups are not treated as independent sector confirmation."
    )
    return payload


base.build_top_picks = _build_top_picks_v481


# V5.0 owns presentation/version labels.
# Legacy V4.8.1 HTML response rewriting is intentionally disabled.
