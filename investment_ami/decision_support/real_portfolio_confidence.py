"""Deterministic confidence scoring for real portfolio recommendations (Phase C)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from investment_ami.decision_support.real_portfolio_cash_classification import classify_real_portfolio_cash
from investment_ami.decision_support.real_portfolio_concentration import RealPortfolioConcentrationAnalysis
from investment_ami.decision_support.real_portfolio_drift import RealPortfolioDriftAnalysis
from investment_ami.decision_support.real_portfolio_models import RealPortfolioSnapshot
from investment_ami.decision_support.real_portfolio_performance import RealPortfolioPerformanceAnalysis

ConfidenceLevel = Literal["low", "medium", "high"]

STALE_QUOTE_AGE_SECONDS = 90


@dataclass(frozen=True)
class RealPortfolioConfidenceAssessment:
    confidence_level: ConfidenceLevel
    confidence_score: int
    factors_increase: tuple[str, ...]
    factors_decrease: tuple[str, ...]


def assess_real_portfolio_confidence(
    snapshot: RealPortfolioSnapshot,
    performance: RealPortfolioPerformanceAnalysis,
    concentration: RealPortfolioConcentrationAnalysis,
    drift: RealPortfolioDriftAnalysis,
) -> RealPortfolioConfidenceAssessment:
    """
    Score starts at 50. Adjust in documented steps; clamp 0–100.

    +10 all holdings priced
    +10 complete cost basis on priced holdings
    +10 explicit target (user_defined, explicit quality)
    +5 saved/inferred target with sufficient quality
    +5 plan monthly contribution provided
    +5 fresh quotes (market_data_status fresh)
    +5 no ledger/model mismatch

    −15 partial prices
    −10 stale/cached quotes beyond fresh window
    −10 unknown security types in concentration
    −10 inferred/limited target
    −10 missing monthly contribution when placement relevant
    −15 holdings_df mismatch
    −10 incomplete cost basis flags
    """
    score = 50
    inc: list[str] = []
    dec: list[str] = []

    if snapshot.unpriced_holdings_count == 0:
        score += 10
        inc.append("all_holdings_priced")
    else:
        score -= 15
        dec.append("partial_prices")

    incomplete_cb = any(
        h.total_cost_basis <= 0 and h.current_price is not None for h in snapshot.holdings
    ) or "incomplete_cost_basis" in snapshot.data_quality_flags
    if incomplete_cb:
        score -= 10
        dec.append("incomplete_cost_basis")
    elif snapshot.total_cost_basis > 0:
        score += 10
        inc.append("cost_basis_present")

    if drift.target_source == "user_defined_target" and drift.target_quality == "explicit":
        score += 10
        inc.append("explicit_target")
    elif drift.target_quality == "sufficient":
        score += 5
        inc.append("sufficient_target")
    elif drift.target_source != "unavailable":
        score -= 10
        dec.append("inferred_or_limited_target")

    if snapshot.monthly_contribution is not None:
        score += 5
        inc.append("monthly_contribution_known")
    else:
        score -= 5
        dec.append("monthly_contribution_unknown")

    age = snapshot.market_data_age_seconds
    if snapshot.market_data_status == "fresh":
        score += 5
        inc.append("fresh_quotes")
    elif snapshot.market_data_status in ("cached", "partial") and age is not None and age > STALE_QUOTE_AGE_SECONDS:
        score -= 10
        dec.append("stale_quotes")

    if concentration.concentration_status == "unknown_metadata":
        score -= 10
        dec.append("unknown_security_type")

    if snapshot.holdings_df_mismatch_warning:
        score -= 15
        dec.append("holdings_df_mismatch")

    cc = classify_real_portfolio_cash(snapshot, drift)
    if cc.portfolio_cash > 0 and not cc.cash_purpose_known:
        score -= 5
        dec.append("unknown_cash_purpose")

    score = max(0, min(100, score))

    if score >= 70:
        level: ConfidenceLevel = "high"
    elif score >= 45:
        level = "medium"
    else:
        level = "low"

    if drift.target_source == "unavailable" or snapshot.unpriced_holdings_count > 0:
        level = "low" if level == "high" else level
        if snapshot.unpriced_holdings_count > 0:
            level = "low"

    if drift.target_quality not in ("explicit", "sufficient") and level == "high":
        level = "medium"

    if drift.target_source == "inferred_risk_profile_target" and level == "high":
        level = "medium"
    if cc.portfolio_cash > 0 and not cc.cash_purpose_known and level == "high":
        level = "medium"

    return RealPortfolioConfidenceAssessment(
        confidence_level=level,
        confidence_score=score,
        factors_increase=tuple(inc),
        factors_decrease=tuple(dec),
    )
