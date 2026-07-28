"""Asset allocation instant reasoning engine (P2)."""

from __future__ import annotations

from typing import Any

from investment_ami_answer_format import build_allocation_sections
from investment_ami_exposure import (
    format_portfolio_weights_table,
    format_tech_exposure_calculation_chain,
    resolve_tech_exposure,
)
from investment_ami_instant_solver import InvestmentSolverResult, _portfolio_label, _weight_rows
from investment_ami_macro import allocation_profile_from_ctx

import investment_ami_allocation as _alloc
from investment_ami.engines.base import InstantEngineRequest
from investment_ami.engines.portfolio_concentration import assess_concentration_from_rows

_ENGINE_ID = "allocation_recommendation"


def run_allocation_recommendation(
    ctx: dict[str, Any],
    *,
    beginner: bool,
    question: str = "",
    engine_id: str = _ENGINE_ID,
) -> InvestmentSolverResult:
    """Portfolio-specific increase / reduce / hold / monitor / rebalance guidance."""
    base_rows = _weight_rows(ctx)
    rows = _alloc._rows_with_allocation_overrides(ctx)
    ctx_adj = _alloc._ctx_with_adjusted_weights(ctx, rows)
    risk_tolerance = _alloc._risk_tolerance_from_ctx(ctx)
    focus = _alloc._parse_recommendation_focus(question)
    mentioned = _alloc._tickers_mentioned_in_question(question)
    drift = ctx.get("rebalance_drift")

    if not rows:
        direct = "Add holdings with weights first — I need your portfolio mix before I can recommend changes."
        sections = build_allocation_sections(
            direct_answer=direct,
            portfolio_analyst_view="Recommendations combine concentration, diversification, exposure, and macro stress signals.",
            recommended_actions="Enter tickers and weights, then ask again.",
            risk_notes=_alloc._allocation_risk_notes(beginner),
            beginner=beginner,
        )
        return InvestmentSolverResult(
            short_answer=direct,
            analyst_sections=sections,
            problem_type="allocation_recommendation",
            model_name="Allocation recommendation analyst",
            confidence_pct=55,
            computed={"ami_engine_id": engine_id},
        )

    profile = allocation_profile_from_ctx(ctx_adj)
    exposure = resolve_tech_exposure(ctx_adj)
    tech_pct = float(exposure.get("total_pct") or 0)
    concentration = assess_concentration_from_rows(rows)
    top_ticker = concentration.top_ticker
    top_pct = concentration.top_pct
    top3 = concentration.top3_pct
    recs = _alloc._sleeve_recommendations(
        ctx_adj,
        rows,
        profile=profile,
        tech_pct=tech_pct,
        risk_tolerance=risk_tolerance,
        focus=focus,
        mentioned=mentioned,
    )
    strengths = _alloc._build_strengths(rows, profile, n_holdings=len(rows))
    weaknesses = _alloc._build_weaknesses(rows, profile, tech_pct=tech_pct, top3=top3, risk_tolerance=risk_tolerance)

    alloc_label = ", ".join(f"**{t}** {p:.1f}%" for t, p in rows[:6])
    reduce_recs = [r for r in recs if r.action in ("reduce", "rebalance")]
    increase_recs = [r for r in recs if r.action == "increase"]
    hold_recs = [r for r in recs if r.action == "hold"]
    monitor_recs = [r for r in recs if r.action == "monitor"]

    rebalance_lead = _alloc._rebalance_verdict(
        focus=focus,
        recs=recs,
        drift=drift,
        top3=top3,
        risk_tolerance=risk_tolerance,
    )
    if rebalance_lead:
        direct = rebalance_lead
    elif focus == "reasonable":
        if weaknesses:
            verdict = "reasonable with caveats" if len(weaknesses) <= 2 else "aggressive for your stated tolerance"
        else:
            verdict = "reasonable for a growth-oriented ETF mix"
        direct = f"Your allocation ({alloc_label}) looks **{verdict}** under a **{risk_tolerance}** lens."
    elif focus == "add" and mentioned:
        direct = (
            f"On adding **{mentioned[0]}**: current weight **{next((p for t, p in rows if t == mentioned[0]), 0):.1f}%**. "
            + (increase_recs[0].rationale if increase_recs else "Size any add against your target mix and overlap with existing sleeves.")
        )
    elif focus == "reduce" and mentioned:
        direct = (
            f"On reducing **{mentioned[0]}**: "
            + (reduce_recs[0].rationale if reduce_recs else "Trim toward your objective weight if drift exceeds your band.")
        )
    elif reduce_recs and risk_tolerance == "Conservative":
        direct = (
            f"For **{risk_tolerance}** goals, consider **reducing** **{reduce_recs[0].ticker}** "
            f"and adding defensive sleeves — tech exposure is **~{tech_pct:.1f}%**, top-3 **{top3:.1f}%**."
        )
    elif increase_recs and not _alloc.has_defensive_row(rows):
        direct = (
            f"Main gap: **defensive ballast**. Your mix ({alloc_label}) is equity-heavy — "
            f"consider **increasing** **{increase_recs[0].ticker}** while **monitoring** growth sleeves."
        )
    else:
        primary = reduce_recs or monitor_recs or hold_recs or recs
        verb = primary[0].action if primary else "monitor"
        direct = (
            f"Portfolio ({alloc_label}): primary guidance is **{verb}** — "
            f"{primary[0].rationale if primary else 'review targets vs current weights.'}"
        )

    if beginner:
        analyst = (
            f"1) **Data:** {alloc_label}; tech exposure ~**{tech_pct:.1f}%**; top-3 **{top3:.1f}%**. "
            f"2) **Meaning:** {'; '.join(weaknesses[:2]) if weaknesses else 'Mix is balanced across fund sleeves.'} "
            f"3) **Action:** Use increase/reduce/hold/monitor/rebalance tags below — not market timing."
        )
    else:
        analyst = (
            f"**Data scan** ({_portfolio_label(ctx_adj)}): tech **{tech_pct:.1f}%** "
            f"(direct **{float(exposure.get('direct_pct') or 0):.1f}%**, embedded **{float(exposure.get('embedded_pct') or 0):.1f}%**); "
            f"top sleeve **{top_ticker}** **{top_pct:.1f}%**; top-3 **{top3:.1f}%**; "
            f"risk tolerance **{risk_tolerance}**. "
            "Signals aggregated from concentration, diversification, exposure, and macro stress modules."
        )

    increases = _alloc._format_action_lines(recs, {"increase"}) or "- **HOLD** current sleeves — no urgent adds flagged."
    reductions = _alloc._format_action_lines(recs, {"reduce", "rebalance"}) or "- **HOLD** — no trim/rebalance urgency at current weights."
    if monitor_recs:
        reductions += ("\n" if reductions else "") + _alloc._format_action_lines(recs, {"monitor"})

    tradeoffs = (
        "**Reduce growth / top sleeves** → lower volatility and recession sensitivity, but may lag in rallies.\n"
        "**Add defensive or diversify** → smoother drawdowns, but lower expected upside.\n"
        "**Hold current mix** → keeps your factor bets intact if they match your goal and horizon."
    )

    actions: list[str] = []
    for r in recs[:4]:
        actions.append(f"**{r.action.upper()}** **{r.ticker}**: {r.rationale}")
    objective = str(ctx.get("objective") or "").strip()
    if objective:
        actions.append(f"Align changes with objective: **{objective}**.")
    if not actions:
        actions.append("**MONITOR** weights quarterly; **rebalance** when drift exceeds ~3–5 pp vs targets.")

    sim = _alloc._simulated_impact_summary(base_rows, rows, ctx)
    what_if = sim if sim and not beginner else ""
    portfolio_changed = _alloc._portfolio_rows_differ(base_rows, rows)
    comparison_table = _alloc._format_before_after_comparison_table(base_rows, rows, ctx) if portfolio_changed and not beginner else ""
    net_changes = _alloc.format_net_allocation_changes(base_rows, rows) if portfolio_changed else ""
    scenario_params = dict(ctx.get("scenario_params") or {})
    overrides_raw = scenario_params.get("allocation_overrides")
    funding_breakdown = ""
    if portfolio_changed and isinstance(overrides_raw, dict) and overrides_raw:
        funding_breakdown = _alloc.format_funding_breakdown(
            {t: p for t, p in base_rows},
            {str(k).upper(): float(v) for k, v in overrides_raw.items()},
            scenario_params,
        )

    base_exposure = resolve_tech_exposure(_alloc._ctx_with_adjusted_weights(ctx, base_rows))
    calc_chain = format_tech_exposure_calculation_chain(base_exposure)
    if portfolio_changed and not beginner:
        adj_exposure = resolve_tech_exposure(ctx_adj)
        adj_chain = format_tech_exposure_calculation_chain(adj_exposure)
        if adj_chain:
            calc_chain = (calc_chain + "\n\n**Proposed mix**\n" + adj_chain).strip()

    methodology = (
        "Signals: concentration bands (top sleeve / top-3), technology exposure (direct + embedded), "
        "defensive sleeve presence, health rebalance drift, and macro recession sensitivity. "
        "Allocation slider scenarios use **explicit reallocation** — freed weight goes only where you designate."
    )
    assumptions_text = (
        f"Risk tolerance: **{risk_tolerance}**. "
        "ETF technology weights use fund sector data or static fallbacks. "
        "Illustrative impacts only — not trade instructions."
    )
    rebalance_block = _alloc._format_rebalance_candidates(recs) if focus == "rebalance" or any(
        r.action == "rebalance" for r in recs
    ) else ""

    sections = build_allocation_sections(
        direct_answer=direct,
        portfolio_analyst_view=analyst,
        current_portfolio=format_portfolio_weights_table(base_rows),
        proposed_portfolio=format_portfolio_weights_table(rows) if portfolio_changed else "",
        portfolio_comparison=comparison_table,
        net_allocation_changes=net_changes,
        funding_breakdown=funding_breakdown,
        current_strengths="\n".join(f"- {s}" for s in strengths),
        current_weaknesses="\n".join(f"- {w}" for w in weaknesses) if weaknesses else "- No major structural flags at current weights.",
        potential_increases=increases,
        potential_reductions=reductions,
        rebalance_candidates=rebalance_block,
        tradeoffs=tradeoffs,
        what_if_scenarios=what_if,
        recommended_actions=" ".join(actions[:3]),
        risk_notes=_alloc._allocation_risk_notes(beginner),
        calculation_chains=calc_chain,
        methodology=methodology if not beginner else "",
        assumptions=assumptions_text,
        beginner=beginner,
    )

    return InvestmentSolverResult(
        short_answer=direct,
        analyst_sections=sections,
        problem_type="allocation_recommendation",
        model_name="Allocation recommendation analyst",
        math_idea="Multi-signal portfolio review → per-sleeve increase/reduce/hold/monitor/rebalance.",
        confidence_pct=84 if rows else 60,
        computed={
            "risk_tolerance": risk_tolerance,
            "tech_exposure_pct": round(tech_pct, 1),
            "top3_pct": round(top3, 1),
            "holdings_weights": {t: round(p, 1) for t, p in rows},
            "recommendations": [{"ticker": r.ticker, "action": r.action, "weight_pct": r.weight_pct} for r in recs],
            "ami_engine_id": engine_id,
        },
    )


class AssetAllocationEngine:
    engine_id = _ENGINE_ID

    def solve(self, request: InstantEngineRequest) -> InvestmentSolverResult:
        return run_allocation_recommendation(
            dict(request.context or {}),
            beginner=bool(request.beginner),
            question=str(request.question or ""),
            engine_id=self.engine_id,
        )


_DEFAULT_ENGINE = AssetAllocationEngine()


def get_asset_allocation_engine() -> AssetAllocationEngine:
    return _DEFAULT_ENGINE
