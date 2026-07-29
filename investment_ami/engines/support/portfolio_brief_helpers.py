"""Phase 3 — derived summaries, archetype, and data-quality helpers for PortfolioAnalysisBrief."""

from __future__ import annotations

from typing import Any, Literal

InferenceClass = Literal["measured", "computed", "estimated", "assumption"]

MAX_HOLDINGS_IN_BRIEF = 12

Archetype = Literal[
    "empty",
    "sparse",
    "single_stock",
    "concentrated",
    "etf_heavy",
    "diversified",
    "balanced_two_fund",
]


def classify_portfolio_archetype(
    rows: list[tuple[str, float]],
    *,
    asset_class_count: int,
    overlap_pair_count: int,
    top_weight_pct: float,
) -> Archetype:
    if not rows:
        return "empty"
    if len(rows) == 1:
        return "single_stock"
    if top_weight_pct > 50:
        return "concentrated"
    if len(rows) == 2 and top_weight_pct <= 50:
        return "balanced_two_fund"
    if overlap_pair_count > 0 and len(rows) <= 5:
        return "etf_heavy"
    if asset_class_count >= 3 and top_weight_pct < 40:
        return "diversified"
    if len(rows) >= 4 and top_weight_pct < 35:
        return "diversified"
    if len(rows) <= 3:
        return "sparse"
    return "diversified"


def concentration_summary(
    *,
    top_ticker: str,
    top_pct: float,
    top3_pct: float,
    flag: str,
) -> dict[str, Any]:
    severity = {"high": "elevated", "moderate": "moderate", "low": "modest"}.get(flag, flag)
    line = (
        f"Largest position **{top_ticker}** at **{top_pct:.1f}%**; top-three weight **{top3_pct:.1f}%** "
        f"({severity} concentration)."
    )
    return {
        "top_ticker": top_ticker,
        "top_weight_pct": round(top_pct, 2),
        "top3_weight_pct": round(top3_pct, 2),
        "severity_flag": flag,
        "summary_line": line,
    }


