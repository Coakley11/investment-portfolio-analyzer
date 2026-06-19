"""Allocation recommendation analyst — convert portfolio signals into investor actions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

import etf_holdings as eh
from investment_ami_answer_format import build_allocation_sections
from investment_ami_exposure import (
    format_portfolio_weights_table,
    format_tech_exposure_calculation_chain,
    resolve_tech_exposure,
)
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


def _subtract_increase_funding(
    weights: dict[str, float],
    to_ticker: str,
    amount: float,
    from_ticker: str,
) -> dict[str, float]:
    """Reduce source sleeve(s) to fund an increase without going below 0%. Returns reductions by ticker."""
    reductions: dict[str, float] = {}
    to_sym = str(to_ticker or "").strip().upper()
    try:
        need = float(amount)
    except (TypeError, ValueError):
        return reductions
    if not to_sym or need <= 0:
        return reductions

    others = [t for t in weights if t != to_sym]
    if from_ticker == "__proportional__":
        avail = {t: float(weights.get(t, 0.0)) for t in others}
        total = sum(avail.values())
        if total <= 0:
            return reductions
        take_total = min(need, total)
        for sym, w in avail.items():
            reduction = take_total * (w / total)
            weights[sym] = max(0.0, weights.get(sym, 0.0) - reduction)
            if reduction > 0.001:
                reductions[sym] = reductions.get(sym, 0.0) + reduction
        return reductions

    if from_ticker == "__equal__":
        remaining = min(need, sum(float(weights.get(t, 0.0)) for t in others))
        active = list(others)
        while remaining > 0.01 and active:
            share = remaining / len(active)
            next_active: list[str] = []
            for sym in active:
                current = float(weights.get(sym, 0.0))
                take = min(share, current)
                weights[sym] = max(0.0, current - take)
                remaining -= take
                if take > 0.001:
                    reductions[sym] = reductions.get(sym, 0.0) + take
                if weights[sym] > 0.01:
                    next_active.append(sym)
            active = next_active
        return reductions

    from_sym = str(from_ticker or "").strip().upper()
    if from_sym:
        current = float(weights.get(from_sym, 0.0))
        take = min(need, current)
        weights[from_sym] = max(0.0, current - take)
        if take > 0.001:
            reductions[from_sym] = take
    return reductions


def _filter_reallocations_for_overrides(
    baseline: dict[str, float],
    overrides: dict[str, float],
    reallocations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Only keep reallocations for sleeves actually reduced in current overrides."""
    kept: list[dict[str, Any]] = []
    for item in reallocations:
        if not isinstance(item, dict):
            continue
        from_t = str(item.get("from_ticker") or "").strip().upper()
        if not from_t or from_t not in overrides:
            continue
        try:
            amount = float(item.get("amount_pct") or 0)
        except (TypeError, ValueError):
            continue
        if amount <= 0:
            continue
        base = float(baseline.get(from_t, 0.0))
        new_w = float(overrides.get(from_t, base))
        if base - new_w >= amount - 0.01:
            kept.append(item)
    return kept


