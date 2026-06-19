"""Local Investment AMI instant solver — Phase 1 portfolio families."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

INVESTMENT_AMI_BUILD_ID = "investment-ami-v2-phase2g-allocation-inflation1"

_TECH_TICKERS = frozenset(
    {
        "QQQ",
        "VGT",
        "XLK",
        "FTEC",
        "IGV",
        "SMH",
        "SOXX",
        "ARKK",
        "TQQQ",
        "TECL",
        "MGK",
        "VUG",
    }
)

_INVESTMENT_SOLVER_INTENTS = frozenset(
    {
        "portfolio_concentration",
        "rebalance_allocation",
        "portfolio_risk",
        "sector_exposure",
        "risk_reduction",
        "investment_coach",
        "etf_overlap",
        "diversification",
        "scenario_stress",
        "valuation",
        "macro_rates",
        "macro_recession",
        "macro_inflation",
        "allocation_recommendation",
    }
)


@dataclass
class InvestmentSolverRoute:
    problem_type: str
    model_name: str
    model_rationale: str = ""


@dataclass
class InvestmentSolverResult:
    short_answer: str
    math_idea: str = ""
    problem_type: str = ""
    model_name: str = ""
    variables: str = ""
    assumptions: list[str] = field(default_factory=list)
    confidence_pct: int | None = 82
    computed: dict[str, Any] = field(default_factory=dict)
    analyst_sections: dict[str, str] = field(default_factory=dict)


def _ctx_value(ctx: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        val = ctx.get(key)
        if val is not None and str(val).strip() != "":
            return val
    return default


def _parse_weight_pct(raw: Any) -> float | None:
    text = str(raw or "").replace("%", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _weight_rows(ctx: dict[str, Any]) -> list[tuple[str, float]]:
    weights = _ctx_value(ctx, "current_weights", default={})
    rows: list[tuple[str, float]] = []
    if isinstance(weights, dict):
        for ticker, wt in weights.items():
            pct = _parse_weight_pct(wt)
            if pct is not None and str(ticker).strip():
                rows.append((str(ticker).strip().upper(), pct))
    if rows:
        return sorted(rows, key=lambda x: x[1], reverse=True)
    holdings = _ctx_value(ctx, "holdings", default=[])
    if isinstance(holdings, list) and holdings:
        even = 100.0 / max(len(holdings), 1)
        return [(str(t).strip().upper(), even) for t in holdings[:12] if str(t).strip()]
    return rows


def _beginner(ctx: dict[str, Any]) -> bool:
    from investment_ami_context import is_beginner_experience

    return is_beginner_experience(ctx)


def _portfolio_label(ctx: dict[str, Any]) -> str:
    tickers = [t for t, _ in _weight_rows(ctx)]
    if tickers:
        return ", ".join(tickers[:4]) + ("…" if len(tickers) > 4 else "")
    return "your current holdings"


def _concentration_answer(ctx: dict[str, Any], *, beginner: bool) -> InvestmentSolverResult:
    rows = _weight_rows(ctx)
    lines: list[str] = []
    computed: dict[str, Any] = {}
    if not rows:
        text = (
            "Add your holdings first so I can judge concentration. "
            "A simple rule: if one fund or stock is much larger than the rest, your portfolio is concentrated."
            if beginner
            else "No holdings weights found in context — run Portfolio Health with weights populated before concentration analysis."
        )
        return InvestmentSolverResult(
            short_answer=text,
            math_idea="Concentration = share of portfolio in top positions.",
            problem_type="portfolio_concentration",
            model_name="Investment concentration check",
            assumptions=["Holdings weights reflect your current portfolio."],
            confidence_pct=60,
        )

    top_ticker, top_pct = rows[0]
    computed["top_ticker"] = top_ticker
    computed["top_weight_pct"] = top_pct
    top3 = sum(p for _, p in rows[:3])
    computed["top3_weight_pct"] = round(top3, 1)

    if beginner:
        if top_pct >= 35:
            lines.append(
                f"**Yes — your portfolio looks concentrated.** **{top_ticker}** is about **{top_pct:.1f}%** of the portfolio."
            )
            lines.append(
                "That means one position drives a large share of outcomes. If it drops, your whole portfolio feels it more."
            )
        elif top_pct >= 25:
            lines.append(
                f"**Moderately concentrated.** **{top_ticker}** is about **{top_pct:.1f}%** — worth watching if you want smoother ride."
            )
        else:
            lines.append(
                f"**Not highly concentrated** in one fund sleeve. Largest holding **{top_ticker}** is about **{top_pct:.1f}%**."
            )
        lines.append("Spreading across more fund sleeves can reduce single-sleeve shock — not a guarantee of better returns.")
    else:
        flag = "high" if top_pct >= 35 else "moderate" if top_pct >= 25 else "low"
        lines.append(
            f"Concentration scan ({_portfolio_label(ctx)}): top fund sleeve **{top_ticker}** **{top_pct:.1f}%**; "
            f"top-3 weight **{top3:.1f}%** → **{flag}** fund-level concentration."
        )
        if top_pct >= 25:
            lines.append(
                "Elevated top-weight concentration increases sleeve-level risk — portfolio volatility tracks the dominant fund more closely."
            )
        else:
            lines.append("Weight distribution is relatively balanced versus a 25–35% concentration warning band.")

    return InvestmentSolverResult(
        short_answer="\n".join(lines),
        math_idea="Top-weight and top-3 weight concentration bands.",
        problem_type="portfolio_concentration",
        model_name="Investment concentration analyst",
        variables=f"top_weight={top_pct:.1f}%",
        assumptions=[
            "Weights are current portfolio targets or actual weights from your session.",
            "This is educational analysis, not personal financial advice.",
        ],
        confidence_pct=84 if rows else 60,
        computed=computed,
    )


def _rebalance_answer(ctx: dict[str, Any], *, beginner: bool) -> InvestmentSolverResult:
    drift = _ctx_value(ctx, "rebalance_drift", default={})
    objective = str(_ctx_value(ctx, "objective", default="")).strip()
    health = _ctx_value(ctx, "health_score", default="")
    rows = _weight_rows(ctx)
    lines: list[str] = []

    if beginner:
        lines.append("**Rebalancing review**")
        if isinstance(drift, dict) and drift:
            worst = list(drift.items())[:3]
            bits = [f"**{t}** ({d})" for t, d in worst]
            lines.append(f"Largest drifts vs objective: {', '.join(bits)}.")
            lines.append("Rebalancing means trimming what grew above target and adding to what fell below — keeps risk aligned with your plan.")
        elif rows:
            alloc = ", ".join(f"**{t}** {p:.1f}%" for t, p in rows[:5])
            lines.append(f"Current mix: {alloc}.")
            lines.append(
                "Compare this to your target mix. If one slice drifted far from plan, a rebalance brings you back — not a market-timing call."
            )
        else:
            lines.append("Set target weights, then compare them to today's mix. Rebalance when drift is large enough to matter to your goal.")
        if objective:
            lines.append(f"Goal context: **{objective}**.")
        if health:
            lines.append(f"Portfolio health score: **{health}**.")
    else:
        lines.append("**Allocation / rebalance assessment**")
        if isinstance(drift, dict) and drift:
            for ticker, val in list(drift.items())[:5]:
                lines.append(f"- **{ticker}** drift **{val}** vs objective")
        elif rows:
            for ticker, pct in rows[:6]:
                lines.append(f"- **{ticker}** **{pct:.1f}%** current weight")
        if objective:
            lines.append(f"- Objective: **{objective}**")
        metrics = []
        for key, label in (("expected_return", "E[R]"), ("volatility", "vol"), ("sharpe_ratio", "Sharpe")):
            val = _ctx_value(ctx, key, default="")
            if val:
                metrics.append(f"{label} **{val}**")
        if metrics:
            lines.append(f"- Historical metrics: {', '.join(metrics)}")
        lines.append(
            "Rebalance when drift exceeds your tolerance band — tradeoff: tracking error vs transaction/tax costs."
        )

    return InvestmentSolverResult(
        short_answer="\n".join(lines),
        math_idea="Drift vs objective weights drives rebalance priority.",
        problem_type="rebalance_allocation",
        model_name="Investment allocation analyst",
        assumptions=["Target weights reflect your stated objective.", "Not personal financial advice."],
        confidence_pct=80,
        computed={"drift_count": len(drift) if isinstance(drift, dict) else 0},
    )


def _portfolio_risk_answer(ctx: dict[str, Any], *, beginner: bool) -> InvestmentSolverResult:
    rows = _weight_rows(ctx)
    risk_level = str(_ctx_value(ctx, "risk_level", default="")).strip()
    vol = str(_ctx_value(ctx, "volatility", default="")).strip()
    lines: list[str] = []

    if beginner:
        lines.append("**Biggest portfolio risks to watch**")
        if rows:
            top_ticker, top_pct = rows[0]
            lines.append(f"1. **Single-position size** — **{top_ticker}** at **{top_pct:.1f}%** moves the whole portfolio.")
        tech_pct = sum(p for t, p in rows if t in _TECH_TICKERS)
        if tech_pct >= 20:
            lines.append(f"2. **Technology tilt** — about **{tech_pct:.1f}%** in tech-heavy funds.")
        if risk_level:
            lines.append(f"3. **Risk label from health check** — **{risk_level}**.")
        elif vol:
            lines.append(f"3. **Historical volatility** — about **{vol}** (past data, not a forecast).")
        else:
            lines.append("3. **Missing diversification** if most holdings move together.")
        lines.append("These are tradeoffs, not predictions — growth and safety pull in opposite directions.")
    else:
        lines.append("**Primary risk factors**")
        if rows:
            top_ticker, top_pct = rows[0]
            lines.append(f"- Top-weight risk: **{top_ticker}** **{top_pct:.1f}%**")
            top3 = sum(p for _, p in rows[:3])
            lines.append(f"- Top-3 concentration: **{top3:.1f}%**")
        tech_pct = sum(p for t, p in rows if t in _TECH_TICKERS)
        if tech_pct:
            lines.append(f"- Technology/growth proxy exposure ≈ **{tech_pct:.1f}%**")
        if vol:
            lines.append(f"- Historical volatility: **{vol}**")
        if risk_level:
            lines.append(f"- Health risk level: **{risk_level}**")
        max_dd = str(_ctx_value(ctx, "max_drawdown", default="")).strip()
        if max_dd:
            lines.append(f"- Max drawdown (historical): **{max_dd}**")

    return InvestmentSolverResult(
        short_answer="\n".join(lines),
        math_idea="Concentration + sector tilt + historical volatility frame risk.",
        problem_type="portfolio_risk",
        model_name="Investment risk analyst",
        confidence_pct=81,
    )


def _tech_exposure_answer(ctx: dict[str, Any], *, beginner: bool) -> InvestmentSolverResult:
    rows = _weight_rows(ctx)
    tech_rows = [(t, p) for t, p in rows if t in _TECH_TICKERS]
    tech_pct = sum(p for t, p in tech_rows)
    other_growth = sum(
        p for t, p in rows if t not in _TECH_TICKERS and t in {"VUG", "MGK", "ARKK", "TQQQ"}
    )
    total_growth_proxy = tech_pct + other_growth

    if beginner:
        if tech_pct >= 40:
            headline = f"**Yes — tech/growth exposure is high** (~**{tech_pct:.1f}%** in tech-heavy funds)."
        elif tech_pct >= 25:
            headline = f"**Moderate tech tilt** (~**{tech_pct:.1f}%** in tech-heavy funds)."
        elif tech_pct > 0:
            headline = f"**Some tech exposure** (~**{tech_pct:.1f}%**), not dominated by tech alone."
        else:
            headline = "**No obvious tech ETF overlap** in the listed tickers — check underlying holdings for hidden tech exposure."
        detail = "Tech-heavy portfolios can grow faster in bull markets but often fall harder when growth stocks sell off."
        if tech_rows:
            names = ", ".join(f"**{t}** ({p:.1f}%)" for t, p in tech_rows[:4])
            detail += f" Tech-linked holdings: {names}."
        text = f"{headline}\n{detail}"
    else:
        text = (
            f"Technology proxy weight ≈ **{tech_pct:.1f}%**"
            + (f"; growth-tilt proxy total ≈ **{total_growth_proxy:.1f}%**." if total_growth_proxy else ".")
        )
        if tech_rows:
            text += "\n" + "\n".join(f"- **{t}** **{p:.1f}%**" for t, p in tech_rows)
        text += "\nCorrelated growth exposure amplifies drawdowns when mega-cap tech corrects."

    return InvestmentSolverResult(
        short_answer=text,
        math_idea="Tech ETF weights as a proxy for growth-sector exposure.",
        problem_type="sector_exposure",
        model_name="Investment sector exposure analyst",
        computed={"tech_weight_pct": round(tech_pct, 1)},
        confidence_pct=83,
    )


def _risk_reduction_answer(ctx: dict[str, Any], *, beginner: bool) -> InvestmentSolverResult:
    rows = _weight_rows(ctx)
    if beginner:
        lines = [
            "**Ideas to reduce risk (tradeoffs, not advice):**",
            "- **Add bonds or balanced funds** to cushion stock drops.",
            "- **Trim your largest position** if one fund dominates the portfolio.",
            "- **Reduce tech/growth overlap** if QQQ/VGT-style funds stack together.",
            "- **Rebalance toward targets** instead of letting winners run unchecked.",
        ]
        if rows:
            top_ticker, top_pct = rows[0]
            if top_pct >= 25:
                lines.append(f"- Start with **{top_ticker}** (**{top_pct:.1f}%**) — largest concentration lever.")
    else:
        lines = [
            "**Risk-reduction levers:**",
            "- Increase defensive allocation (IGSB/BND-style) to lower portfolio beta.",
            "- Cut top-weight concentration and correlated growth ETFs.",
            "- Tighten rebalance bands to prevent drift into higher-volatility weights.",
        ]
        vol = str(_ctx_value(ctx, "volatility", default="")).strip()
        if vol:
            lines.append(f"- Current historical vol **{vol}** — simulate impact of +10% bond sleeve in full AMI analysis.")

    return InvestmentSolverResult(
        short_answer="\n".join(lines),
        math_idea="Defensive allocation + de-concentration reduce portfolio variance.",
        problem_type="risk_reduction",
        model_name="Investment risk coach",
        confidence_pct=79,
    )


def _coach_answer(ctx: dict[str, Any], *, beginner: bool) -> InvestmentSolverResult:
    objective = str(_ctx_value(ctx, "objective", default="")).strip() or "your goal"
    if beginner:
        text = (
            f"**Portfolio coaching snapshot** for **{objective}**:\n"
            "- **Diversification** = not betting everything on one outcome.\n"
            "- **Allocation** = how much goes to stocks, bonds, and other assets.\n"
            "- **Rebalancing** = resetting mix when markets push weights off-plan.\n"
            "Ask a specific question (concentration, tech exposure, rebalance) for a tailored read on your holdings."
        )
    else:
        text = (
            f"Objective **{objective}** — framework: expected return vs volatility vs concentration vs correlation. "
            "Use Portfolio Health metrics, then stress single-factor tilts (tech, top weight, rate sensitivity)."
        )
    return InvestmentSolverResult(
        short_answer=text,
        math_idea="Educational portfolio construction framing.",
        problem_type="investment_coach",
        model_name="Investment coach",
        confidence_pct=74,
    )


def _route_for_intent(intent: str) -> InvestmentSolverRoute:
    labels = {
        "portfolio_concentration": ("portfolio_concentration", "Investment concentration analyst"),
        "rebalance_allocation": ("rebalance_allocation", "Investment allocation analyst"),
        "portfolio_risk": ("portfolio_risk", "Investment risk analyst"),
        "sector_exposure": ("sector_exposure", "Investment sector exposure analyst"),
        "risk_reduction": ("risk_reduction", "Investment risk coach"),
        "investment_coach": ("investment_coach", "Investment coach"),
        "etf_overlap": ("etf_overlap", "ETF overlap analyst"),
        "diversification": ("diversification", "Diversification analyst"),
        "scenario_stress": ("scenario_stress", "Portfolio scenario analyst"),
        "valuation": ("valuation", "Valuation analyst"),
        "macro_rates": ("macro_rates", "Interest rate scenario analyst"),
        "macro_recession": ("macro_recession", "Recession scenario analyst"),
        "macro_inflation": ("macro_inflation", "Inflation scenario analyst"),
        "allocation_recommendation": ("allocation_recommendation", "Allocation recommendation analyst"),
    }
    problem_type, model_name = labels.get(intent, ("investment_generic", "Investment analyst"))
    return InvestmentSolverRoute(
        problem_type=problem_type,
        model_name=model_name,
        model_rationale=f"Routed from investment intent `{intent}`.",
    )


def solve_instant_investment_insight(
    question: str,
    context: dict[str, Any] | None,
) -> tuple[InvestmentSolverRoute, InvestmentSolverResult] | None:
    q = str(question or "").strip()
    if not q:
        return None
    ctx = dict(context or {})
    try:
        from investment_ami_context import detect_investment_send_intent, intent_supported
    except ImportError:
        return None

    page = str(ctx.get("page") or ctx.get("source_page") or "").strip()
    intent = detect_investment_send_intent(q, page)
    if not intent_supported(intent):
        return None

    beginner = _beginner(ctx)
    phase2_intents = {
        "portfolio_concentration",
        "portfolio_risk",
        "etf_overlap",
        "diversification",
        "scenario_stress",
        "valuation",
        "macro_rates",
        "macro_recession",
        "macro_inflation",
        "allocation_recommendation",
    }
    if intent in phase2_intents:
        from investment_ami_phase2_solvers import solve_phase2_or_structured

        pair = solve_phase2_or_structured(intent, ctx, beginner=beginner, question=q)
        if pair:
            return pair

    if intent == "portfolio_concentration":
        result = _concentration_answer(ctx, beginner=beginner)
    elif intent == "rebalance_allocation":
        result = _rebalance_answer(ctx, beginner=beginner)
    elif intent == "portfolio_risk":
        result = _portfolio_risk_answer(ctx, beginner=beginner)
    elif intent == "sector_exposure":
        result = _tech_exposure_answer(ctx, beginner=beginner)
    elif intent == "risk_reduction":
        result = _risk_reduction_answer(ctx, beginner=beginner)
    else:
        result = _coach_answer(ctx, beginner=beginner)

    route = _route_for_intent(intent)
    result.problem_type = route.problem_type
    result.model_name = route.model_name
    return route, result