def overlap_summary(overlap_pairs: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if not overlap_pairs:
        return None
    best = max(overlap_pairs, key=lambda p: float(p.get("overlap_pct") or 0))
    pair = str(best.get("pair") or "")
    pct = float(best.get("overlap_pct") or 0)
    return {
        "highest_overlap_pair": pair,
        "highest_overlap_pct": round(pct, 2),
        "pair_count": len(overlap_pairs),
        "summary_line": (
            f"Highest ETF overlap **{pair}** at **{pct:.1f}%** shared holdings "
            f"({len(overlap_pairs)} pair(s) scanned)."
        ),
    }


def scenario_summary(
    ctx: dict[str, Any],
    *,
    question: str = "",
) -> tuple[dict[str, Any], list[str]]:
    """Standard illustrative shocks for synthesis (not question-specific)."""
    limitations: list[str] = []
    try:
        from investment_ami.engines.support.scenario_stress_data import build_scenario_stress_snapshot
        from investment_ami_macro import allocation_profile_from_ctx, rate_rise_portfolio_impacts

        snap = build_scenario_stress_snapshot(ctx, question=question, default_drawdown_pct=20.0)
        profile = allocation_profile_from_ctx(ctx)
        rate_up = rate_rise_portfolio_impacts(profile, 2.0)
        rate_down = rate_rise_portfolio_impacts(profile, -2.0)
    except Exception as exc:
        limitations.append(f"Scenario summary unavailable: {exc}")
        return {}, limitations

    if snap.total_tech_pct <= 0 and not profile.get("equity"):
        limitations.append("Scenario shocks are approximate — limited sleeve data for stress math.")

    summary = {
        "tech_drawdown_assumption_pct": round(snap.tech_drawdown_pct, 1),
        "illustrative_portfolio_impact_from_tech_shock_pct": round(snap.illustrative_impact_pct, 2),
        "total_technology_exposure_pct": round(snap.total_tech_pct, 2),
        "bond_defensive_sleeve_pct": round(snap.bond_defensive_pct, 2),
        "rate_shock_plus_200bp_net_return_shift_pp": rate_up.get("net_return_shift_pp"),
        "rate_shock_minus_200bp_net_return_shift_pp": rate_down.get("net_return_shift_pp"),
        "method_note": (
            "Illustrative education model from AMI engines; not a forecast or trade recommendation."
        ),
    }
    return summary, limitations


def sector_allocation_summary(
    ctx: dict[str, Any],
    *,
    tech_exposure: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[str]]:
    limitations: list[str] = []
    breakdown = ctx.get("asset_class_breakdown")
    out: dict[str, Any] = {}
    if isinstance(breakdown, dict) and breakdown:
        items = sorted(((k, float(v)) for k, v in breakdown.items()), key=lambda x: x[1], reverse=True)
        out["asset_class_weights_pct"] = {k: round(v, 2) for k, v in items}
        out["primary_sleeve"] = items[0][0]
        out["primary_sleeve_pct"] = round(items[0][1], 2)
    else:
        limitations.append("No asset-class breakdown — sector view uses technology exposure proxy only.")
    if isinstance(tech_exposure, dict) and tech_exposure:
        out["technology_exposure_pct"] = round(float(tech_exposure.get("total_pct") or 0), 2)
        if tech_exposure.get("used_static_fallback"):
            limitations.append("Technology exposure uses estimated fund-sector weights where live data was missing.")
    return out, limitations


def build_data_quality(
    *,
    rows: list[tuple[str, float]],
    has_performance: bool,
    has_overlap: bool,
    has_targets: bool,
    has_macro_brief: bool,
    has_asset_classes: bool,
    weight_rows_truncated: bool,
) -> dict[str, Any]:
    checks: list[dict[str, str]] = []

    def add(name: str, ok: bool, miss: str = "missing") -> None:
        checks.append({"check": name, "status": "ok" if ok else miss})

    add("portfolio_weights", bool(rows), "missing")
    add("historical_performance", has_performance, "missing")
    add("asset_class_breakdown", has_asset_classes, "missing")
    add("etf_overlap_pairs", has_overlap, "missing" if len(rows) >= 2 else "not_applicable")
    add("rebalance_targets", has_targets, "missing")
    add("macro_intelligence_brief", has_macro_brief, "missing")
    if weight_rows_truncated:
        add("holdings_complete_list", False, "truncated")

    applicable = [c for c in checks if c["status"] != "not_applicable"]
    ok_count = sum(1 for c in applicable if c["status"] == "ok")
    score = int(round(100 * ok_count / max(len(applicable), 1)))

    if not rows:
        tier = "empty"
    elif score >= 75:
        tier = "strong"
    elif score >= 45:
        tier = "partial"
    else:
        tier = "sparse"

    return {
        "completeness_score": score,
        "tier": tier,
        "checks": checks,
    }


def sleeve_profile_summary(ctx: dict[str, Any]) -> dict[str, Any]:
    from investment_ami_macro import allocation_profile_from_ctx

    profile = allocation_profile_from_ctx(ctx)
    pct = {
        k: round(float(v) * 100, 1) if isinstance(v, (int, float)) and k != "n_holdings" else v
        for k, v in profile.items()
        if k
        in (
            "equity",
            "bonds",
            "tbills",
            "reit",
            "dividend",
            "long_duration_bonds",
            "tech",
            "qqq_spy",
        )
    }
    equity = float(profile.get("equity") or 0) * 100
    bonds = float(profile.get("bonds") or 0) * 100
    defensive = float(profile.get("tbills") or 0) * 100 + bonds
    return {
        "sleeves_pct": pct,
        "equity_pct": round(equity, 1),
        "bonds_pct": round(bonds, 1),
        "defensive_liquid_pct": round(defensive, 1),
        "summary_line": (
            f"Approximate sleeves — equity **{equity:.1f}%**, bonds **{bonds:.1f}%**, "
            f"defensive/liquid **{defensive:.1f}%** (AMI allocation profile)."
        ),
    }
