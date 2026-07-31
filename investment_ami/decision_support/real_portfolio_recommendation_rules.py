"""Deterministic recommendation rules for the real portfolio advisor (Phase C)."""

from __future__ import annotations

from typing import Any

from investment_ami.decision_support.real_portfolio_confidence import assess_real_portfolio_confidence
from investment_ami.decision_support.real_portfolio_concentration import RealPortfolioConcentrationAnalysis
from investment_ami.decision_support.real_portfolio_drift import (
    DRIFT_MATERIAL_MIN_PP,
    RealPortfolioDriftAnalysis,
)
from investment_ami.decision_support.real_portfolio_models import RealPortfolioSnapshot
from investment_ami.decision_support.real_portfolio_performance import RealPortfolioPerformanceAnalysis
from investment_ami.decision_support.real_portfolio_recommendations import (
    ActionType,
    RealPortfolioRecommendation,
    RealPortfolioRecommendationSet,
    RecommendationRuleResult,
)
from investment_ami.decision_support.real_portfolio_security_types import SecurityKind

STALE_QUOTE_AGE_SECONDS = 90
NEAR_TERM_LIQUIDITY_RATIO = 0.15
WEAK_RESERVE_THRESHOLD = 10_000.0


def _rule_to_rec(rule: RecommendationRuleResult) -> RealPortfolioRecommendation:
    titles: dict[str, str] = {
        "refresh_market_data": "Refresh market data before acting",
        "add_missing_cost_basis": "Add or correct cost basis in transaction history",
        "define_target_allocation": "Define an explicit target allocation",
        "preserve_liquidity": "Preserve liquidity for near-term needs",
        "review_material_single_security": "Review materially concentrated individual security",
        "review_asset_class_overweight": "Review asset-class overweight versus target",
        "review_thematic_etf_concentration": "Review thematic or sector ETF concentration",
        "direct_new_contributions_underweight": "Direct new contributions toward underweight sleeves",
        "rebalance_with_new_money": "Rebalance gradually using future contributions",
        "hold_current_course": "Continue holding the current allocation",
        "no_urgent_change": "No urgent portfolio change appears necessary",
        "review_negative_cash": "Review funding and transaction ledger for cash balance",
        "review_dual_portfolio_mismatch": "Review ledger versus holdings editor alignment",
        "insufficient_data": "Insufficient data for target-based placement",
        "reduce_contribution_temporarily": "Reduce new investment until liquidity improves",
    }
    return RealPortfolioRecommendation(
        code=rule.code,
        priority=rule.priority,
        action_type=rule.action_type,
        title=titles.get(rule.code, rule.code.replace("_", " ").title()),
        rationale_code=rule.rationale_code,
        evidence=dict(rule.evidence),
        conditions=rule.conditions,
        caution_flags=rule.caution_flags,
    )


def _liquidity_pressure(snapshot: RealPortfolioSnapshot) -> tuple[bool, dict[str, Any]]:
    near = float(snapshot.near_term_needs or 0.0)
    reserves = snapshot.reserves or {}
    emergency = float(reserves.get("emergency", 0.0))
    tmv = max(snapshot.total_market_value, 1.0)
    evidence: dict[str, Any] = {
        "near_term_needs": near,
        "emergency_reserve": emergency,
        "total_market_value": snapshot.total_market_value,
    }
    strong_near_term = near >= NEAR_TERM_LIQUIDITY_RATIO * tmv and near > 0
    weak_reserves = emergency < WEAK_RESERVE_THRESHOLD and near > 0
    pressured = strong_near_term or weak_reserves
    evidence["liquidity_pressured"] = pressured
    return pressured, evidence


