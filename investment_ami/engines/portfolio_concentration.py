"""Portfolio concentration instant reasoning engine (P2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from investment_ami_answer_format import build_analyst_sections
from investment_ami_instant_solver import (
    InvestmentSolverResult,
    _portfolio_label,
    _weight_rows,
)

from investment_ami.engines.base import InstantEngineRequest
from investment_ami.engines.support.presentation import default_educational_risk_notes


@dataclass(frozen=True)
class ConcentrationAssessment:
    """Pure concentration metrics from portfolio weight rows."""

    top_ticker: str
    top_pct: float
    top3_pct: float
    flag: str
    rows: tuple[tuple[str, float], ...]
    empty: bool = False


def assess_concentration_from_rows(rows: list[tuple[str, float]]) -> ConcentrationAssessment:
    if not rows:
        return ConcentrationAssessment(
            top_ticker="",
            top_pct=0.0,
            top3_pct=0.0,
            flag="",
            rows=(),
            empty=True,
        )
    top_ticker, top_pct = rows[0]
    top3 = sum(p for _, p in rows[:3])
    flag = "high" if top_pct >= 35 else "moderate" if top_pct >= 25 else "low"
    return ConcentrationAssessment(
        top_ticker=str(top_ticker),
        top_pct=float(top_pct),
        top3_pct=float(top3),
        flag=flag,
        rows=tuple(rows),
    )


def assess_portfolio_concentration(context: dict[str, Any]) -> ConcentrationAssessment:
    return assess_concentration_from_rows(_weight_rows(context))


class PortfolioConcentrationEngine:
    engine_id = "portfolio_concentration"

    def solve(self, request: InstantEngineRequest) -> InvestmentSolverResult:
        ctx = dict(request.context or {})
        beginner = bool(request.beginner)
        assessment = assess_portfolio_concentration(ctx)

        if assessment.empty:
            direct = (
                "Add holdings with weights first — I need your portfolio mix to judge concentration."
                if beginner
                else "No holdings weights in context — populate Portfolio Health weights before concentration analysis."
            )
            sections = build_analyst_sections(
                direct_answer=direct,
                portfolio_analyst_view=(
                    "Concentration measures how much of your portfolio sits in a few fund sleeves. "
                    "Without weights, I cannot score top-fund or top-3 allocation exposure."
                ),
                recommended_actions="Enter tickers and target weights, then ask again.",
                risk_notes=default_educational_risk_notes(beginner),
                beginner=beginner,
            )
            return InvestmentSolverResult(
                short_answer=direct,
                analyst_sections=sections,
                math_idea="Top-weight and top-3 concentration bands.",
                problem_type="portfolio_concentration",
                model_name="Investment concentration analyst",
                confidence_pct=60,
                computed={"ami_engine_id": self.engine_id},
            )

        rows = list(assessment.rows)
        top_ticker = assessment.top_ticker
        top_pct = assessment.top_pct
        top3 = assessment.top3_pct
        flag = assessment.flag

        if beginner:
            if top_pct >= 35:
                direct = (
                    f"Yes — your portfolio looks concentrated. **{top_ticker}** is about **{top_pct:.1f}%** of the mix."
                )
            elif top_pct >= 25:
                direct = f"Moderately concentrated — **{top_ticker}** is about **{top_pct:.1f}%**."
            else:
                direct = (
                    f"Not highly concentrated in one fund sleeve. Largest holding **{top_ticker}** is **{top_pct:.1f}%**."
                )
            analyst = (
                f"Your top three fund sleeves (**{', '.join(t for t, _ in rows[:3])}**) add up to about **{top3:.1f}%**. "
                "Portfolio performance will be heavily influenced by those top sleeves — returns and drawdowns "
                "will largely track their combined moves rather than a broad diversified index."
            )
            tradeoffs = (
                "**More concentration** → simpler portfolio, clearer bets, but bigger swings from one sleeve.\n"
                "**More diversification** → smoother ride, less single-sleeve shock, but you may lag a hot sector."
            )
            actions = (
                "If concentration feels uncomfortable, consider trimming the largest weight toward your target mix "
                "or adding a complementary asset class (e.g., bonds or a broad market fund)."
            )
        else:
            direct = (
                f"Concentration scan ({_portfolio_label(ctx)}): top **{top_ticker}** **{top_pct:.1f}%**; "
                f"top-3 **{top3:.1f}%** → **{flag}** fund-level concentration."
            )
            analyst = (
                f"Top-3 weight **{top3:.1f}%** implies meaningful **allocation concentration** — portfolio P&L will "
                f"be driven primarily by {top_ticker} and the other top fund sleeves, not by market-wide diversification. "
                "Risk **increases** if top weights drift higher; it **eases** if you rebalance toward targets or add "
                "uncorrelated sleeves."
            )
            tradeoffs = (
                "Higher top-weight concentration increases tracking error vs a broad benchmark and amplifies "
                "drawdowns if the dominant sleeve underperforms. Lower concentration reduces sleeve-level shock "
                "but may dilute intentional tilts."
            )
            actions = (
                f"Monitor **{top_ticker}** vs target band; rebalance if top weight exceeds policy tolerance "
                "(often 25–35% for single-fund sleeves in diversified portfolios)."
            )

        key_vars = (
            "\n".join(f"- **{t}**: **{p:.1f}%**" for t, p in rows[:5])
            + f"\n- **Top-3 weight**: **{top3:.1f}%**"
        )

        what_if = (
            f"If **{top_ticker}** fell **10%**, a rough static impact is about **{top_pct * 0.10:.1f}%** on the total portfolio "
            f"(ignoring correlation and other moves)."
        )
        if not beginner:
            what_if += (
                f"\nIf top-3 holdings fell together **10%**, illustrative portfolio impact ≈ **{top3 * 0.10:.1f}%**."
            )

        sections = build_analyst_sections(
            direct_answer=direct,
            portfolio_analyst_view=analyst,
            key_variables=key_vars,
            tradeoffs=tradeoffs,
            what_if_scenarios=what_if,
            recommended_actions=actions,
            risk_notes=default_educational_risk_notes(beginner),
            beginner=beginner,
        )
        return InvestmentSolverResult(
            short_answer=direct,
            analyst_sections=sections,
            math_idea="Top-weight and top-3 weight concentration bands.",
            problem_type="portfolio_concentration",
            model_name="Investment concentration analyst",
            variables=f"top_weight={top_pct:.1f}%",
            assumptions=["Weights reflect current portfolio session.", "Not personal financial advice."],
            confidence_pct=84,
            computed={
                "top_ticker": top_ticker,
                "top_weight_pct": top_pct,
                "top3_weight_pct": round(top3, 1),
                "ami_engine_id": self.engine_id,
            },
        )


_DEFAULT_ENGINE = PortfolioConcentrationEngine()


def get_portfolio_concentration_engine() -> PortfolioConcentrationEngine:
    return _DEFAULT_ENGINE
