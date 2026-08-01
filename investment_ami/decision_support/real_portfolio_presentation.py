"""User-facing presentation for the Real Portfolio Advisor (Phase D)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from investment_ami.decision_support.models import DecisionSupportResponse
from investment_ami.decision_support.modules import MODULE_REAL_PORTFOLIO
from investment_ami.decision_support.real_portfolio_cash_classification import (
    RealPortfolioCashClassification,
    classify_real_portfolio_cash,
)
from investment_ami.decision_support.real_portfolio_concentration import RealPortfolioConcentrationAnalysis
from investment_ami.decision_support.real_portfolio_drift import RealPortfolioDriftAnalysis
from investment_ami.decision_support.real_portfolio_models import RealPortfolioSnapshot
from investment_ami.decision_support.real_portfolio_performance import (
    METRIC_LABEL_UNREALIZED,
    METRIC_TOOLTIP_UNREALIZED,
    RealPortfolioPerformanceAnalysis,
    unrealized_gain_loss_phrase,
)
from investment_ami.decision_support.real_portfolio_recommendations import (
    RealPortfolioRecommendation,
    RealPortfolioRecommendationSet,
)

_RECOMMENDATION_COPY: dict[str, str] = {
    "refresh_market_data": "Refresh market prices before relying on portfolio-wide return figures.",
    "define_target_allocation": "Define a target asset allocation before making a formal rebalancing decision.",
    "direct_new_contributions_underweight": "Direct new contributions toward the most underweight target asset class.",
    "rebalance_with_new_money": "Use future contributions to reduce drift gradually before considering sales.",
    "review_material_single_security": "Review whether the size of a concentrated position still matches the role you intended for it.",
    "review_thematic_etf_concentration": "Review thematic or sector ETF exposure; many holdings can still share one theme.",
    "review_asset_class_overweight": "Review asset-class overweight versus your target allocation.",
    "preserve_liquidity": "Preserve sufficient cash for near-term needs before increasing portfolio risk.",
    "hold_current_course": "No urgent portfolio change is indicated by the available data.",
    "no_urgent_change": "The current evidence supports monitoring rather than making an immediate change.",
    "review_negative_cash": "Review transaction history and funding — the ledger shows a negative cash balance.",
    "add_missing_cost_basis": "Add or correct cost basis in your transaction history before relying on gain/loss figures.",
    "insufficient_data": "More information is needed before a target-based placement recommendation is available.",
    "reduce_contribution_temporarily": "Consider pausing or lowering new investments until liquidity needs are covered.",
}

_INFO_LABELS: dict[str, str] = {
    "explicit_target_allocation": "An explicit target asset allocation saved for this portfolio",
    "monthly_contribution_capacity": "Your intended monthly contribution capacity",
    "updated_market_prices": "Updated market prices for holdings missing quotes",
    "missing_cost_basis": "Cost basis for holdings with incomplete transaction history",
    "protected_vs_investable_cash": (
        "Which portion of your ledger cash balance is reserved for emergencies or near-term spending "
        "versus available for long-term investing"
    ),
}


def _money(x: float) -> str:
    return f"${x:,.0f}"


def _pct(x: float) -> str:
    return f"{x:.1f}%"


@dataclass(frozen=True)
class RealPortfolioPresentation:
    assessment: str
    portfolio_snapshot: str
    performance_drivers: str
    allocation_concentration: str
    suggestions: str
    trade_offs: str
    information_needed: str
    confidence: str
    module_label: str = "Real Portfolio Advisor"
    recommendation_codes: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


def _format_contributors(performance: RealPortfolioPerformanceAnalysis, *, limit: int = 3) -> str:
    lines: list[str] = []
    if performance.positive_contributors:
        lines.append("**Largest positive contributors:**")
        for c in performance.positive_contributors[:limit]:
            d = c.contribution_to_total_gain_loss_dollars
            if d is None:
                continue
            lines.append(f"- **{c.ticker}**: approximately {_money(d)} of unrealized gain.")
    if performance.negative_contributors:
        if lines:
            lines.append("")
        lines.append("**Largest negative contributors:**")
        for c in performance.negative_contributors[:limit]:
            d = c.contribution_to_total_gain_loss_dollars
            if d is None:
                continue
            lines.append(f"- **{c.ticker}**: approximately {_money(abs(d))} of unrealized loss.")
    return "\n".join(lines)


def _inferred_target_summary(drift: RealPortfolioDriftAnalysis) -> str:
    alloc = drift.target_allocation or {}
    eq = alloc.get("Equity")
    bd = alloc.get("Bonds")
    ca = alloc.get("Cash_and_TBills") or alloc.get("Cash")
    if eq is not None and bd is not None and ca is not None:
        return f"{eq:.0f}/{bd:.0f}/{ca:.0f}"
    parts = [f"{k} {_pct(v)}" for k, v in sorted(alloc.items(), key=lambda kv: -kv[1])]
    return ", ".join(parts) if parts else "your saved or inferred target"


def _top_contributor_phrases(performance: RealPortfolioPerformanceAnalysis) -> str:
    chunks: list[str] = []
    if performance.positive_contributors:
        c = performance.positive_contributors[0]
        d = c.contribution_to_total_gain_loss_dollars
        if d is not None and d > 0:
            chunks.append(f"**{c.ticker}** is the main positive contributor")
    if performance.negative_contributors:
        c = performance.negative_contributors[0]
        d = c.contribution_to_total_gain_loss_dollars
        if d is not None and d < 0:
            if chunks:
                chunks.append(
                    f"while **{c.ticker}** has a small unrealized loss of approximately {_money(abs(d))}"
                )
            else:
                chunks.append(
                    f"**{c.ticker}** is the main negative contributor "
                    f"(approximately {_money(abs(d))} unrealized loss)"
                )
    if not chunks:
        return ""
    if len(chunks) == 1:
        return chunks[0] + "."
    return f"{chunks[0]}, {chunks[1]}."


def _unrealized_headline(performance: RealPortfolioPerformanceAnalysis) -> str:
    d = performance.total_gain_loss_dollars
    if d is None:
        return ""
    pct = performance.total_gain_loss_pct
    if pct is None:
        pct = performance.priced_holdings_gain_loss_pct
    if d > 0:
        line = f"Your portfolio has an unrealized gain of approximately {_money(d)}"
        if pct is not None:
            line += f", or {_pct(pct)},"
        line += " since purchase (not today's return)."
        return line
    if d < 0:
        line = f"Your portfolio has an unrealized loss of approximately {_money(abs(d))}"
        if pct is not None:
            line += f", or {_pct(abs(pct))},"
        line += " since purchase (not today's return)."
        return line
    return ""


def _build_informative_assessment(
    performance: RealPortfolioPerformanceAnalysis,
    recommendations: RealPortfolioRecommendationSet,
    cash_class: RealPortfolioCashClassification,
) -> str:
    sentences: list[str] = []
    headline = _unrealized_headline(performance)
    if headline:
        sentences.append(headline)
    contributor = _top_contributor_phrases(performance)
    if contributor:
        sentences.append(contributor)
    urgent_codes = {
        r.code
        for r in recommendations.recommendations
        if r.priority <= 30 and r.code not in ("preserve_liquidity",)
    }
    if not urgent_codes and recommendations.primary_action in (
        "hold_current_course",
        "no_urgent_change",
        "preserve_liquidity",
    ):
        urgent = "No urgent portfolio change is indicated"
    elif not urgent_codes:
        urgent = "No urgent portfolio change is indicated"
    else:
        urgent = "Review the highlighted items below before making changes"
    if cash_class.protected_shortfall > 0:
        urgent += (
            f", but your current ledger cash is about {_money(cash_class.protected_shortfall)} below "
            "the emergency and near-term reserve target entered in your plan"
        )
    urgent += "."
    sentences.append(urgent)
    return " ".join(sentences)


def _format_confidence_narrative(
    *,
    conf_label: str,
    snapshot: RealPortfolioSnapshot,
    drift: RealPortfolioDriftAnalysis,
    cash_class: RealPortfolioCashClassification,
    score: int | None,
) -> str:
    body = f"**{conf_label}**"
    if score:
        body += f" (score {score}/100)"
    strengths: list[str] = []
    if snapshot.unpriced_holdings_count == 0:
        strengths.append("all holdings are priced")
    incomplete_cb = any(
        h.total_cost_basis <= 0 and h.current_price is not None for h in snapshot.holdings
    )
    if not incomplete_cb and snapshot.total_cost_basis > 0:
        strengths.append("cost basis is available")
    limitations: list[str] = []
    if drift.target_source == "inferred_risk_profile_target" or drift.target_quality not in (
        "explicit",
        "sufficient",
    ):
        limitations.append("the target allocation is inferred")
    if cash_class.portfolio_cash > 0:
        limitations.append(
            "the ledger does not yet distinguish protected cash from cash available for long-term investing"
        )
    level_word = conf_label.lower()
    if limitations:
        if strengths:
            body += (
                f"\n\nConfidence is {level_word} because "
                f"{' and '.join(strengths)}, but {' and '.join(limitations)}."
            )
        else:
            body += f"\n\nConfidence is limited because {' and '.join(limitations)}."
    elif strengths:
        body += f"\n\n{' and '.join(strengths).capitalize()} support this read."
    else:
        body += "\n\nPricing and plan inputs support this read."
    return body


def _allocation_concentration_block(
    snapshot: RealPortfolioSnapshot,
    concentration: RealPortfolioConcentrationAnalysis,
    drift: RealPortfolioDriftAnalysis,
) -> str:
    lines: list[str] = []
    if concentration.largest_holding:
        lines.append(
            f"- Largest position: **{concentration.largest_holding.ticker}** "
            f"({_pct(concentration.largest_holding_weight)} of marked value)."
        )
    lines.append(f"- Top three positions: **{_pct(concentration.top_three_weight)}** of marked value.")
    lines.append(f"- Top five positions: **{_pct(concentration.top_five_weight)}** of marked value.")
    ac = snapshot.allocation_by_asset_class or {}
    if ac:
        parts = [f"{k} {_pct(v)}" for k, v in sorted(ac.items(), key=lambda kv: -kv[1]) if v > 0]
        if parts:
            lines.append("- Asset-class mix (ledger buckets): " + ", ".join(parts) + ".")
            if float(ac.get("Other", 0)) > 0:
                lines.append(
                    "- **Other / uncategorized** sleeve weights are shown separately; "
                    "they are not automatically treated as bonds without holding-level metadata."
                )
    for obs in concentration.observations:
        if obs.code == "material_single_security_weight":
            lines.append(
                f"- **{obs.ticker}** at {_pct(obs.value or 0)} is a materially large **individual security** "
                "— company-specific concentration risk, not the same as a broad fund at that weight."
            )
        elif obs.code == "broad_market_etf_weight":
            lines.append(
                f"- **{obs.ticker}** appears to be a **broad-market ETF** at {_pct(obs.value or 0)}; "
                "that weight is not equivalent to holding the same percentage in one company."
            )
        elif obs.code == "narrow_or_thematic_etf_weight":
            lines.append(
                f"- **{obs.ticker}** is a **thematic or sector ETF** at {_pct(obs.value or 0)}; "
                "it may still represent concentrated theme exposure."
            )
        elif obs.code == "unknown_security_type":
            lines.append(
                f"- Security type for **{obs.ticker}** is uncertain; concentration interpretation is limited."
            )
    if drift.target_source != "unavailable" and drift.observations:
        lines.append("- Target drift (percentage points vs saved/inferred target):")
        for o in drift.observations:
            if o.severity == "immaterial":
                continue
            lines.append(
                f"  - {o.asset_class}: current {_pct(o.current_weight)}, target {_pct(o.target_weight)} "
                f"({o.drift_percentage_points:+.1f} pp, {o.severity})."
            )
        lines.append(
            "- These drift figures describe the full ledger allocation. Because part of the cash balance "
            "may be reserved rather than investable, they should not automatically be treated as rebalancing instructions."
        )
        if drift.target_source == "inferred_risk_profile_target":
            lines.append(
                "- Target comparison uses an **inferred** objective mapping; save an explicit target for stronger drift guidance."
            )
    return "\n".join(lines)


def build_no_ledger_presentation(*, question: str) -> RealPortfolioPresentation:
    assessment = (
        "No transaction-backed real portfolio is available yet. "
        "AMI cannot evaluate your **actual** owned holdings from the weight-based model portfolio alone."
    )
    snapshot = (
        "Enter or import **portfolio transactions** (buys, sells, deposits) in the Real Portfolio workflow "
        "so AMI can mark positions from your ledger."
    )
    suggestions = (
        "- Record actual transactions before asking for real performance, concentration, or drift answers.\n"
        "- The holdings editor and presets describe a **model** portfolio — not a silent substitute for your ledger."
    )
    return RealPortfolioPresentation(
        assessment=assessment,
        portfolio_snapshot=snapshot,
        performance_drivers="",
        allocation_concentration="",
        suggestions=suggestions,
        trade_offs="",
        information_needed="Transaction-backed portfolio history (`portfolio_transactions`).",
        confidence="**Low** — no real ledger to analyze.\n\nConfidence is low because no transaction-backed portfolio exists.",
        metadata={"no_ledger": True, "question": question},
    )


def build_assessment_text(
    performance: RealPortfolioPerformanceAnalysis,
    concentration: RealPortfolioConcentrationAnalysis,
    drift: RealPortfolioDriftAnalysis,
    recommendations: RealPortfolioRecommendationSet,
    *,
    snapshot: RealPortfolioSnapshot | None = None,
    cash_class: RealPortfolioCashClassification | None = None,
) -> str:
    if performance.performance_status == "partial_data":
        return (
            "The portfolio **cannot be evaluated completely** because one or more holdings are missing current prices. "
            "Partial marks and priced-holdings return are shown where available."
        )
    if any(r.code == "review_material_single_security" for r in recommendations.recommendations):
        perf_note = ""
        if performance.performance_status == "positive_unrealized_gain":
            perf_note = " The portfolio is above recorded cost basis on priced holdings, but "
        elif performance.performance_status == "negative_unrealized_loss":
            perf_note = " The portfolio is below recorded cost basis on priced holdings, but "
        return (
            f"{perf_note}the **main issue to review is concentration in an individual security**, "
            "not overall performance alone."
        ).strip()
    if (
        cash_class is not None
        and performance.total_gain_loss_dollars is not None
        and performance.performance_status != "partial_data"
    ):
        return _build_informative_assessment(performance, recommendations, cash_class)
    if drift.rebalance_triggered and snapshot is not None:
        cc = classify_real_portfolio_cash(snapshot, drift)
        if cc.portfolio_cash_weight_pct >= 15.0 and (
            drift.target_source == "inferred_risk_profile_target" or not cc.reserves_fully_funded
        ):
            return (
                f"Your marked portfolio differs substantially from the inferred {_inferred_target_summary(drift)} "
                f"target, mainly because {_pct(cc.portfolio_cash_weight_pct)} is currently cash. "
                "However, part or all of that cash may be reserved for emergencies and near-term needs. "
                "Clarify which portion is investable before treating the full cash balance as allocation drift."
            )
        if cc.reserves_fully_funded:
            return (
                "Protected reserve targets appear fully funded from plan inputs; "
                "directing future contributions or excess cash toward underweight sleeves may be reasonable "
                "rather than selling current holdings."
            )
        return (
            "The portfolio has **materially drifted** from the available target allocation; "
            "separate reserved cash from investable cash before strong rebalancing actions."
        )
    if drift.rebalance_triggered:
        return (
            "The portfolio has **materially drifted** from the available target allocation; "
            "gradual rebalancing with new contributions may be reasonable if liquidity allows."
        )
    return "Here is a factual read of your transaction-backed portfolio based on available marks and plan context."


def build_real_portfolio_presentation(
    *,
    question: str,
    snapshot: RealPortfolioSnapshot,
    performance: RealPortfolioPerformanceAnalysis,
    concentration: RealPortfolioConcentrationAnalysis,
    drift: RealPortfolioDriftAnalysis,
    recommendations: RealPortfolioRecommendationSet,
) -> RealPortfolioPresentation:
    cash_class = classify_real_portfolio_cash(snapshot, drift)
    assessment = build_assessment_text(
        performance, concentration, drift, recommendations, snapshot=snapshot, cash_class=cash_class
    )

    snap_lines = [
        f"- **Total marked value:** {_money(snapshot.total_market_value)}"
        + (" (partial — excludes unpriced holdings)" if snapshot.unpriced_holdings_count else ""),
        f"- **Recorded cost basis (open positions):** {_money(snapshot.total_cost_basis)}",
    ]
    if performance.total_gain_loss_dollars is not None:
        d = performance.total_gain_loss_dollars
        snap_lines.append(
            f"- **{unrealized_gain_loss_phrase(d)}:** {_money(abs(d) if d < 0 else d)}."
        )
    if performance.total_gain_loss_pct is not None:
        snap_lines.append(f"- **Unrealized gain/loss % (complete):** {_pct(performance.total_gain_loss_pct)}.")
    elif performance.priced_holdings_gain_loss_pct is not None:
        snap_lines.append(
            f"- **Priced-holdings unrealized return:** {_pct(performance.priced_holdings_gain_loss_pct)} "
            "(holdings with valid prices only)."
        )
    snap_lines.append(f"- **Holdings:** {len(snapshot.holdings)} securities (+ cash when present).")
    snap_lines.append(f"- **Market data status:** {snapshot.market_data_status}.")
    if snapshot.unpriced_holdings_count:
        snap_lines.append(f"- **Missing prices:** {snapshot.unpriced_holdings_count} holding(s) unpriced.")
    if snapshot.as_of:
        snap_lines.append(f"- **Snapshot as of (UTC):** {snapshot.as_of.isoformat(timespec='seconds')}.")

    snap_lines.append(f"- **Portfolio cash (ledger):** {_money(cash_class.portfolio_cash)}.")
    if cash_class.cash_purpose_known:
        snap_lines.append(
            f"- **Protected cash target (plan):** approximately {_money(cash_class.protected_cash_target)}."
        )
        if cash_class.protected_shortfall > 0:
            snap_lines.append(
                f"- **Reserve funding gap:** about {_money(cash_class.protected_shortfall)} below that target."
            )
        elif cash_class.investable_cash is not None:
            snap_lines.append(
                f"- **Investable cash (above reserves):** approximately {_money(cash_class.investable_cash)}."
            )
    if cash_class.target_portfolio_cash_allocation_pct is not None:
        snap_lines.append(
            f"- **Target portfolio cash allocation:** "
            f"{_pct(cash_class.target_portfolio_cash_allocation_pct)} "
            f"(distinct from reserve needs; current ledger cash weight {_pct(cash_class.portfolio_cash_weight_pct)})."
        )

    perf_block = _format_contributors(performance)
    alloc_block = _allocation_concentration_block(snapshot, concentration, drift)

    sug_lines: list[str] = []
    for rec in recommendations.recommendations:
        text = _RECOMMENDATION_COPY.get(rec.code, rec.title)
        if rec.code == "preserve_liquidity":
            shortfall = rec.evidence.get("protected_shortfall")
            if shortfall is not None and float(shortfall) > 0:
                target = cash_class.protected_cash_target
                text = (
                    f"Your current portfolio cash is about {_money(float(shortfall))} below the combined "
                    "emergency and near-term reserve target entered in your plan. Until that gap is addressed, "
                    "increasing new investment contributions may reduce liquidity below your stated target.\n\n"
                    f"Before increasing long-term investments, consider bringing protected cash closer to the "
                    f"{_money(target)} target. Once those reserves are adequately funded, future contributions "
                    "could be directed gradually toward underweight equity and bond sleeves rather than selling "
                    "current holdings."
                )
        if rec.code == "rebalance_with_new_money":
            if rec.evidence.get("conditional_only"):
                target = _inferred_target_summary(drift)
                text = (
                    f"Your marked portfolio differs substantially from the inferred {target} target, mainly because "
                    f"{_pct(cash_class.portfolio_cash_weight_pct)} is currently cash. However, part or all of that "
                    "cash may be reserved for emergencies and near-term needs. Clarify which portion is investable "
                    "before treating the full cash balance as allocation drift."
                )
            elif cash_class.reserves_fully_funded:
                text = (
                    "Direct future contributions or excess cash toward underweight equity and bond sleeves "
                    "rather than selling current holdings."
                )
        if rec.code == "review_material_single_security" and rec.evidence.get("ticker"):
            text = (
                f"Review whether the size of **{rec.evidence['ticker']}** still matches the role you intended "
                "for it (review — not a sell instruction)."
            )
        sug_lines.append(f"- {text}")
    suggestions = "\n".join(sug_lines)

    trade_offs = "\n".join(f"- {t}" for t in recommendations.tradeoffs)

    info_lines = [
        _INFO_LABELS.get(k, k.replace("_", " "))
        for k in recommendations.information_needed
        if k not in _present_info_skip(snapshot, recommendations)
    ]
    for key in recommendations.information_needed:
        if key == "protected_vs_investable_cash" and cash_class.portfolio_cash > 0:
            info_lines = [
                x
                for x in info_lines
                if "Which portion" not in x
            ]
            info_lines.append(
                f"Which portion of the {_money(cash_class.portfolio_cash)} cash balance is reserved for "
                "emergencies or near-term spending versus available for long-term investing?"
            )
            break
    information_needed = "\n".join(f"- {x}" for x in dict.fromkeys(info_lines))

    conf = recommendations.confidence_level.title()
    if recommendations.confidence_level == "high" and (
        snapshot.unpriced_holdings_count
        or drift.target_source in ("inferred_risk_profile_target", "unavailable")
        or cash_class.portfolio_cash > 0
    ):
        conf = "Medium"
    if drift.target_source == "inferred_risk_profile_target" or cash_class.portfolio_cash > 0:
        if conf == "High":
            conf = "Medium"
    conf_body = _format_confidence_narrative(
        conf_label=conf,
        snapshot=snapshot,
        drift=drift,
        cash_class=cash_class,
        score=recommendations.confidence_score or None,
    )

    return RealPortfolioPresentation(
        assessment=assessment,
        portfolio_snapshot="\n".join(snap_lines),
        performance_drivers=perf_block,
        allocation_concentration=alloc_block,
        suggestions=suggestions,
        trade_offs=trade_offs,
        information_needed=information_needed,
        confidence=conf_body,
        recommendation_codes=tuple(r.code for r in recommendations.recommendations),
        metadata={
            "metric_label": METRIC_LABEL_UNREALIZED,
            "metric_tooltip_unrealized": METRIC_TOOLTIP_UNREALIZED,
            "cash_classification": {
                "portfolio_cash": cash_class.portfolio_cash,
                "protected_cash_target": cash_class.protected_cash_target,
                "protected_shortfall": cash_class.protected_shortfall,
                "investable_cash": cash_class.investable_cash,
                "target_portfolio_cash_allocation_pct": cash_class.target_portfolio_cash_allocation_pct,
            },
        },
    )


def _present_info_skip(
    snapshot: RealPortfolioSnapshot,
    recommendations: RealPortfolioRecommendationSet,
) -> set[str]:
    skip: set[str] = set()
    if snapshot.monthly_contribution is not None:
        skip.add("monthly_contribution_capacity")
    if drift_has_target(recommendations):
        skip.add("explicit_target_allocation")
    if snapshot.unpriced_holdings_count == 0:
        skip.add("updated_market_prices")
    return skip


def drift_has_target(recommendations: RealPortfolioRecommendationSet) -> bool:
    return "define_target_allocation" not in {r.code for r in recommendations.recommendations}


def presentation_to_decision_support_response(
    presentation: RealPortfolioPresentation,
    *,
    question: str,
    recommendations: RealPortfolioRecommendationSet | None = None,
) -> DecisionSupportResponse:
    recs = recommendations or RealPortfolioRecommendationSet(
        primary_action="insufficient_data",
        recommendations=(),
        urgency="low",
        recommendation_status="insufficient_data",
        confidence_level="low",
        confidence_score=0,
        supporting_facts=(),
        tradeoffs=(),
        information_needed=(),
    )
    info_list = [presentation.information_needed] if presentation.information_needed else []
    return DecisionSupportResponse(
        module_id=MODULE_REAL_PORTFOLIO,
        question=question,
        facts=[presentation.portfolio_snapshot] if presentation.portfolio_snapshot else [],
        observations=[x for x in (presentation.performance_drivers, presentation.allocation_concentration) if x],
        concerns=[],
        suggested_actions=[presentation.suggestions] if presentation.suggestions else [],
        trade_offs=[presentation.trade_offs] if presentation.trade_offs else [],
        confidence=recs.confidence_level,  # type: ignore[arg-type]
        limitations=[],
        assessment=presentation.assessment,
        information_needed=info_list,
        confidence_pct=recs.confidence_score or 40,
        confidence_note=presentation.confidence,
        information_needed_markdown=presentation.information_needed,
    )


def render_real_portfolio_analyst_sections(
    presentation: RealPortfolioPresentation,
    *,
    question: str,
) -> dict[str, str]:
    from investment_ami_context import normalize_insight_question_text

    q_clean = normalize_insight_question_text(question)
    disclaimer = (
        "*Educational guidance only — not personal financial advice. "
        "Verify numbers and consult a qualified professional for your situation.*"
    )
    sections: dict[str, str] = {
        "insights_layout": "real_portfolio_advisor",
        "ami_module_name": presentation.module_label,
        "question_text": q_clean,
        "direct_answer": presentation.assessment,
        "portfolio_snapshot": presentation.portfolio_snapshot,
        "performance_drivers": presentation.performance_drivers,
        "allocation_concentration": presentation.allocation_concentration,
        "recommended_actions": presentation.suggestions,
        "tradeoffs": presentation.trade_offs,
        "risk_notes": presentation.information_needed,
        "methodology": presentation.confidence,
        "assumptions": disclaimer,
    }
    return {k: v for k, v in sections.items() if v and str(v).strip()}


def real_portfolio_to_solver_payload(
    presentation: RealPortfolioPresentation,
    response: DecisionSupportResponse,
    *,
    recommendations: RealPortfolioRecommendationSet,
) -> dict[str, Any]:
    sections = render_real_portfolio_analyst_sections(presentation, question=response.question)
    return {
        "short_answer": response.assessment,
        "math_idea": "",
        "confidence_pct": response.confidence_pct,
        "computed": {
            "ami_engine_id": MODULE_REAL_PORTFOLIO,
            "insights_layout": "real_portfolio_advisor",
            "decision_support_version": "real_portfolio_v1",
            "real_portfolio": {
                "recommendation_codes": list(presentation.recommendation_codes),
                "primary_action": recommendations.primary_action,
                "confidence_level": recommendations.confidence_level,
            },
        },
        "analyst_sections": sections,
    }