def _contribution_placement(
    drift: RealPortfolioDriftAnalysis,
    snapshot: RealPortfolioSnapshot,
    *,
    liquidity_pressured: bool,
) -> dict[str, Any]:
    if drift.target_source == "unavailable" or drift.target_quality not in ("explicit", "sufficient"):
        return {
            "available": False,
            "reason": "no_valid_target",
            "eligible_underweights": [],
        }
    underweights = [
        o
        for o in drift.observations
        if o.drift_percentage_points <= -DRIFT_MATERIAL_MIN_PP and o.severity in ("material", "substantial", "modest")
    ]
    underweights = sorted(underweights, key=lambda o: o.drift_percentage_points)
    eligible = [
        {
            "asset_class": o.asset_class,
            "drift_pp": o.drift_percentage_points,
            "current_weight": o.current_weight,
            "target_weight": o.target_weight,
        }
        for o in underweights
    ]
    if liquidity_pressured:
        return {
            "available": False,
            "reason": "liquidity_constraints",
            "eligible_underweights": eligible,
            "hold_cash_temporarily": True,
        }
    if not eligible:
        return {"available": False, "reason": "no_material_underweight", "eligible_underweights": []}
    return {
        "available": True,
        "primary_asset_class": eligible[0]["asset_class"],
        "eligible_underweights": eligible,
        "prefer_new_money_over_sales": True,
        "monthly_contribution_known": snapshot.monthly_contribution is not None,
    }


