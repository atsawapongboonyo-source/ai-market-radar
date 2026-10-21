"""Read-only, pure candidate-universe validation; no network, collector or scanner imports."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WATCHLIST = ROOT / "data" / "stock-radar-research-watchlist-v1.json"
HOLDINGS = ROOT / "data" / "rotation-stock-universe-v1.json"


def validate_universe(watchlist, holdings):
    if watchlist.get("source_type") != "CURATED_RESEARCH_CANDIDATES_NOT_HOLDINGS":
        raise ValueError("research candidates must not be presented as verified ETF holdings")
    safety = watchlist.get("safety", {})
    required = ("read_only", "requires_market_data_provenance",
                "requires_liquidity_and_history_validation",
                "requires_signed_ingest_before_decisions",
                "do_not_mix_with_etf_holdings", "do_not_trigger_bulk_collection")
    if any(safety.get(key) is not True for key in required):
        raise ValueError("research-only safety gates missing")
    if safety.get("signal") != "NOT_EVALUATED" or safety.get("feed") != "UNVERIFIED_UNTIL_COLLECTED":
        raise ValueError("unvalidated symbols cannot have live feed or signal")
    groups = watchlist.get("groups", {})
    if not groups or not all(isinstance(v, list) and v for v in groups.values()):
        raise ValueError("research groups missing")
    candidates = [symbol for symbols in groups.values() for symbol in symbols]
    if len(candidates) != len(set(candidates)):
        raise ValueError("duplicate research candidate across groups")
    if any(not isinstance(s, str) or not s or len(s) > 12 or
           not all(c.isupper() or c.isdigit() or c in ".-" for c in s)
           for s in candidates):
        raise ValueError("invalid research ticker")
    funds = holdings.get("funds", {})
    if not funds:
        raise ValueError("verified ETF holdings missing")
    verified = {row["symbol"] for fund in funds.values() for row in fund["stocks"]}
    return {"groups": len(groups), "research_candidates": len(candidates),
            "verified_etf_funds": len(funds), "verified_unique_stocks": len(verified),
            "overlap_symbols": sorted(set(candidates) & verified),
            "research_only_symbols": sorted(set(candidates) - verified)}


def load_report():
    with WATCHLIST.open(encoding="utf-8") as f:
        watchlist = json.load(f)
    with HOLDINGS.open(encoding="utf-8") as f:
        holdings = json.load(f)
    return validate_universe(watchlist, holdings)


if __name__ == "__main__":
    print(json.dumps(load_report(), sort_keys=True, indent=2))
