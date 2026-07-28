"""ETF overlap instant reasoning engine (P2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from investment_ami_answer_format import build_analyst_sections
from investment_ami_instant_solver import InvestmentSolverResult, _weight_rows

from investment_ami.engines.base import InstantEngineRequest
from investment_ami.engines.support.overlap_data import (
    resolve_etf_overlap_pairs,
    tickers_mentioned_in_question,
)
from investment_ami.engines.support.presentation import default_educational_risk_notes

_GROWTH_TICKERS = frozenset({"QQQ", "VGT", "ARKK", "TQQQ"})


@dataclass(frozen=True)
class EtfOverlapAssessment:
    pairs: tuple[dict[str, Any], ...]
    top_pair: dict[str, Any]
    ticker_a: str
    ticker_b: str
    overlap_pct: float
    compare_mode: bool
    growth_tilt: bool
    portfolio_tickers: tuple[str, ...]
    empty: bool = False


def assess_etf_overlap(
    context: dict[str, Any],
    *,
    question: str = "",
) -> EtfOverlapAssessment:
    pairs = resolve_etf_overlap_pairs(context, question=question)
    rows = _weight_rows(context)
    tickers = tuple(t for t, _ in rows)
    mentioned = tickers_mentioned_in_question(question)

    if not pairs:
        return EtfOverlapAssessment(
            pairs=(),
            top_pair={},
            ticker_a="",
            ticker_b="",
            overlap_pct=0.0,
            compare_mode=False,
            growth_tilt=False,
            portfolio_tickers=tickers,
            empty=True,
        )

    top_pair = max(pairs, key=lambda p: float(p.get("overlap_pct") or 0))
    pair_str = str(top_pair.get("pair") or "")
    if "/" in pair_str:
        t1, t2 = pair_str.split("/", 1)
    else:
        t1, t2 = "?", "?"
    ov = float(top_pair.get("overlap_pct") or 0)
    compare_mode = len(mentioned) >= 2 and mentioned[0] in (t1, t2) and mentioned[1] in (t1, t2)
    growth_tilt = t2 in _GROWTH_TICKERS or t1 in _GROWTH_TICKERS

    return EtfOverlapAssessment(
        pairs=tuple(pairs),
        top_pair=dict(top_pair),
        ticker_a=str(t1),
        ticker_b=str(t2),
        overlap_pct=ov,
        compare_mode=compare_mode,
        growth_tilt=growth_tilt,
        portfolio_tickers=tickers,
        empty=False,
    )


class EtfOverlapEngine:
    engine_id = "etf_overlap"

    def solve(self, request: InstantEngineRequest) -> InvestmentSolverResult:
        ctx = dict(request.context or {})
        beginner = bool(request.beginner)
        question = str(request.question or "")
        assessment = assess_etf_overlap(ctx, question=question)

        if assessment.empty:
            tickers = list(assessment.portfolio_tickers)
            if len(tickers) >= 2:
                direct = (
                    f"You hold **{'**, **'.join(tickers[:4])}** — overlap data was not loaded. "
                    "Open ETF Holdings or retry after holdings sync."
                )
            else:
                direct = "Add at least two ETF tickers to analyze overlap."
            sections = build_analyst_sections(
                direct_answer=direct,
                recommended_actions="Use the ETF Holdings tab to inspect underlying overlap, then ask again.",
                risk_notes=default_educational_risk_notes(beginner),
                beginner=beginner,
            )
            return InvestmentSolverResult(
                short_answer=direct,
                analyst_sections=sections,
                problem_type="etf_overlap",
                model_name="ETF overlap analyst",
                confidence_pct=55,
                computed={"ami_engine_id": self.engine_id},
            )

        t1 = assessment.ticker_a
        t2 = assessment.ticker_b
        ov = assessment.overlap_pct
        compare_mode = assessment.compare_mode
        growth_tilt = assessment.growth_tilt
        pairs = list(assessment.pairs)
        top_pair = assessment.top_pair

        if compare_mode and beginner:
            if ov >= 50:
                direct = (
                    f"**Usually not both** — **{t1}** and **{t2}** overlap about **{ov:.0f}%**. "
                    "You mostly duplicate the same large US stocks."
                )
            elif ov >= 35:
                direct = (
                    f"**Optional, not both at large weights** — **{ov:.0f}%** overlap between **{t1}** and **{t2}**."
                )
            else:
                direct = f"**Can own both** at moderate weights — overlap is **{ov:.0f}%**, lower duplication."
            analyst = (
                f"**{t1}** is a broad US market fund; **{t2}** is {'growth/tech tilted' if growth_tilt else 'a different factor sleeve'}. "
                "Overlap means you double-count the same underlying names."
            )
        elif compare_mode and not beginner:
            direct = (
                f"ETF comparison **{t1} vs {t2}**: overlap **{ov:.1f}%** — "
                + ("high duplication; prefer one core sleeve." if ov >= 35 else "moderate overlap; size sleeves intentionally.")
            )
            analyst = (
                f"**{t1}** = broad beta exposure; **{t2}** = {'growth/tech concentration' if growth_tilt else 'alternate factor'}. "
                "Combined overlap raises effective mega-cap weight and reduces independent diversification."
            )
        elif beginner:
            direct = (
                f"**{t1}** and **{t2}** share about **{ov:.0f}%** of the same underlying holdings — "
                + ("that is meaningful duplication." if ov >= 35 else "some overlap is normal for broad US funds.")
            )
            analyst = (
                "Owning two funds with similar holdings means you may think you are diversified when both "
                "move with the same large stocks (often Apple, Microsoft, NVIDIA in index ETFs)."
            )
        else:
            direct = f"Highest pairwise overlap: **{t1}/{t2}** ≈ **{ov:.1f}%** (sum of min inner weights)."
            analyst = (
                "High overlap increases effective concentration in shared mega-cap names and reduces "
                "independent diversification benefit between sleeves."
            )

        key_vars = "\n".join(
            f"- **{p.get('pair')}**: **{float(p.get('overlap_pct') or 0):.1f}%**" for p in pairs[:5]
        )
        tradeoffs = (
            "**Stacking similar index ETFs** → simpler implementation, but hidden duplication.\n"
            "**Consolidating to one core sleeve** → cleaner exposure, easier rebalancing."
        )
        actions = (
            f"Consider keeping one primary US equity sleeve instead of both **{t1}** and **{t2}** "
            "if overlap exceeds your tolerance (~35%)."
            if ov >= 35
            else "Overlap is moderate — verify sector goals before adding a third broad equity fund."
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
            problem_type="etf_overlap",
            model_name="ETF overlap analyst",
            confidence_pct=82 if ov else 60,
            computed={
                "max_overlap_pct": ov,
                "max_overlap_pair": top_pair.get("pair"),
                "ami_engine_id": self.engine_id,
            },
        )


_DEFAULT_ENGINE = EtfOverlapEngine()


def get_etf_overlap_engine() -> EtfOverlapEngine:
    return _DEFAULT_ENGINE