def evaluate_recommendation_rules(
    snapshot: RealPortfolioSnapshot,
    performance: RealPortfolioPerformanceAnalysis,
    concentration: RealPortfolioConcentrationAnalysis,
    drift: RealPortfolioDriftAnalysis,
    *,
    ask_contribution_placement: bool = False,
) -> list[RecommendationRuleResult]:
    """Evaluate all applicable rules; does not mutate inputs."""
    rules: list[RecommendationRuleResult] = []

    if snapshot.unpriced_holdings_count > 0 or "missing_prices" in snapshot.data_quality_flags:
        rules.append(
            RecommendationRuleResult(
                code="refresh_market_data",
                priority=10,
                action_type="refresh_market_data",
                rationale_code="missing_prices",
                evidence={"unpriced_holdings_count": snapshot.unpriced_holdings_count},
            )
        )

    age = snapshot.market_data_age_seconds
    if snapshot.market_data_status == "cached" and age is not None and age > STALE_QUOTE_AGE_SECONDS:
        rules.append(
            RecommendationRuleResult(
                code="refresh_market_data",
                priority=12,
                action_type="refresh_market_data",
                rationale_code="stale_quotes",
                evidence={"market_data_age_seconds": age},
            )
        )

    if any(h.total_cost_basis <= 0 and h.current_price for h in snapshot.holdings):
        rules.append(
            RecommendationRuleResult(
                code="add_missing_cost_basis",
                priority=15,
                action_type="add_missing_cost_basis",
                rationale_code="incomplete_cost_basis",
                evidence={},
            )
        )

    if snapshot.cash < -1e-6 or "negative_cash_balance" in snapshot.data_quality_flags:
        rules.append(
            RecommendationRuleResult(
                code="review_negative_cash",
                priority=18,
                action_type="insufficient_data",
                rationale_code="negative_cash_balance",
                evidence={"cash": snapshot.cash},
            )
        )

    if drift.target_source == "unavailable" or drift.target_quality == "invalid":
        rules.append(
            RecommendationRuleResult(
                code="define_target_allocation",
                priority=20,
                action_type="define_target_allocation",
                rationale_code="target_unavailable",
                evidence={"target_source": drift.target_source},
            )
        )

    liquidity_pressured, liq_evidence = _liquidity_pressure(snapshot)
    if liquidity_pressured:
        rules.append(
            RecommendationRuleResult(
                code="preserve_liquidity",
                priority=25,
                action_type="preserve_liquidity",
                rationale_code="near_term_or_reserve_pressure",
                evidence=liq_evidence,
            )
        )
        if snapshot.monthly_contribution is not None and snapshot.monthly_contribution > 0:
            rules.append(
                RecommendationRuleResult(
                    code="reduce_contribution_temporarily",
                    priority=26,
                    action_type="reduce_contribution_temporarily",
                    rationale_code="liquidity_over_contribution",
                    evidence=liq_evidence,
                )
            )

    for obs in concentration.observations:
        if obs.code == "material_single_security_weight":
            urgency_evidence = dict(obs.evidence)
            urgency_evidence.update({"weight": obs.value, "ticker": obs.ticker})
            priority = 30
            if liquidity_pressured:
                priority = 28
            if snapshot.investment_horizon is not None and snapshot.investment_horizon < 5:
                priority -= 2
            rules.append(
                RecommendationRuleResult(
                    code="review_material_single_security",
                    priority=priority,
                    action_type="review_material_single_security",
                    rationale_code="material_single_stock_weight",
                    evidence=urgency_evidence,
                    conditions=("does_not_recommend_sale",),
                )
            )
        elif obs.code == "narrow_or_thematic_etf_weight" and (obs.value or 0) >= 10.0:
            rules.append(
                RecommendationRuleResult(
                    code="review_thematic_etf_concentration",
                    priority=32,
                    action_type="review_material_single_security",
                    rationale_code="thematic_etf_concentration",
                    evidence={"ticker": obs.ticker, "weight": obs.value},
                )
            )

    if drift.rebalance_triggered and drift.largest_overweight:
        ow = drift.largest_overweight
        clf = concentration.security_classifications.get(
            concentration.largest_holding.ticker if concentration.largest_holding else "",
        )
        kind: SecurityKind | None = clf.kind if clf else None
        if kind == "broad_market_etf":
            rules.append(
                RecommendationRuleResult(
                    code="review_asset_class_overweight",
                    priority=40,
                    action_type="review_asset_class_overweight",
                    rationale_code="broad_etf_asset_class_overweight",
                    evidence={
                        "asset_class": ow.asset_class,
                        "drift_pp": ow.drift_percentage_points,
                    },
                    caution_flags=("not_single_company_risk",),
                )
            )
        else:
            rules.append(
                RecommendationRuleResult(
                    code="review_asset_class_overweight",
                    priority=40,
                    action_type="review_asset_class_overweight",
                    rationale_code="material_overweight",
                    evidence={
                        "asset_class": ow.asset_class,
                        "drift_pp": ow.drift_percentage_points,
                    },
                    caution_flags=("seek_tax_guidance_before_sale",),
                )
            )
        rules.append(
            RecommendationRuleResult(
                code="rebalance_with_new_money",
                priority=45,
                action_type="rebalance_with_new_money",
                rationale_code="material_drift_prefer_contributions",
                evidence={"rebalance_triggered": True},
                caution_flags=("seek_tax_guidance_before_sale",),
            )
        )

    placement = _contribution_placement(drift, snapshot, liquidity_pressured=liquidity_pressured)
    if ask_contribution_placement or placement.get("available"):
        if placement.get("available") and not liquidity_pressured:
            rules.append(
                RecommendationRuleResult(
                    code="direct_new_contributions_underweight",
                    priority=50,
                    action_type="direct_new_contributions",
                    rationale_code="underweight_asset_class",
                    evidence={
                        "primary_asset_class": placement.get("primary_asset_class"),
                        "eligible": placement.get("eligible_underweights"),
                    },
                )
            )
        elif ask_contribution_placement and not placement.get("available"):
            rules.append(
                RecommendationRuleResult(
                    code="insufficient_data",
                    priority=55,
                    action_type="insufficient_data",
                    rationale_code=placement.get("reason", "no_placement"),
                    evidence={"contribution_placement": placement},
                )
            )

    if snapshot.holdings_df_mismatch_warning:
        rules.append(
            RecommendationRuleResult(
                code="review_dual_portfolio_mismatch",
                priority=14,
                action_type="insufficient_data",
                rationale_code="ledger_model_mismatch",
                evidence={"message": snapshot.holdings_df_mismatch_warning[:200]},
            )
        )

    data_blockers = {
        r.action_type
        for r in rules
        if r.priority <= 20 and r.action_type in ("refresh_market_data", "define_target_allocation", "insufficient_data")
    }
    can_hold = (
        snapshot.unpriced_holdings_count == 0
        and drift.drift_status in ("aligned", "immaterial_drift")
        and concentration.concentration_status
        in ("well_diversified_by_weight", "unknown_metadata")
        and not any(r.code == "review_material_single_security" for r in rules)
        and not liquidity_pressured
    )
    if can_hold and "define_target_allocation" not in {r.action_type for r in rules}:
        rules.append(
            RecommendationRuleResult(
                code="no_urgent_change",
                priority=90,
                action_type="no_urgent_change",
                rationale_code="within_thresholds",
                evidence={
                    "drift_status": drift.drift_status,
                    "performance_status": performance.performance_status,
                },
            )
        )
        rules.append(
            RecommendationRuleResult(
                code="hold_current_course",
                priority=95,
                action_type="hold_current_course",
                rationale_code="hold_current_course",
                evidence={},
            )
        )

    if not rules and data_blockers:
        rules.append(
            RecommendationRuleResult(
                code="insufficient_data",
                priority=100,
                action_type="insufficient_data",
                rationale_code="blocked_by_data_quality",
                evidence={},
            )
        )

    rules.sort(key=lambda r: (r.priority, r.code))
    deduped: list[RecommendationRuleResult] = []
    seen_codes: set[str] = set()
    for rule in rules:
        if rule.code in seen_codes:
            continue
        seen_codes.add(rule.code)
        deduped.append(rule)
    return deduped


