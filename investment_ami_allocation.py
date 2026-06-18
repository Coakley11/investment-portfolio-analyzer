"""Allocation recommendation analyst — convert portfolio signals into investor actions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

import etf_holdings as eh
from investment_ami_answer_format import build_allocation_sections
from investment_ami_exposure import resolve_tech_exposure
from investment_ami_instant_solver import InvestmentSolverResult, _parse_weight_pct, _portfolio_label, _weight_rows
from investment_ami_macro import allocation_profile_from_ctx, recession_portfolio_impacts

ActionVerb = Literal["increase", "reduce", "hold", "monitor", "rebalance"]

_DEFENSIVE_TICKERS = frozenset({"BND", "AGG", "TLT", "BIL", "SCHZ", "IEF", "VGSH", "SHY"})
_GROWTH_TICKERS = frozenset({"QQQ", "VGT", "XLK", "MGK", "VUG", "ARKK"})


def _tickers_mentioned_in_question(question: str) -> list[str]:
    q = re.sub(r"[^A-Z0-9 ]", " ", str(question or "").upper())
    known = ("VOO", "QQQ", "VTI", "SPY", "IVV", "SCHD", "VYM", "VNQ", "BND", "VXUS", "VGT", "MGK", "AGG", "BIL")
    return [t for t in known if re.search(rf"\b{t}\b", q)]


@dataclass
class SleeveRecommendation:
    ticker: str
    weight_pct: float
    action: ActionVerb
    rationale: str


def _risk_tolerance_from_ctx(ctx: dict[str, Any]) -> str:
    params = dict(ctx.get("scenario_params") or {})
    raw = str(params.get("risk_tolerance") or ctx.get("risk_tolerance") or "Moderate").strip()
    low = raw.lower()
    if "conserv" in low:
        return "Conservative"
    if "aggress" in low:
        return "Aggressive"
    return "Moderate"


def _concentration_band(risk_tolerance: str) -> tuple[float, float]:
    """Return (monitor_pct, reduce_pct) top-weight thresholds."""
    if risk_tolerance == "Conservative":
        return 20.0, 30.0
    if risk_tolerance == "Aggressive":
        return 30.0, 45.0
    return 25.0, 35.0


def _tech_threshold(risk_tolerance: str) -> float:
    if risk_tolerance == "Conservative":
        return 25.0
    if risk_tolerance == "Aggressive":
        return 45.0
    return 35.0


def _rows_with_allocation_overrides(ctx: dict[str, Any]) -> list[tuple[str, float]]:
    """Apply scenario allocation overrides and renormalize to 100%."""
    rows = _weight_rows(ctx)
    if not rows:
        return rows
    params = dict(ctx.get("scenario_params") or {})
    overrides = params.get("allocation_overrides")
    if not isinstance(overrides, dict) or not overrides:
        return rows
    weights = {t: p for t, p in rows}
    for ticker, raw in overrides.items():
        sym = str(ticker or "").strip().upper()
        pct = _parse_weight_pct(raw)
        if sym and pct is not None and pct >= 0:
            weights[sym] = pct
    total = sum(weights.values())
    if total <= 0:
        return rows
    norm = [(t, w / total * 100.0) for t, w in weights.items()]
    return sorted(norm, key=lambda x: x[1], reverse=True)


def has_defensive_row(rows: list[tuple[str, float]]) -> bool:
    return any(t in _DEFENSIVE_TICKERS for t, _ in rows)


def _ctx_with_adjusted_weights(ctx: dict[str, Any], rows: list[tuple[str, float]]) -> dict[str, Any]:
    out = dict(ctx)
    out["current_weights"] = {t: f"{p:.1f}%" for t, p in rows}
    return out


def _parse_recommendation_focus(question: str) -> str:
    q = str(question or "").lower()
    if any(p in q for p in ("add more", "add to", "should i add", "which etf should i add", "increase")):
        return "add"
    if any(p in q for p in ("reduce", "trim", "cut", "sell", "which etf should i reduce", "decrease")):
        return "reduce"
    if "rebalance" in q:
        return "rebalance"
    if any(p in q for p in ("reasonable", "allocation reasonable", "is my allocation")):
        return "reasonable"
    if any(p in q for p in ("improve", "change", "should i do", "what should i")):
        return "change"
    return "general"


def _asset_class_label(ticker: str) -> str:
    try:
        return str(eh.infer_portfolio_fund_info(ticker).get("asset_type") or "Equity ETF")
    except Exception:
        return "Equity ETF"


def _build_strengths(rows: list[tuple[str, float]], profile: dict, *, n_holdings: int) -> list[str]:
    strengths: list[str] = []
    if n_holdings >= 3:
        strengths.append(f"**{n_holdings} fund sleeves** — not a single-position portfolio.")
    top_ticker, top_pct = rows[0] if rows else ("", 0.0)
    if top_pct < 35:
        strengths.append(f"Top sleeve **{top_ticker}** at **{top_pct:.1f}%** — no extreme single-fund dominance.")
    eq = float(profile.get("equity") or 0) * 100
    if eq >= 40 and eq <= 80:
        strengths.append(f"Balanced equity sleeve (**{eq:.0f}%**) with room for diversifiers.")
    intl = sum(p for t, p in rows if t in {"VXUS", "VEA", "IEFA", "IXUS", "EFA"})
    if intl >= 15:
        strengths.append(f"International exposure via **{intl:.0f}%** non-US sleeve(s).")
    broad = sum(p for t, p in rows if t in {"VTI", "VOO", "SPY", "IVV"})
    if broad >= 30:
        strengths.append(f"Broad US market core (**{broad:.0f}%**) anchors the mix.")
    if not strengths and rows:
        alloc = ", ".join(f"**{t}** {p:.1f}%" for t, p in rows[:4])
        strengths.append(f"Clear fund-level mix: {alloc}.")
    return strengths[:5]


def _build_weaknesses(
    rows: list[tuple[str, float]],
    profile: dict,
    *,
    tech_pct: float,
    top3: float,
    risk_tolerance: str,
) -> list[str]:
    weaknesses: list[str] = []
    monitor_pct, reduce_pct = _concentration_band(risk_tolerance)
    top_ticker, top_pct = rows[0] if rows else ("", 0.0)
    if top_pct >= monitor_pct:
        weaknesses.append(
            f"**Allocation concentration** — top sleeve **{top_ticker}** is **{top_pct:.1f}%** "
            f"(watch band ≥ **{monitor_pct:.0f}%** for {risk_tolerance.lower()} tolerance)."
        )
    if top3 >= 75:
        weaknesses.append(f"**Top-3 fund sleeves = {top3:.1f}%** — outcomes track a small set of ETFs closely.")
    tech_thresh = _tech_threshold(risk_tolerance)
    if tech_pct >= tech_thresh:
        weaknesses.append(
            f"**Technology exposure ~{tech_pct:.1f}%** exceeds a **{tech_thresh:.0f}%** comfort band "
            f"for {risk_tolerance.lower()} profiles."
        )
    bonds = float(profile.get("bonds") or 0) * 100
    tbills = float(profile.get("tbills") or 0) * 100
    defensive = bonds + tbills + float(profile.get("dividend") or 0) * 100
    if defensive < 10 and risk_tolerance == "Conservative":
        weaknesses.append("**No meaningful bond/cash ballast** — recession and rate shocks hit harder.")
    elif defensive < 5 and risk_tolerance == "Moderate":
        weaknesses.append("**Minimal defensive sleeves** — limited cushion in downturn scenarios.")
    reit = float(profile.get("reit") or 0) * 100
    if reit >= 15:
        weaknesses.append(f"**REIT sleeve {reit:.0f}%** — cyclical and rate-sensitive in stress scenarios.")
    return weaknesses[:6]


def _sleeve_recommendations(
    ctx: dict[str, Any],
    rows: list[tuple[str, float]],
    *,
    profile: dict,
    tech_pct: float,
    risk_tolerance: str,
    focus: str,
    mentioned: list[str],
) -> list[SleeveRecommendation]:
    recs: list[SleeveRecommendation] = []
    monitor_pct, reduce_pct = _concentration_band(risk_tolerance)
    tech_thresh = _tech_threshold(risk_tolerance)
    drift = ctx.get("rebalance_drift")
    drift_map: dict[str, str] = dict(drift) if isinstance(drift, dict) else {}

    bonds_pct = sum(p for t, p in rows if t in _DEFENSIVE_TICKERS)
    has_defensive = bonds_pct >= 5

    for ticker, pct in rows:
        action: ActionVerb = "hold"
        rationale = f"**{pct:.1f}%** weight is within a reasonable sleeve size for your mix."
        ac = _asset_class_label(ticker)

        if ticker in drift_map:
            d = str(drift_map[ticker])
            if "+" in d and _parse_weight_pct(d.replace("+", "")) and float(d.replace("+", "").replace("pp", "")) >= 3:
                action = "rebalance"
                rationale = f"Drift **{d}** vs objective — trim back toward target band."
            elif "-" in d:
                action = "rebalance"
                rationale = f"Drift **{d}** vs objective — add back toward target band."

        if ticker in _GROWTH_TICKERS and tech_pct >= tech_thresh:
            if risk_tolerance == "Conservative":
                action = "reduce"
                rationale = (
                    f"Growth/tech sleeve at **{pct:.1f}%** with total tech ~**{tech_pct:.1f}%** — "
                    "consider trimming for lower volatility."
                )
            elif risk_tolerance == "Moderate" and pct >= 20:
                action = "monitor"
                rationale = (
                    f"**{pct:.1f}%** growth tilt — acceptable for growth goals but watch drawdowns "
                    f"(tech exposure ~**{tech_pct:.1f}%**)."
                )
            else:
                action = "hold"
                rationale = (
                    f"**{pct:.1f}%** growth sleeve fits an aggressive profile; tech exposure ~**{tech_pct:.1f}%**."
                )

        if pct >= reduce_pct and action not in ("reduce", "rebalance"):
            action = "reduce" if risk_tolerance != "Aggressive" else "monitor"
            rationale = (
                f"Top fund sleeve at **{pct:.1f}%** — above **{reduce_pct:.0f}%** "
                f"{risk_tolerance.lower()} concentration band."
            )
        elif pct >= monitor_pct and action == "hold":
            action = "monitor"
            rationale = f"**{pct:.1f}%** — largest sleeve; monitor drift vs your target mix."

        if ticker in {"VTI", "VOO", "SPY", "IVV"} and pct >= 30 and action in ("hold", "monitor"):
            action = "hold"
            rationale = f"Core **{ac}** anchor at **{pct:.1f}%** — reasonable foundation sleeve."

        if focus == "add" and mentioned and ticker in mentioned:
            action = "increase"
            rationale = f"You asked about adding — **{ticker}** at **{pct:.1f}%**; confirm it fits targets before sizing up."
        if focus == "reduce" and mentioned and ticker in mentioned:
            action = "reduce"
            rationale = f"You asked about reducing — trim **{ticker}** toward your objective weight if drift is large."

        recs.append(SleeveRecommendation(ticker=ticker, weight_pct=pct, action=action, rationale=rationale))

    if not has_defensive and risk_tolerance in ("Conservative", "Moderate"):
        target = "BND" if risk_tolerance == "Conservative" else "BIL"
        recs.append(
            SleeveRecommendation(
                ticker=target,
                weight_pct=0.0,
                action="increase",
                rationale=(
                    f"No bond/cash sleeve detected — consider adding **{target}** "
                    f"({'10–20%' if risk_tolerance == 'Conservative' else '5–15%'}) for defensive ballast."
                ),
            )
        )

    health_recs = ctx.get("rebalance_recommendation")
    if isinstance(health_recs, list):
        for text in health_recs[:2]:
            m = re.search(r"\b([A-Z]{2,5})\b", str(text))
            if m:
                sym = m.group(1)
                if not any(r.ticker == sym for r in recs):
                    recs.append(
                        SleeveRecommendation(
                            ticker=sym,
                            weight_pct=0.0,
                            action="rebalance",
                            rationale=str(text).strip(),
                        )
                    )

    order = {"rebalance": 0, "reduce": 1, "increase": 2, "monitor": 3, "hold": 4}
    recs.sort(key=lambda r: (order.get(r.action, 5), -r.weight_pct))
    return recs[:8]


def _format_action_lines(recs: list[SleeveRecommendation], verbs: set[str]) -> str:
    lines = [f"- **{r.action.upper()}** **{r.ticker}** — {r.rationale}" for r in recs if r.action in verbs]
    return "\n".join(lines) if lines else ""


def _simulated_impact_summary(base_rows: list[tuple[str, float]], adj_rows: list[tuple[str, float]], ctx: dict) -> str:
    if base_rows == adj_rows:
        return ""
    base_ctx = _ctx_with_adjusted_weights(ctx, base_rows)
    adj_ctx = _ctx_with_adjusted_weights(ctx, adj_rows)
    base_exp = resolve_tech_exposure(base_ctx)
    adj_exp = resolve_tech_exposure(adj_ctx)
    base_prof = allocation_profile_from_ctx(base_ctx)
    adj_prof = allocation_profile_from_ctx(adj_ctx)
    base_rec = recession_portfolio_impacts(base_prof)
    adj_rec = recession_portfolio_impacts(adj_prof)
    base_top3 = sum(p for _, p in base_rows[:3])
    adj_top3 = sum(p for _, p in adj_rows[:3])
    parts = [
        f"- Tech exposure: **{float(base_exp.get('total_pct') or 0):.1f}%** → **{float(adj_exp.get('total_pct') or 0):.1f}%**",
        f"- Top-3 concentration: **{base_top3:.1f}%** → **{adj_top3:.1f}%**",
        f"- Recession stress (illustrative): **{base_rec['net_return_shift_pp']:+.1f} pp** → **{adj_rec['net_return_shift_pp']:+.1f} pp**",
    ]
    return "\n".join(parts)


def allocation_recommendation_answer(
    ctx: dict[str, Any],
    *,
    beginner: bool,
    question: str = "",
) -> InvestmentSolverResult:
    """Portfolio-specific increase / reduce / hold / monitor / rebalance guidance."""
    base_rows = _weight_rows(ctx)
    rows = _rows_with_allocation_overrides(ctx)
    ctx_adj = _ctx_with_adjusted_weights(ctx, rows)
    risk_tolerance = _risk_tolerance_from_ctx(ctx)
    focus = _parse_recommendation_focus(question)
    mentioned = _tickers_mentioned_in_question(question)

    if not rows:
        direct = "Add holdings with weights first — I need your portfolio mix before I can recommend changes."
        sections = build_allocation_sections(
            direct_answer=direct,
            portfolio_analyst_view="Recommendations combine concentration, diversification, exposure, and macro stress signals.",
            recommended_actions="Enter tickers and weights, then ask again.",
            risk_notes=_allocation_risk_notes(beginner),
            beginner=beginner,
        )
        return InvestmentSolverResult(
            short_answer=direct,
            analyst_sections=sections,
            problem_type="allocation_recommendation",
            model_name="Allocation recommendation analyst",
            confidence_pct=55,
        )

    profile = allocation_profile_from_ctx(ctx_adj)
    exposure = resolve_tech_exposure(ctx_adj)
    tech_pct = float(exposure.get("total_pct") or 0)
    top_ticker, top_pct = rows[0]
    top3 = sum(p for _, p in rows[:3])
    recs = _sleeve_recommendations(
        ctx_adj,
        rows,
        profile=profile,
        tech_pct=tech_pct,
        risk_tolerance=risk_tolerance,
        focus=focus,
        mentioned=mentioned,
    )
    strengths = _build_strengths(rows, profile, n_holdings=len(rows))
    weaknesses = _build_weaknesses(rows, profile, tech_pct=tech_pct, top3=top3, risk_tolerance=risk_tolerance)

    alloc_label = ", ".join(f"**{t}** {p:.1f}%" for t, p in rows[:6])
    reduce_recs = [r for r in recs if r.action in ("reduce", "rebalance")]
    increase_recs = [r for r in recs if r.action == "increase"]
    hold_recs = [r for r in recs if r.action == "hold"]
    monitor_recs = [r for r in recs if r.action == "monitor"]

    if focus == "reasonable":
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
    elif increase_recs and not has_defensive_row(rows):
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

    increases = _format_action_lines(recs, {"increase"}) or "- **HOLD** current sleeves — no urgent adds flagged."
    reductions = _format_action_lines(recs, {"reduce", "rebalance"}) or "- **HOLD** — no trim/rebalance urgency at current weights."
    if monitor_recs:
        reductions += ("\n" if reductions else "") + _format_action_lines(recs, {"monitor"})

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

    sim = _simulated_impact_summary(base_rows, rows, ctx)
    what_if = sim if sim and not beginner else ""

    sections = build_allocation_sections(
        direct_answer=direct,
        portfolio_analyst_view=analyst,
        current_strengths="\n".join(f"- {s}" for s in strengths),
        current_weaknesses="\n".join(f"- {w}" for w in weaknesses) if weaknesses else "- No major structural flags at current weights.",
        potential_increases=increases,
        potential_reductions=reductions,
        tradeoffs=tradeoffs,
        what_if_scenarios=what_if,
        recommended_actions=" ".join(actions[:3]),
        risk_notes=_allocation_risk_notes(beginner),
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
        },
    )


def _allocation_risk_notes(beginner: bool) -> str:
    if beginner:
        return (
            "Educational allocation guidance based on your entered weights — not personal financial advice. "
            "Increase/reduce suggestions are illustrative, not trade instructions."
        )
    return (
        "Educational recommendation model only; not investment advice. "
        "Actions derive from concentration bands, exposure thresholds, drift, and macro stress — verify against your policy targets."
    )