def _filter_increase_funding_for_overrides(
    baseline: dict[str, float],
    overrides: dict[str, float],
    increase_funding: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Only keep funding rows for sleeves actually increased in current overrides."""
    kept: list[dict[str, Any]] = []
    for item in increase_funding:
        if not isinstance(item, dict):
            continue
        to_t = str(item.get("to_ticker") or "").strip().upper()
        if not to_t or to_t not in overrides:
            continue
        try:
            amount = float(item.get("amount_pct") or 0)
        except (TypeError, ValueError):
            continue
        if amount <= 0:
            continue
        base = float(baseline.get(to_t, 0.0))
        new_w = float(overrides.get(to_t, base))
        if new_w - base >= amount - 0.01:
            kept.append(item)
    return kept


def _apply_explicit_reallocation(
    baseline: dict[str, float],
    overrides: dict[str, float],
    reallocations: list[dict[str, Any]],
    increase_funding: list[dict[str, Any]] | None = None,
    *,
    funding_breakdown: list[dict[str, Any]] | None = None,
) -> dict[str, float]:
    """Option B: explicit destinations for freed weight and sources for increased sleeves."""
    reallocations = _filter_reallocations_for_overrides(baseline, overrides, reallocations)
    funding_list = _filter_increase_funding_for_overrides(
        baseline, overrides, list(increase_funding or [])
    )
    weights = {str(k).upper(): float(v) for k, v in baseline.items()}
    for ticker, new_w in overrides.items():
        sym = str(ticker or "").strip().upper()
        if sym and new_w >= 0:
            weights[sym] = float(new_w)
    for item in reallocations:
        if not isinstance(item, dict):
            continue
        from_t = str(item.get("from_ticker") or "").strip().upper()
        try:
            amount = float(item.get("amount_pct") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        to_t = str(item.get("to_ticker") or "").strip()
        if not from_t or amount <= 0:
            continue
        if to_t == "__equal__":
            others = [t for t in weights if t != from_t]
            share = amount / len(others) if others else 0.0
            for sym in others:
                weights[sym] = weights.get(sym, 0.0) + share
        elif to_t:
            weights[to_t.upper()] = weights.get(to_t.upper(), 0.0) + amount
    for item in funding_list:
        if not isinstance(item, dict):
            continue
        to_t = str(item.get("to_ticker") or "").strip().upper()
        from_t = str(item.get("from_ticker") or "").strip()
        try:
            amount = float(item.get("amount_pct") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        if not to_t or amount <= 0:
            continue
        reductions = _subtract_increase_funding(weights, to_t, amount, from_t)
        if funding_breakdown is not None:
            label = from_t
            if from_t == "__proportional__":
                label = "proportional"
            elif from_t == "__equal__":
                label = "equal"
            funding_breakdown.append(
                {
                    "to_ticker": to_t,
                    "amount_pct": amount,
                    "from_mode": label,
                    "reductions": dict(reductions),
                }
            )
    weights = {t: max(0.0, float(w)) for t, w in weights.items()}
    total = sum(weights.values())
    if not funding_list and total > 0 and abs(total - 100.0) > 0.25:
        weights = {t: w / total * 100.0 for t, w in weights.items()}
    return weights


def _proposed_weight_rows(
    baseline: dict[str, float],
    weights: dict[str, float],
) -> list[tuple[str, float]]:
    """All baseline tickers in proposed mix, including sleeves taken to 0%."""
    tickers = set(baseline) | set(weights)
    rows = [(t, float(weights.get(t, 0.0))) for t in tickers]
    return sorted(rows, key=lambda x: x[1], reverse=True)


def _rows_with_allocation_overrides(ctx: dict[str, Any]) -> list[tuple[str, float]]:
    """Apply scenario allocation overrides with explicit reallocation (Option B)."""
    rows = _weight_rows(ctx)
    if not rows:
        return rows
    params = dict(ctx.get("scenario_params") or {})
    overrides = params.get("allocation_overrides")
    if not isinstance(overrides, dict) or not overrides:
        return rows
    baseline = {t: p for t, p in rows}
    parsed_overrides: dict[str, float] = {}
    for ticker, raw in overrides.items():
        sym = str(ticker or "").strip().upper()
        pct = _parse_weight_pct(raw)
        if sym and pct is not None and pct >= 0:
            parsed_overrides[sym] = pct
    realloc_raw = params.get("allocation_reallocations")
    reallocations: list[dict[str, Any]] = []
    if isinstance(realloc_raw, list):
        reallocations = [r for r in realloc_raw if isinstance(r, dict)]
    elif isinstance(params.get("allocation_reallocate"), dict):
        reallocations = [params["allocation_reallocate"]]
    funding_raw = params.get("allocation_increase_funding")
    increase_funding: list[dict[str, Any]] = []
    if isinstance(funding_raw, list):
        increase_funding = [r for r in funding_raw if isinstance(r, dict)]
    breakdown: list[dict[str, Any]] = []
    weights = _apply_explicit_reallocation(
        baseline,
        parsed_overrides,
        reallocations,
        increase_funding,
        funding_breakdown=breakdown,
    )
    return _proposed_weight_rows(baseline, weights)


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


def _rebalance_verdict(
    *,
    focus: str,
    recs: list[SleeveRecommendation],
    drift: Any,
    top3: float,
    risk_tolerance: str,
) -> str:
    if focus != "rebalance":
        return ""
    rebalance_recs = [r for r in recs if r.action in ("rebalance", "reduce")]
    max_drift = 0.0
    if isinstance(drift, dict) and drift:
        for raw in drift.values():
            text = str(raw).replace("pp", "").replace("+", "").replace("%", "").strip()
            try:
                max_drift = max(max_drift, abs(float(text)))
            except (TypeError, ValueError):
                continue
    if max_drift >= 5.0 or len(rebalance_recs) >= 2:
        lead = "**Yes, rebalance recommended**"
        why = (
            f"Largest sleeve drift is about **{max_drift:.1f} pp** vs targets"
            if max_drift >= 3
            else "Multiple sleeves are outside your tolerance band"
        )
    elif max_drift >= 2.5 or rebalance_recs:
        lead = "**Moderate rebalance may be appropriate**"
        why = "Drift is noticeable but not extreme — review before trading."
    else:
        lead = "**No significant rebalance needed**"
        why = f"Current weights are within typical bands for **{risk_tolerance}** tolerance (top-3 **{top3:.1f}%**)."
    return f"{lead} — {why}"


def _format_rebalance_candidates(recs: list[SleeveRecommendation]) -> str:
    blocks: list[str] = []
    for label, verbs in (
        ("Reduce", {"reduce", "rebalance"}),
        ("Increase", {"increase"}),
        ("Hold", {"hold"}),
        ("Monitor", {"monitor"}),
    ):
        lines = _format_action_lines(recs, verbs)
        if lines:
            blocks.append(f"**{label}**\n{lines}")
    return "\n\n".join(blocks)


def _portfolio_rows_differ(
    base_rows: list[tuple[str, float]],
    adj_rows: list[tuple[str, float]],
    *,
    tolerance: float = 0.05,
) -> bool:
    base = {t: p for t, p in base_rows}
    adj = {t: p for t, p in adj_rows}
    tickers = set(base) | set(adj)
    return any(abs(base.get(t, 0.0) - adj.get(t, 0.0)) > tolerance for t in tickers)


def _diversification_summary(profile: dict[str, float | int | str], n_rows: int) -> str:
    sleeves = int(profile.get("n_holdings") or n_rows or 0)
    equity = float(profile.get("equity") or 0) * 100
    bonds = float(profile.get("bonds") or 0) * 100
    return f"**{sleeves}** sleeves; equity **{equity:.0f}%** / bonds **{bonds:.0f}%**"


def format_net_allocation_changes(
    base_rows: list[tuple[str, float]],
    prop_rows: list[tuple[str, float]],
) -> str:
    baseline = {t: p for t, p in base_rows}
    proposed = {t: p for t, p in prop_rows}
    tickers = sorted(set(baseline) | set(proposed), key=lambda t: baseline.get(t, proposed.get(t, 0)), reverse=True)
    lines: list[str] = []
    for ticker in tickers:
        delta = float(proposed.get(ticker, 0.0)) - float(baseline.get(ticker, 0.0))
        if abs(delta) < 0.01:
            lines.append(f"- **{ticker}**: 0%")
        elif delta > 0:
            lines.append(f"- **{ticker}**: +{delta:.1f}%")
        else:
            lines.append(f"- **{ticker}**: {delta:.1f}%")
    return "\n".join(lines)


def format_funding_breakdown(
    baseline: dict[str, float],
    overrides: dict[str, float],
    params: dict[str, Any],
) -> str:
    """Human-readable funding sources for sleeve increases."""
    realloc_raw = params.get("allocation_reallocations")
    reallocations: list[dict[str, Any]] = []
    if isinstance(realloc_raw, list):
        reallocations = [r for r in realloc_raw if isinstance(r, dict)]
    funding_raw = params.get("allocation_increase_funding")
    increase_funding: list[dict[str, Any]] = []
    if isinstance(funding_raw, list):
        increase_funding = [r for r in funding_raw if isinstance(r, dict)]
    if not increase_funding:
        return ""

    parsed_overrides = {str(k).upper(): float(v) for k, v in overrides.items()}
    breakdown: list[dict[str, Any]] = []
    _apply_explicit_reallocation(
        baseline,
        parsed_overrides,
        reallocations,
        increase_funding,
        funding_breakdown=breakdown,
    )
    if not breakdown:
        return ""

    blocks: list[str] = []
    for item in breakdown:
        to_t = str(item.get("to_ticker") or "").upper()
        amount = float(item.get("amount_pct") or 0)
        mode = str(item.get("from_mode") or "")
        reductions = item.get("reductions") if isinstance(item.get("reductions"), dict) else {}
        if not to_t or amount <= 0 or not reductions:
            continue
        mode_label = {
            "proportional": "proportional across other sleeves",
            "equal": "equal across other sleeves",
        }.get(mode, f"**{mode}**")
        blocks.append(f"Additional **{amount:.1f}%** allocated to **{to_t}** (funded {mode_label}):")
        for sym in sorted(reductions, key=lambda t: reductions[t], reverse=True):
            blocks.append(f"- **{sym}**: -{float(reductions[sym]):.1f}%")
    return "\n\n".join(blocks)


def _format_before_after_comparison_table(
    base_rows: list[tuple[str, float]],
    adj_rows: list[tuple[str, float]],
    ctx: dict[str, Any],
) -> str:
    if not _portfolio_rows_differ(base_rows, adj_rows):
        return ""
    base_ctx = _ctx_with_adjusted_weights(ctx, base_rows)
    adj_ctx = _ctx_with_adjusted_weights(ctx, adj_rows)
    base_exp = resolve_tech_exposure(base_ctx)
    adj_exp = resolve_tech_exposure(adj_ctx)
    base_prof = allocation_profile_from_ctx(base_ctx)
    adj_prof = allocation_profile_from_ctx(adj_ctx)
    base_rec = recession_portfolio_impacts(base_prof)
    adj_rec = recession_portfolio_impacts(adj_prof)
    base_top_ticker, base_top = base_rows[0] if base_rows else ("—", 0.0)
    adj_top_ticker, adj_top = adj_rows[0] if adj_rows else ("—", 0.0)
    base_top3 = sum(p for _, p in base_rows[:3])
    adj_top3 = sum(p for _, p in adj_rows[:3])
    top_label = base_top_ticker if base_top_ticker == adj_top_ticker else f"{base_top_ticker} / {adj_top_ticker}"
    return "\n".join(
        [
            "| Metric | Current | Proposed |",
            "| --- | --- | --- |",
            (
                f"| Tech exposure | **{float(base_exp.get('total_pct') or 0):.1f}%** "
                f"| **{float(adj_exp.get('total_pct') or 0):.1f}%** |"
            ),
            f"| Top sleeve ({top_label}) | **{base_top:.1f}%** | **{adj_top:.1f}%** |",
            f"| Top-3 concentration | **{base_top3:.1f}%** | **{adj_top3:.1f}%** |",
            (
                f"| Recession sensitivity (illustrative) | **{base_rec['net_return_shift_pp']:+.1f} pp** "
                f"| **{adj_rec['net_return_shift_pp']:+.1f} pp** |"
            ),
            (
                f"| Diversification (sleeves / equity-bond) | {_diversification_summary(base_prof, len(base_rows))} "
                f"| {_diversification_summary(adj_prof, len(adj_rows))} |"
            ),
        ]
    )


def _simulated_impact_summary(base_rows: list[tuple[str, float]], adj_rows: list[tuple[str, float]], ctx: dict) -> str:
    if not _portfolio_rows_differ(base_rows, adj_rows):
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
    drift = ctx.get("rebalance_drift")

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

    rebalance_lead = _rebalance_verdict(
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
    portfolio_changed = _portfolio_rows_differ(base_rows, rows)
    comparison_table = _format_before_after_comparison_table(base_rows, rows, ctx) if portfolio_changed and not beginner else ""
    net_changes = format_net_allocation_changes(base_rows, rows) if portfolio_changed else ""
    scenario_params = dict(ctx.get("scenario_params") or {})
    overrides_raw = scenario_params.get("allocation_overrides")
    funding_breakdown = ""
    if portfolio_changed and isinstance(overrides_raw, dict) and overrides_raw:
        funding_breakdown = format_funding_breakdown(
            {t: p for t, p in base_rows},
            {str(k).upper(): float(v) for k, v in overrides_raw.items()},
            scenario_params,
        )

    base_exposure = resolve_tech_exposure(_ctx_with_adjusted_weights(ctx, base_rows))
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
    rebalance_block = _format_rebalance_candidates(recs) if focus == "rebalance" or any(
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
        risk_notes=_allocation_risk_notes(beginner),
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
