"""Portfolio risk instant reasoning engine (P2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from investment_ami_answer_format import build_analyst_sections
from investment_ami_exposure import resolve_tech_exposure
from investment_ami_instant_solver import InvestmentSolverResult

from investment_ami.engines.base import InstantEngineRequest
from investment_ami.engines.portfolio_concentration import assess_portfolio_concentration
from investment_ami.engines.support.presentation import default_educational_risk_notes


@dataclass(frozen=True)
class PortfolioRiskAssessment:
    """Risk snapshot from weights, tech exposure, and health context."""

    top_ticker: str
    top_weight_pct: float
    top3_weight_pct: float
    tech_proxy_pct: float
    embedded_tech_pct: float
    risk_level: str
    volatility: str
    max_drawdown: str
    has_weights: bool


def assess_portfolio_risk(context: dict[str, Any]) -> PortfolioRiskAssessment:
    concentration = assess_portfolio_concentration(context)
    exposure = resolve_tech_exposure(context)
    tech_pct = float(exposure.get("total_pct") or 0)
    embedded_tech = float(exposure.get("embedded_pct") or 0)
    risk_level = str(context.get("risk_level") or "").strip()
    vol = str(context.get("volatility") or "").strip()
    max_dd = context.get("max_drawdown")
    max_drawdown = str(max_dd).strip() if max_dd not in (None, "") else ""

    if concentration.empty:
        return PortfolioRiskAssessment(
            top_ticker="—",
            top_weight_pct=0.0,
            top3_weight_pct=0.0,
            tech_proxy_pct=tech_pct,
            embedded_tech_pct=embedded_tech,
            risk_level=risk_level,
            volatility=vol,
            max_drawdown=max_drawdown,
            has_weights=False,
        )

    return PortfolioRiskAssessment(
        top_ticker=concentration.top_ticker,
        top_weight_pct=concentration.top_pct,
        top3_weight_pct=concentration.top3_pct,
        tech_proxy_pct=tech_pct,
        embedded_tech_pct=embedded_tech,
        risk_level=risk_level,
        volatility=vol,
        max_drawdown=max_drawdown,
        has_weights=True,
    )


class PortfolioRiskEngine:
    engine_id = "portfolio_risk"

    def solve(self, request: InstantEngineRequest) -> InvestmentSolverResult:
        ctx = dict(request.context or {})
        beginner = bool(request.beginner)
        a = assess_portfolio_risk(ctx)

        top_ticker = a.top_ticker
        top_pct = a.top_weight_pct
        top3 = a.top3_weight_pct
        tech_pct = a.tech_proxy_pct
        embedded_tech = a.embedded_tech_pct
        risk_level = a.risk_level
        vol = a.volatility
        rows = a.has_weights

        if beginner:
            direct = "Your biggest risks right now are concentration, sector tilt, and how much volatility you are carrying."
            analyst = (
                f"Largest position **{top_ticker}** at **{top_pct:.1f}%** can move the whole portfolio — "
                "that is **concentration risk**: one sleeve drives outcomes. "
                + (
                    f"Estimated technology exposure is **{tech_pct:.1f}%** "
                    f"({'including embedded exposure in broad/dividend funds' if embedded_tech > 0 else 'direct tech sleeves'}) — "
                    "meaningful if tech sells off. "
                    if tech_pct >= 10
                    else ""
                )
                + (f"Health check labels risk as **{risk_level}**." if risk_level else "")
                + " Risk **rises** if top weights grow; **falls** if you diversify or add defensive assets."
            )
            key_vars = "\n".join(
                filter(
                    None,
                    [
                        f"- Largest holding: **{top_ticker}** **{top_pct:.1f}%**" if rows else None,
                        f"- Top-3 concentration: **{top3:.1f}%**" if rows else None,
                        f"- Technology exposure (direct + embedded): **{tech_pct:.1f}%**" if tech_pct else None,
                        f"- Risk label: **{risk_level}**" if risk_level else None,
                        f"- Historical volatility: **{vol}**" if vol else None,
                    ],
                )
            )
            tradeoffs = (
                "**Growth tilt** can boost returns in strong markets but increases drawdown risk.\n"
                "**Defensive sleeves** (bonds, dividend, cash) reduce swings but may lag in rallies."
            )
            what_if = "If your largest holding fell **10%**, expect a noticeable portfolio dip — exact size depends on its weight."
            actions = (
                "Review whether top weights and tech tilt match your comfort level. "
                "If not, rebalance toward targets or add diversifiers."
            )
        else:
            direct = (
                f"Primary risk drivers: top-weight **{top_ticker}** **{top_pct:.1f}%**, "
                f"top-3 **{top3:.1f}%**"
                + (f", tech proxy **{tech_pct:.1f}%**" if tech_pct else "")
                + (f", health risk **{risk_level}**" if risk_level else "")
                + "."
            )
            analyst = (
                "Risk stacks from **concentration** (idiosyncratic), **factor/sector tilt** (systematic), "
                "and **historical volatility**. Dominant sleeves drive short-term variance. "
                "Severity is **elevated** when top-3 exceeds ~60% or tech proxy exceeds ~35%; "
                "**moderate** below those bands. Rebalancing and defensive sleeves reduce exposure."
            )
            key_vars = "\n".join(
                filter(
                    None,
                    [
                        f"- Top-weight risk: **{top_ticker}** **{top_pct:.1f}%**" if rows else None,
                        f"- Top-3 concentration: **{top3:.1f}%**" if rows else None,
                        f"- Technology exposure (direct + embedded): **{tech_pct:.1f}%**" if tech_pct else None,
                        f"- Historical volatility: **{vol}**" if vol else None,
                        f"- Health risk level: **{risk_level}**" if risk_level else None,
                        f"- Max drawdown (historical): **{a.max_drawdown}**" if a.max_drawdown else None,
                    ],
                )
            )
            tradeoffs = (
                "Reducing concentration lowers sleeve-level shock but may trim intentional factor bets. "
                "Adding defensive assets cuts variance but creates opportunity cost in equity rallies."
            )
            what_if = (
                f"Static shock: **{top_ticker}** **-10%** → ~**{top_pct * 0.10:.1f}%** portfolio impact.\n"
                f"Tech sleeve **-20%** → ~**{tech_pct * 0.20:.1f}%** impact (proxy, ignoring correlation)."
                if tech_pct
                else f"Static shock: **{top_ticker}** **-10%** → ~**{top_pct * 0.10:.1f}%** portfolio impact."
            )
            actions = (
                "Set rebalance bands for top weights and sector proxies; stress-test before adding overlapping index funds."
            )

        sections = build_analyst_sections(
            direct_answer=direct,
            portfolio_analyst_view=analyst,
            key_variables=key_vars or "—",
            tradeoffs=tradeoffs,
            what_if_scenarios=what_if,
            recommended_actions=actions,
            risk_notes=default_educational_risk_notes(beginner),
            beginner=beginner,
        )
        return InvestmentSolverResult(
            short_answer=direct,
            analyst_sections=sections,
            math_idea="Concentration + sector tilt + historical volatility frame risk.",
            problem_type="portfolio_risk",
            model_name="Investment risk analyst",
            confidence_pct=81,
            computed={
                "top_weight_pct": top_pct,
                "top3_weight_pct": round(top3, 1),
                "tech_proxy_pct": round(tech_pct, 1),
                "ami_engine_id": self.engine_id,
            },
        )


_DEFAULT_ENGINE = PortfolioRiskEngine()


def get_portfolio_risk_engine() -> PortfolioRiskEngine:
    return _DEFAULT_ENGINE