def build_real_portfolio_recommendations(
    snapshot: RealPortfolioSnapshot,
    performance: RealPortfolioPerformanceAnalysis,
    concentration: RealPortfolioConcentrationAnalysis,
    drift: RealPortfolioDriftAnalysis,
    *,
    ask_contribution_placement: bool = False,
) -> RealPortfolioRecommendationSet:
    """Assemble prioritized recommendations and confidence from typed analyses only."""
    rules = evaluate_recommendation_rules(
        snapshot,
        performance,
        concentration,
        drift,
        ask_contribution_placement=ask_contribution_placement,
    )
    recs = tuple(_rule_to_rec(r) for r in rules)
    confidence = assess_real_portfolio_confidence(snapshot, performance, concentration, drift)

    flags = list(snapshot.data_quality_flags)
    for src in (performance.data_quality_flags, concentration.data_quality_flags, drift.data_quality_flags):
        flags.extend(src)

    tradeoffs: list[str] = []
    if any(r.action_type == "rebalance_with_new_money" for r in recs):
        tradeoffs.append(
            "Using new contributions avoids realizing taxable gains but rebalances more slowly than selling overweight positions."
        )
    if any("seek_tax_guidance_before_sale" in r.caution_flags for r in rules):
        tradeoffs.append(
            "Selling appreciated positions may have tax consequences; verify before acting."
        )
    if any(r.action_type == "preserve_liquidity" for r in recs):
        tradeoffs.append(
            "Increasing cash improves liquidity but reduces market exposure until needs are funded."
        )

    information_needed: list[str] = []
    if drift.target_source == "unavailable":
        information_needed.append("explicit_target_allocation")
    if snapshot.monthly_contribution is None and ask_contribution_placement:
        information_needed.append("monthly_contribution_capacity")
    if snapshot.unpriced_holdings_count > 0:
        information_needed.append("updated_market_prices")
    if any(h.total_cost_basis <= 0 for h in snapshot.holdings):
        information_needed.append("missing_cost_basis")

    supporting: list[str] = []
    if performance.total_gain_loss_dollars is not None:
        supporting.append(f"unrealized_gain_loss_dollars:{performance.total_gain_loss_dollars:.2f}")
    supporting.append(f"drift_status:{drift.drift_status}")
    supporting.append(f"concentration_status:{concentration.concentration_status}")

    primary: ActionType = recs[0].action_type if recs else "insufficient_data"
    urgent_actions = {r.action_type for r in recs if r.priority <= 30}
    if "review_material_single_security" in urgent_actions or "preserve_liquidity" in urgent_actions:
        urgency = "high"
    elif any(r.priority <= 50 for r in recs):
        urgency = "medium"
    else:
        urgency = "low"

    if primary in ("hold_current_course", "no_urgent_change"):
        status = "hold"
    elif primary in ("insufficient_data", "define_target_allocation"):
        status = "information_needed" if primary == "define_target_allocation" else "insufficient_data"
    elif information_needed and primary == "direct_new_contributions":
        status = "action_recommended"
    elif information_needed:
        status = "information_needed"
    else:
        status = "action_recommended"

    limitations = list(performance.limitations) + list(drift.limitations)
    placement = _contribution_placement(
        drift,
        snapshot,
        liquidity_pressured=_liquidity_pressure(snapshot)[0],
    )

    return RealPortfolioRecommendationSet(
        primary_action=primary,
        recommendations=recs,
        urgency=urgency,
        recommendation_status=status,
        confidence_level=confidence.confidence_level,
        confidence_score=confidence.confidence_score,
        supporting_facts=tuple(supporting),
        tradeoffs=tuple(tradeoffs),
        information_needed=tuple(dict.fromkeys(information_needed)),
        data_quality_flags=tuple(dict.fromkeys(flags)),
        limitations=tuple(limitations),
        contribution_placement=placement,
    )
