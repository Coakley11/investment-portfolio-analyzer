"""Single highest-priority change presentation for Real Portfolio Advisor."""

from __future__ import annotations

from typing import Callable

from investment_ami.decision_support.real_portfolio_cash_classification import (
    RealPortfolioCashClassification,
)
from investment_ami.decision_support.real_portfolio_drift import RealPortfolioDriftAnalysis
from investment_ami.decision_support.real_portfolio_models import RealPortfolioSnapshot
from investment_ami.decision_support.real_portfolio_performance import RealPortfolioPerformanceAnalysis
from investment_ami.decision_support.real_portfolio_recommendation_rules import STALE_QUOTE_AGE_SECONDS
from investment_ami.decision_support.real_portfolio_recommendations import (
    RealPortfolioRecommendation,
    RealPortfolioRecommendationSet,
)

_SINGLE_PRIORITY_PHRASES: tuple[str, ...] = (
    "if you could change only one thing",
    "change only one thing about my portfolio",
    "only one thing about my portfolio",
    "single biggest improvement",
    "one biggest improvement",
    "what should i fix first",
    "what's the highest-priority change",
    "what is the highest-priority change",
    "highest-priority change",
    "most important thing i should do",
    "the most important thing i should do",
    "what is the most important thing",
    "what's the most important thing",
)

_CO_PRIMARY_SKIP: frozenset[str] = frozenset(
    {
        "hold_current_course",
        "no_urgent_change",
    }
)


def is_single_priority_portfolio_question(question: str) -> bool:
    q = str(question or "").strip().lower()
    if not q:
        return False
    return any(p in q for p in _SINGLE_PRIORITY_PHRASES)


def market_data_needs_refresh(snapshot: RealPortfolioSnapshot) -> bool:
    """True only when quotes are missing, partial, unavailable, or stale."""
    if snapshot.unpriced_holdings_count > 0:
        return True
    status = str(snapshot.market_data_status or "")
    if status in ("partial", "unavailable"):
        return True
    age = snapshot.market_data_age_seconds
    if status == "cached" and age is not None and age > STALE_QUOTE_AGE_SECONDS:
        return True
    return False


def select_highest_priority_recommendation(
    recommendations: RealPortfolioRecommendationSet,
    snapshot: RealPortfolioSnapshot,
) -> RealPortfolioRecommendation | None:
    candidates: list[RealPortfolioRecommendation] = []
    for rec in recommendations.recommendations:
        if rec.code in _CO_PRIMARY_SKIP:
            continue
        if rec.code == "refresh_market_data" and not market_data_needs_refresh(snapshot):
            continue
        candidates.append(rec)
    if not candidates:
        return None
    return min(candidates, key=lambda r: (r.priority, r.code))


def _money(x: float) -> str:
    return f"${x:,.0f}"


def _underweight_follow_on(drift: RealPortfolioDriftAnalysis) -> str:
    under = [
        o.asset_class
        for o in drift.observations
        if o.drift_percentage_points <= -5.0 and o.severity in ("material", "substantial", "modest")
    ]
    if not under:
        return "address underweight sleeves in your target allocation"
    if len(under) == 1:
        return f"address the underweight **{under[0]}** sleeve"
    return "address underweight **equity and bond** sleeves"


def build_highest_priority_change_section(
    primary: RealPortfolioRecommendation,
    *,
    snapshot: RealPortfolioSnapshot,
    performance: RealPortfolioPerformanceAnalysis,
    drift: RealPortfolioDriftAnalysis,
    cash_class: RealPortfolioCashClassification,
    recommendations: RealPortfolioRecommendationSet,
) -> str:
    others = [
        r.code
        for r in recommendations.recommendations
        if r.code != primary.code and r.code not in _CO_PRIMARY_SKIP
    ]
    outrank = _outrank_explanation(primary, others)

    if primary.code == "preserve_liquidity":
        shortfall = float(primary.evidence.get("protected_shortfall") or cash_class.protected_shortfall or 0)
        target = float(primary.evidence.get("protected_cash_target") or cash_class.protected_cash_target or 0)
        action = (
            f"If I could change only one thing, I would first **increase protected cash by about {_money(shortfall)}** "
            f"so it reaches the **{_money(target)}** emergency and near-term reserve target entered in your plan."
        )
        why = (
            f"**Why this comes first:** {outrank} Reserve funding takes precedence over allocation drift and "
            "small unrealized gains or losses on individual holdings."
        )
        after = (
            f"**After that:** Once the reserve gap is covered, future contributions can gradually "
            f"{_underweight_follow_on(drift)} rather than selling current holdings."
        )
        return f"{action}\n\n{why}\n\n{after}"

    if primary.code == "review_material_single_security":
        ticker = str(primary.evidence.get("ticker") or "that holding")
        action = (
            f"If I could change only one thing, I would **review whether {ticker} still matches the role you intended** "
            "— sizing and concentration, not an automatic sell."
        )
        why = f"**Why this comes first:** {outrank}"
        after = "**After that:** Revisit drift and contribution placement once concentration is intentional."
        return f"{action}\n\n{why}\n\n{after}"

    if primary.code == "direct_new_contributions_underweight":
        sleeve = str(primary.evidence.get("primary_asset_class") or "underweight sleeves")
        action = (
            f"If I could change only one thing, I would **direct the next contributions toward {sleeve}** "
            "using new money rather than sales."
        )
        why = f"**Why this comes first:** {outrank}"
        after = "**After that:** Monitor drift until sleeves move closer to target."
        return f"{action}\n\n{why}\n\n{after}"

    title = primary.title or primary.code.replace("_", " ")
    action = f"If I could change only one thing, I would **{title[0].lower()}{title[1:]}** based on your ledger and plan inputs."
    why = f"**Why this comes first:** {outrank}"
    after = "**After that:** Address remaining suggestions only once this priority is handled."
    return f"{action}\n\n{why}\n\n{after}"


