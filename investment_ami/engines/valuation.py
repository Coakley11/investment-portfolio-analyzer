"""Security valuation instant reasoning engine (P2)."""

from __future__ import annotations

from typing import Any

from investment_ami_answer_format import build_analyst_sections
from investment_ami_instant_solver import InvestmentSolverResult
from investment_ami_valuation import resolve_valuation_context

from investment_ami.engines.base import InstantEngineRequest
from investment_ami.engines.support.presentation import default_educational_risk_notes


def _valuation_solve(ctx: dict[str, Any], *, beginner: bool, question: str = "") -> InvestmentSolverResult:
    vctx = resolve_valuation_context(question, ctx)
    target = vctx.get("target_ticker")
    ticker_data = dict(vctx.get("ticker_data") or {})
    assessment = dict(vctx.get("assessment") or {})
    macro_env = str(vctx.get("macro_env") or "Fair Value")
    macro_fx = dict(vctx.get("macro_effects") or {})
    port_w = vctx.get("portfolio_weight_pct")
    sym = str(ticker_data.get("ticker") or target or "").strip().upper()
    name = str(ticker_data.get("name") or sym or "this holding")
    pe = ticker_data.get("pe")
    style = str(ticker_data.get("style") or "broad")
    label = str(assessment.get("label") or "unknown")
    headline = str(assessment.get("headline") or "")
    ey = assessment.get("earnings_yield_pct")
    impl_g = assessment.get("implied_growth_pct")
    fair_mid = assessment.get("fair_pe_mid")

    if not sym:
        direct = (
            "Name a ticker or ETF (for example VOO or SCHD) so I can frame whether it looks expensive or fair."
            if beginner
            else "Specify a ticker/ETF in the question — valuation analysis needs a target security."
        )
        sections = build_analyst_sections(
            direct_answer=direct,
            portfolio_analyst_view=(
                "Valuation is security-specific. Broad market P/E, fund style, and your macro assumptions "
                "all shape whether an investment looks rich or cheap."
            ),
            recommended_actions="Ask e.g. “Is SCHD expensive?” or “What growth rate is implied for VOO?”",
            risk_notes=default_educational_risk_notes(beginner),
            beginner=beginner,
        )
        return InvestmentSolverResult(
            short_answer=direct,
            analyst_sections=sections,
            problem_type="valuation",
            model_name="Valuation analyst",
            confidence_pct=55,
            computed={"ami_engine_id": "valuation"},
        )

    if style == "bond":
        direct = (
            f"**{sym}** is a bond fund — equity P/E is not the right lens. Focus on **yield**, **duration**, "
            "and how **rate changes** affect price."
        )
        analyst = (
            "Bond valuation is driven by interest rates and credit quality, not earnings multiples. "
            f"Your macro valuation setting (**{macro_env}**) mainly affects **equity** sleeves in the portfolio."
        )
    elif label == "unknown" or pe is None:
        direct = f"I cannot pin a reliable P/E on **{sym}** right now — use fund style and macro backdrop instead."
        analyst = (
            f"Without a clean multiple, analysts still ask: what growth must **{name}** deliver to justify today's price? "
            f"Macro valuation environment: **{macro_env}**."
        )
    else:
        direct = f"**{sym}** {headline}"
        if port_w:
            direct += f" It is **{port_w:.1f}%** of your portfolio."
        analyst = (
            f"At P/E **{pe:.1f}**, earnings yield is about **{ey:.1f}%** — the market is pricing in roughly "
            f"**{impl_g:.1f}%** long-run growth (educational estimate vs a ~10% required return). "
            f"For **{style}** funds, a typical fair P/E band centers near **{fair_mid:.0f}**. "
            f"Your Portfolio Health macro setting is **{macro_env}**, which shifts forward equity return "
            f"by about **{macro_fx.get('equity_return_shift_pct', 0):+.1f}%** on your **{vctx.get('equity_pct', 0):.0f}%** equity sleeve."
        )

    q_lower = str(question or "").lower()
    asks_growth = any(p in q_lower for p in ("growth rate", "implied", "assumptions matter", "what assumptions"))
    asks_expensive = any(p in q_lower for p in ("expensive", "overvalued", "cheap", "undervalued", "fair"))

    key_lines = [
        f"- Target: **{sym}** ({ticker_data.get('category', 'ETF')})",
        f"- Valuation label: **{label.replace('_', ' ')}**",
        f"- Macro valuation environment: **{macro_env}**",
        f"- Portfolio equity sleeve: **{vctx.get('equity_pct', 0):.0f}%**",
    ]
    if pe is not None:
        key_lines.extend(
            [
                f"- Trailing P/E: **{pe:.1f}** ({ticker_data.get('pe_source', 'estimate')})",
                f"- Earnings yield (1/P/E): **{ey:.1f}%**",
                f"- Implied growth (est.): **{impl_g:.1f}%**",
                f"- Style fair P/E midpoint: **{fair_mid:.0f}**" if fair_mid else "",
            ]
        )
    if port_w:
        key_lines.append(f"- Your portfolio weight in **{sym}**: **{port_w:.1f}%**")
    key_lines = [ln for ln in key_lines if ln]

    if asks_growth and impl_g is not None:
        tradeoffs = (
            f"**Higher implied growth ({impl_g:.1f}%)** means the market already expects strong earnings — "
            "surprises must beat that bar.\n"
            "**Lower growth assumptions** would justify a cheaper multiple — downside if growth disappoints."
        )
    elif asks_expensive:
        tradeoffs = (
            "**Buying rich multiples** can work if growth delivers — but margin of safety is thinner.\n"
            "**Waiting for cheaper entry** reduces upside timing risk but may mean sitting in cash longer."
        )
    else:
        tradeoffs = (
            "**Style matters** — growth ETFs tolerate higher P/E than dividend/value funds.\n"
            "**Macro backdrop matters** — expensive markets can stay rich until rates or earnings shift."
        )

    sens = list(vctx.get("sensitivity") or [])
    if sens and not beginner:
        what_if = "\n".join(f"- **{s['scenario']}** → {s['impact']}" for s in sens[:3])
    elif pe is not None and impl_g is not None:
        what_if = (
            f"- If growth expectations fall 2% → P/E compression risk on **{sym}**\n"
            f"- If macro shifts to **Expensive** → ~**{abs(macro_fx.get('equity_return_shift_pct') or 1.5):.1f}%** "
            f"headwind on equity sleeve\n"
            f"- If earnings grow faster than **{impl_g:.1f}%** implied → multiple may hold or expand"
        )
    else:
        what_if = f"- Macro **{macro_env}** → equity return shift ~**{macro_fx.get('equity_return_shift_pct', 0):+.1f}%**"

    if label in {"expensive", "moderately rich"}:
        actions = (
            f"If **{sym}** feels rich, consider whether you already get similar exposure elsewhere, "
            "or dollar-cost average rather than lump-sum adding."
        )
    elif label == "cheap":
        actions = (
            f"**{sym}** looks relatively cheap for its style — confirm the thesis fits your allocation "
            "before sizing up."
        )
    else:
        actions = (
            f"For **{sym}**, focus on whether implied growth (~**{impl_g:.1f}%**)" if impl_g else f"For **{sym}**, focus"
        ) + " matches your view — valuation is about expectations, not just today's price."

    if port_w and port_w >= 20 and label in {"expensive", "moderately rich"}:
        actions += f" At **{port_w:.0f}%** portfolio weight, multiple compression on **{sym}** would be noticeable."

    sections = build_analyst_sections(
        direct_answer=direct,
        portfolio_analyst_view=analyst,
        key_variables="\n".join(key_lines),
        tradeoffs=tradeoffs,
        what_if_scenarios=what_if,
        recommended_actions=actions,
        risk_notes=default_educational_risk_notes(beginner),
        beginner=beginner,
    )
    conf = 78 if pe is not None else 62
    if ticker_data.get("pe_source") == "live":
        conf = min(85, conf + 4)
    return InvestmentSolverResult(
        short_answer=direct,
        analyst_sections=sections,
        problem_type="valuation",
        model_name="Valuation analyst",
        confidence_pct=conf,
        computed={
            "target_ticker": sym,
            "pe": pe,
            "valuation_label": label,
            "implied_growth_pct": impl_g,
            "macro_valuation": macro_env,
            "portfolio_weight_pct": port_w,
            "ami_engine_id": "valuation",
        },
    )


class ValuationEngine:
    engine_id = "valuation"

    def solve(self, request: InstantEngineRequest) -> InvestmentSolverResult:
        return _valuation_solve(
            dict(request.context or {}),
            beginner=bool(request.beginner),
            question=str(request.question or ""),
        )


_DEFAULT_ENGINE = ValuationEngine()


def get_valuation_engine() -> ValuationEngine:
    return _DEFAULT_ENGINE
