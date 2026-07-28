"""Diversification instant reasoning engine (P2 reference implementation)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from investment_ami_answer_format import build_analyst_sections
from investment_ami_instant_solver import InvestmentSolverResult, _weight_rows

from investment_ami.engines.base import InstantEngineRequest
from investment_ami.engines.support.presentation import default_educational_risk_notes


@dataclass(frozen=True)
class DiversificationAssessment:
    """Pure diversification metrics (testable without narrative formatting)."""

    judgment: str
    top_class: str
    top_pct: float
    equity_pct: float
    bond_pct: float
    items: tuple[tuple[str, float], ...]
    empty: bool = False


def assess_diversification(context: dict[str, Any]) -> DiversificationAssessment:
    """Compute diversification judgment from asset-class breakdown or weight rows."""
    breakdown = context.get("asset_class_breakdown")
    rows = _weight_rows(context)
    if isinstance(breakdown, dict) and breakdown:
        items = sorted(((k, float(v)) for k, v in breakdown.items()), key=lambda x: x[1], reverse=True)
        top_class, top_pct = items[0]
        equity_pct = sum(p for k, p in items if "equity" in k.lower())
        bond_pct = sum(p for k, p in items if "bond" in k.lower() or "bill" in k.lower())
        n_classes = len(items)
        if top_pct >= 70 or n_classes < 2:
            judgment = "Not fully diversified"
        elif n_classes >= 3 and top_pct < 50:
            judgment = "Yes — moderately diversified"
        elif n_classes >= 2 and top_pct < 60:
            judgment = "Partially diversified — room to improve"
        else:
            judgment = "Moderately diversified with concentration in one sleeve"
        return DiversificationAssessment(
            judgment=judgment,
            top_class=str(top_class),
            top_pct=float(top_pct),
            equity_pct=float(equity_pct),
            bond_pct=float(bond_pct),
            items=tuple(items),
        )
    if rows:
        top_pct = sum(p for _, p in rows)
        return DiversificationAssessment(
            judgment="Partially diversified — single asset-class proxy from weights",
            top_class="Equity (default)",
            top_pct=float(top_pct),
            equity_pct=float(top_pct),
            bond_pct=0.0,
            items=(("Equity (default)", top_pct),),
        )
    return DiversificationAssessment(
        judgment="",
        top_class="",
        top_pct=0.0,
        equity_pct=0.0,
        bond_pct=0.0,
        items=(),
        empty=True,
    )


class DiversificationEngine:
    engine_id = "diversification"

    def solve(self, request: InstantEngineRequest) -> InvestmentSolverResult:
        ctx = dict(request.context or {})
        beginner = bool(request.beginner)
        assessment = assess_diversification(ctx)

        if assessment.empty:
            direct = "Add holdings to assess diversification across asset classes."
            sections = build_analyst_sections(
                direct_answer=direct,
                risk_notes=default_educational_risk_notes(beginner),
                beginner=beginner,
            )
            return InvestmentSolverResult(
                short_answer=direct,
                analyst_sections=sections,
                problem_type="diversification",
                model_name="Diversification analyst",
                confidence_pct=55,
                computed={"ami_engine_id": self.engine_id},
            )

        judgment = assessment.judgment
        top_class = assessment.top_class
        top_pct = assessment.top_pct
        equity_pct = assessment.equity_pct
        bond_pct = assessment.bond_pct
        items = list(assessment.items)

        if beginner:
            direct = (
                f"**{judgment}.** Your mix is led by **{top_class}** at about **{top_pct:.1f}%**."
                + (f" Equities total ~**{equity_pct:.1f}%**." if equity_pct else "")
            )
            analyst = (
                "Diversification means spreading across asset classes (stocks, bonds, real estate, cash) "
                "so one type of market stress does not drive everything."
            )
            if bond_pct < 10 and equity_pct > 70:
                actions = "You are equity-heavy — adding bonds or defensive sleeves can reduce portfolio swings."
            else:
                actions = "Compare this mix to your goal; fill missing asset classes if the balance feels off."
        else:
            direct = (
                f"**{judgment}.** Asset-class mix: **{top_class}** **{top_pct:.1f}%** dominant; "
                f"equity **{equity_pct:.1f}%**, defensive/bond **{bond_pct:.1f}%**."
            )
            analyst = (
                "Diversification quality depends on asset-class balance, geographic spread, and correlation "
                "— not ticker count alone."
            )
            actions = (
                "Use target weights to close gaps in underrepresented asset classes; "
                "monitor effective overlap among equity ETFs."
            )

        key_vars = "\n".join(f"- **{k}**: **{p:.1f}%**" for k, p in items[:6])
        tradeoffs = (
            "**More asset classes** → smoother drawdowns potential, but more funds to manage.\n"
            "**Equity-heavy mix** → higher growth potential, larger bear-market swings."
        )
        sections = build_analyst_sections(
            direct_answer=direct,
            portfolio_analyst_view=analyst,
            key_variables=key_vars,
            tradeoffs=tradeoffs,
            recommended_actions=actions,
            risk_notes=default_educational_risk_notes(beginner),
            beginner=beginner,
        )
        return InvestmentSolverResult(
            short_answer=direct,
            analyst_sections=sections,
            problem_type="diversification",
            model_name="Diversification analyst",
            confidence_pct=80,
            computed={
                "equity_pct": round(equity_pct, 1),
                "bond_pct": round(bond_pct, 1),
                "ami_engine_id": self.engine_id,
            },
        )


_DEFAULT_ENGINE = DiversificationEngine()


def get_diversification_engine() -> DiversificationEngine:
    return _DEFAULT_ENGINE
