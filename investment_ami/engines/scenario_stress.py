"""Portfolio scenario stress instant reasoning engine (P2)."""

from __future__ import annotations

from typing import Any

from investment_ami_answer_format import build_analyst_sections
from investment_ami_instant_solver import InvestmentSolverResult

from investment_ami.engines.base import InstantEngineRequest
from investment_ami.engines.support.presentation import default_educational_risk_notes
from investment_ami.engines.support.scenario_stress_data import build_scenario_stress_snapshot


def _scenario_stress_solve(ctx: dict[str, Any], *, beginner: bool, question: str = "") -> InvestmentSolverResult:
    snap = build_scenario_stress_snapshot(ctx, question=question)
    tech_dd = snap.tech_drawdown_pct
    rate_shock = snap.rate_shock
    direct_pct = snap.direct_tech_pct
    embedded_pct = snap.embedded_tech_pct
    total_tech_pct = snap.total_tech_pct
    embedded_holdings = list(snap.embedded_holdings)
    bond_pct = snap.bond_defensive_pct
    equity_pct = snap.equity_sleeve_pct
    tech_impact = snap.illustrative_impact_pct

    embedded_bits = ", ".join(
        f"**{h['ticker']}** (~{h.get('contribution_pct', 0):.1f}% tech contribution)"
        for h in embedded_holdings[:3]
    )

    if beginner:
        if direct_pct <= 0 and embedded_pct > 0:
            direct = (
                f"You do not hold a dedicated technology ETF, but embedded tech exposure is about "
                f"**{embedded_pct:.1f}%** of your portfolio. A **{tech_dd:.0f}%** tech drawdown could "
                f"still reduce the portfolio by roughly **{tech_impact:.1f}%** (simple estimate)."
            )
        elif total_tech_pct > 0:
            direct = (
                f"A **{tech_dd:.0f}%** technology drawdown could reduce your portfolio by about "
                f"**{tech_impact:.1f}%** based on **{total_tech_pct:.1f}%** total tech exposure."
            )
        else:
            direct = (
                f"With minimal technology exposure detected, a tech-only **{tech_dd:.0f}%** shock "
                f"would likely have a **small direct impact** — other sectors would matter more."
            )
        analyst = (
            "Technology exposure comes from **direct tech funds** (like QQQ) and **embedded exposure** "
            "inside broad/dividend ETFs (like VTI, SCHD, VYM). Even without a tech ETF, a sector selloff "
            "can still hit your portfolio through those underlying holdings."
        )
        if embedded_bits:
            analyst += f" Largest embedded contributors: {embedded_bits}."
        what_if = (
            f"**Tech drawdown {tech_dd:.0f}%** → ~**{tech_impact:.1f}%** portfolio impact "
            f"(total tech exposure **{total_tech_pct:.1f}%**).\n"
            f"Bond/defensive sleeve **{bond_pct:.1f}%** may offset some equity stress."
        )
    else:
        if direct_pct <= 0 and embedded_pct > 0:
            direct = (
                f"No dedicated tech sleeve; **embedded tech exposure ≈ {embedded_pct:.1f}%**. "
                f"Tech shock **-{tech_dd:.0f}%** → illustrative portfolio impact **~{tech_impact:.1f}%**."
            )
        else:
            direct = (
                f"Tech shock **-{tech_dd:.0f}%** → portfolio impact **~{tech_impact:.1f}%** "
                f"(direct **{direct_pct:.1f}%** + embedded **{embedded_pct:.1f}%** = **{total_tech_pct:.1f}%**)."
            )
        analyst = (
            "Scenario model: portfolio impact ≈ (direct tech weight + Σ fund_weight × tech_sector_weight_in_fund) × shock. "
            "Embedded exposure captures technology holdings inside diversified and dividend ETFs."
        )
        if embedded_bits:
            analyst += f" Top embedded: {embedded_bits}."
        what_if = (
            f"- Direct tech sleeves: **{direct_pct:.1f}%**\n"
            f"- Embedded tech exposure: **{embedded_pct:.1f}%**\n"
            f"- Combined tech exposure: **{total_tech_pct:.1f}%**\n"
            f"- Shock **-{tech_dd:.0f}%** → **~{tech_impact:.1f}%** portfolio\n"
            f"- Equity sleeve **~{equity_pct:.1f}%** | Bond/defensive **{bond_pct:.1f}%**"
            + (f"\n- Rate environment: **{rate_shock}**" if rate_shock else "")
        )

    key_lines = [
        f"- Direct technology ETFs: **{direct_pct:.1f}%**",
        f"- Embedded technology exposure: **{embedded_pct:.1f}%**",
        f"- Total technology exposure (est.): **{total_tech_pct:.1f}%**",
        f"- Bond/defensive: **{bond_pct:.1f}%**",
    ]
    for h in embedded_holdings[:4]:
        key_lines.append(
            f"- **{h['ticker']}**: {h.get('portfolio_weight_pct')}% of portfolio × "
            f"{h.get('tech_weight_in_fund_pct')}% tech in fund ≈ **{h.get('contribution_pct')}%**"
        )

    actions = (
        "If embedded tech exposure is higher than you realized, consider whether your dividend/broad sleeves "
        "already give enough growth tilt — or add defensive assets if tech volatility feels too high."
        if embedded_pct > direct_pct
        else "If tech shock impact exceeds comfort, trim dedicated tech sleeves or rebalance toward targets."
    )

    sections = build_analyst_sections(
        direct_answer=direct,
        portfolio_analyst_view=analyst,
        key_variables="\n".join(key_lines),
        tradeoffs=(
            "**Ignoring embedded exposure** understates tech shock risk in broad/dividend portfolios.\n"
            "**Focusing only on ETF labels** misses underlying sector composition."
        ),
        what_if_scenarios=what_if,
        recommended_actions=actions,
        risk_notes=default_educational_risk_notes(beginner),
        beginner=beginner,
    )
    return InvestmentSolverResult(
        short_answer=direct,
        analyst_sections=sections,
        problem_type="scenario_stress",
        model_name="Portfolio scenario analyst",
        confidence_pct=82 if total_tech_pct > 0 else 68,
        computed={
            "tech_drawdown_pct": tech_dd,
            "direct_tech_pct": round(direct_pct, 2),
            "embedded_tech_pct": round(embedded_pct, 2),
            "total_tech_pct": round(total_tech_pct, 2),
            "illustrative_impact_pct": round(tech_impact, 2),
            "ami_engine_id": "scenario_stress",
        },
    )


class ScenarioStressEngine:
    engine_id = "scenario_stress"

    def solve(self, request: InstantEngineRequest) -> InvestmentSolverResult:
        return _scenario_stress_solve(
            dict(request.context or {}),
            beginner=bool(request.beginner),
            question=str(request.question or ""),
        )


_DEFAULT_ENGINE = ScenarioStressEngine()


def get_scenario_stress_engine() -> ScenarioStressEngine:
    return _DEFAULT_ENGINE