def _outrank_explanation(primary: RealPortfolioRecommendation, other_codes: list[str]) -> str:
    if not other_codes:
        return "No other recommendation outranks this one on liquidity, data quality, and plan targets."
    labels = {
        "review_asset_class_overweight": "allocation drift",
        "rebalance_with_new_money": "gradual rebalancing",
        "direct_new_contributions_underweight": "contribution placement",
        "review_thematic_etf_concentration": "thematic concentration",
        "define_target_allocation": "saving an explicit target",
    }
    named = [labels.get(c, c.replace("_", " ")) for c in other_codes[:4] if c != primary.code]
    if not named:
        return "No other recommendation outranks this one on liquidity, data quality, and plan targets."
    if len(named) == 1:
        return f"This outranks {named[0]} in the current facts."
    return f"This outranks {', '.join(named[:-1])}, and {named[-1]} in the current facts."


def build_single_priority_assessment_lead(
    primary: RealPortfolioRecommendation,
    *,
    performance: RealPortfolioPerformanceAnalysis,
    cash_class: RealPortfolioCashClassification,
    drift: RealPortfolioDriftAnalysis,
) -> str:
    perf_bits: list[str] = []
    d = performance.total_gain_loss_dollars
    if d is not None and d > 0:
        perf_bits.append("Your invested holdings are above recorded cost basis")
    elif d is not None and d < 0:
        perf_bits.append("Your invested holdings are below recorded cost basis")
    if primary.code == "preserve_liquidity":
        shortfall = float(primary.evidence.get("protected_shortfall") or cash_class.protected_shortfall or 0)
        target = float(primary.evidence.get("protected_cash_target") or cash_class.protected_cash_target or 0)
        lead = (
            f"If I could change only one thing, I would first increase protected cash by about {_money(shortfall)} "
            f"to reach the {_money(target)} emergency and near-term reserve target in your plan."
        )
        tail_parts = perf_bits + [
            "no urgent sale or major portfolio restructuring is indicated",
        ]
        if cash_class.protected_shortfall <= 0:
            tail_parts = perf_bits + ["monitoring may be appropriate"]
        after = (
            f" Once the reserve gap is covered, future contributions can gradually "
            f"{_underweight_follow_on(drift)}."
        )
        return f"{lead} {'; '.join(tail_parts).capitalize() if tail_parts else ''}.{after}"

    if perf_bits:
        return f"{' '.join(perf_bits)}. See **Highest-Priority Change** below for the one action that matters most now."
    return "See **Highest-Priority Change** below for the single action that matters most now."


def format_later_step_suggestions(
    recommendations: RealPortfolioRecommendationSet,
    primary: RealPortfolioRecommendation,
    snapshot: RealPortfolioSnapshot,
    *,
    suggestion_text_for: Callable[[RealPortfolioRecommendation], str],
) -> str:
    lines: list[str] = []
    secondary: list[RealPortfolioRecommendation] = []
    for rec in recommendations.recommendations:
        if rec.code == primary.code or rec.code in _CO_PRIMARY_SKIP:
            continue
        if rec.code == "refresh_market_data" and not market_data_needs_refresh(snapshot):
            continue
        secondary.append(rec)
    if not secondary:
        lines.append(
            "No other changes are co-primary; focus on the highest-priority change above before acting on drift or holdings."
        )
        return "\n".join(lines)
    lines.append("**Later steps (not equal priorities):**")
    for rec in secondary:
        text = suggestion_text_for(rec)
        lines.append(f"- {text}")
    return "\n".join(lines)
