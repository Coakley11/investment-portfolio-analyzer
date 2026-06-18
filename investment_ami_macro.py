"""Macro scenario analysts for Investment AMI — rates, recession, inflation, unemployment."""

from __future__ import annotations

import re
from typing import Any

import numpy as np

import etf_holdings as eh
import portfolio_core as core
from investment_ami_answer_format import build_analyst_sections
from investment_ami_instant_solver import InvestmentSolverResult, _weight_rows


def parse_rate_rise_pct(question: str, *, default: float = 2.0) -> float:
    """Parse explicit rate rise magnitude from question text (percentage points)."""
    q = str(question or "").strip().lower()
    patterns = (
        r"interest rates?\s+(?:rise|rising|increase|go up|hike|jump)[^\d%]{0,30}(\d+(?:\.\d+)?)\s*%?",
        r"rates?\s+(?:rise|rising|increase|go up|hike|jump)[^\d%]{0,30}(\d+(?:\.\d+)?)\s*%?",
        r"(\d+(?:\.\d+)?)\s*%\s*(?:rate|interest rate)",
        r"(?:rise|rising|increase|hike|up)\s+(?:by\s+)?(\d+(?:\.\d+)?)\s*%?",
    )
    for pattern in patterns:
        match = re.search(pattern, q, flags=re.IGNORECASE)
        if match:
            try:
                val = float(match.group(1))
                if 0 < val <= 10:
                    return val
            except (TypeError, ValueError):
                continue
    if "rate" in q and any(w in q for w in ("rise", "rising", "increase", "hike", "higher")):
        return default
    return default


def allocation_profile_from_ctx(ctx: dict[str, Any]) -> dict[str, float | int | str]:
    """Build portfolio_core allocation profile from AMI context weights."""
    rows = _weight_rows(ctx)
    if not rows:
        return {
            "equity": 0.0,
            "bonds": 0.0,
            "tbills": 0.0,
            "reit": 0.0,
            "dividend": 0.0,
            "long_duration_bonds": 0.0,
            "short_duration_cash": 0.0,
            "tech": 0.0,
            "qqq_spy": 0.0,
            "n_holdings": 0,
            "top_ticker": "",
            "concentration": 0.0,
        }
    tickers = [t for t, _ in rows]
    weights = np.array([p / 100.0 for _, p in rows], dtype=float)
    asset_types = [eh.infer_portfolio_fund_info(t)["asset_type"] for t in tickers]
    return core.allocation_profile(tickers, weights, asset_types)


def rate_rise_portfolio_impacts(profile: dict[str, float | int | str], rate_bump_pct: float) -> dict[str, Any]:
    """
    Educational portfolio impact model for a rate rise shock.

    Scales portfolio_core Rising Rates coefficients to the requested bump (default 2pp).
    Returns component drags/lifts in illustrative annual return percentage points.
    """
    scale = float(rate_bump_pct) / 2.0
    eq = float(profile.get("equity") or 0)
    bonds = float(profile.get("bonds") or 0)
    tbills = float(profile.get("tbills") or 0)
    reit = float(profile.get("reit") or 0)
    long_bonds = float(profile.get("long_duration_bonds") or 0)
    growth = float(profile.get("qqq_spy") or 0) + float(profile.get("tech") or 0) * 0.35

    # Coefficients mirror portfolio_core._rate_environment_effects (Rising Rates), scaled to bump size.
    bond_duration_drag = (-0.060 * bonds - 0.040 * long_bonds) * scale * 100
    reit_drag = (-0.030 * reit) * scale * 100
    equity_valuation_drag = (-0.020 * eq) * scale * 100
    growth_compression = (-0.012 * growth) * scale * 100
    tbill_lift = (0.020 * tbills) * scale * 100

    components = {
        "bond_duration_drag_pp": round(bond_duration_drag, 2),
        "reit_drag_pp": round(reit_drag, 2),
        "equity_valuation_drag_pp": round(equity_valuation_drag, 2),
        "growth_compression_pp": round(growth_compression, 2),
        "tbill_lift_pp": round(tbill_lift, 2),
    }
    net_pp = sum(components.values())
    return {
        "rate_bump_pct": rate_bump_pct,
        "scale": scale,
        "components_pp": components,
        "net_return_shift_pp": round(net_pp, 2),
        "profile_pct": {
            "equity": round(eq * 100, 1),
            "bonds": round(bonds * 100, 1),
            "tbills": round(tbills * 100, 1),
            "reit": round(reit * 100, 1),
            "long_duration_bonds": round(long_bonds * 100, 1),
            "growth_proxy": round(growth * 100, 1),
        },
    }


def _default_risk_notes(beginner: bool) -> str:
    if beginner:
        return (
            "Educational scenario analysis based on your portfolio weights — not personal financial advice. "
            "Actual rate impacts depend on timing, starting yields, and market expectations."
        )
    return (
        "Educational macro scenario model only; not investment advice. "
        "Illustrative return shifts use scaled Rising Rates coefficients from portfolio_core."
    )


def macro_rates_answer(ctx: dict[str, Any], *, beginner: bool, question: str = "") -> InvestmentSolverResult:
    """Analyze portfolio sensitivity to an interest-rate rise shock."""
    rate_bump = parse_rate_rise_pct(question)
    profile = allocation_profile_from_ctx(ctx)
    impacts = rate_rise_portfolio_impacts(profile, rate_bump)
    comps = impacts["components_pp"]
    prof = impacts["profile_pct"]
    net = float(impacts["net_return_shift_pp"])
    rate_env = str(ctx.get("health_rate_env") or ctx.get("scenario_params", {}).get("rate_shock") or "").strip()

    if prof["equity"] + prof["bonds"] + prof["reit"] + prof["tbills"] <= 0:
        direct = "Add holdings with weights first — I need your portfolio mix to estimate rate sensitivity."
        sections = build_analyst_sections(
            direct_answer=direct,
            portfolio_analyst_view="Rate shocks hit bonds, REITs, and growth equities differently depending on sleeve weights.",
            recommended_actions="Enter tickers and weights, then ask again.",
            risk_notes=_default_risk_notes(beginner),
            beginner=beginner,
        )
        return InvestmentSolverResult(
            short_answer=direct,
            analyst_sections=sections,
            problem_type="macro_rates",
            model_name="Interest rate scenario analyst",
            confidence_pct=55,
        )

    if beginner:
        direct = (
            f"If interest rates rise **{rate_bump:.1f}%**, your portfolio could face a rough "
            f"**{abs(net):.1f} percentage-point** headwind on forward returns (simple model)."
        )
        if prof["bonds"] >= 20 or prof["long_duration_bonds"] >= 5:
            direct += f" Your **{prof['bonds']:.0f}%** bond sleeve is the main duration risk."
        elif prof["reit"] >= 10:
            direct += f" Your **{prof['reit']:.0f}%** REIT exposure is sensitive to higher rates."
        elif prof["growth_proxy"] >= 15:
            direct += " Growth-heavy holdings may see valuation pressure as discount rates rise."
        analyst = (
            "Higher rates usually hurt **long-duration bonds** first, then **REITs** and **growth stocks** "
            "(higher discount rates compress valuations). **Cash / T-Bills** often hold up better."
        )
    else:
        direct = (
            f"A **+{rate_bump:.1f}%** rate shock implies an illustrative portfolio return shift of "
            f"**{net:+.1f} pp** (scaled Rising Rates model)."
        )
        analyst = (
            f"Bond duration drag ≈ **{comps['bond_duration_drag_pp']:+.1f} pp** "
            f"({prof['bonds']:.0f}% bonds, {prof['long_duration_bonds']:.0f}% long-duration). "
            f"REIT drag ≈ **{comps['reit_drag_pp']:+.1f} pp** ({prof['reit']:.0f}% REIT). "
            f"Equity valuation drag ≈ **{comps['equity_valuation_drag_pp']:+.1f} pp**; "
            f"growth compression ≈ **{comps['growth_compression_pp']:+.1f} pp** "
            f"({prof['growth_proxy']:.0f}% growth proxy). "
            f"T-Bill lift ≈ **{comps['tbill_lift_pp']:+.1f} pp**."
        )
        if rate_env:
            analyst += f" Portfolio Health rate setting: **{rate_env}**."

    key_lines = [
        f"- Rate shock assumption: **+{rate_bump:.1f}%**",
        f"- Equity sleeve: **{prof['equity']:.1f}%**",
        f"- Bonds: **{prof['bonds']:.1f}%** (long-duration **{prof['long_duration_bonds']:.1f}%**)",
        f"- REIT: **{prof['reit']:.1f}%**",
        f"- T-Bills / cash-like: **{prof['tbills']:.1f}%**",
        f"- Growth proxy (QQQ/SPY/tech tilt): **{prof['growth_proxy']:.1f}%**",
        f"- Bond duration drag (est.): **{comps['bond_duration_drag_pp']:+.1f} pp**",
        f"- REIT sensitivity (est.): **{comps['reit_drag_pp']:+.1f} pp**",
        f"- Growth valuation compression (est.): **{comps['growth_compression_pp']:+.1f} pp**",
        f"- Net illustrative shift: **{net:+.1f} pp**",
    ]

    tradeoffs = (
        "**More long-duration bonds / REITs** → larger downside if rates jump.\n"
        "**More cash / short Treasuries** → better relative resilience, but lower long-run return potential.\n"
        "**Growth-heavy equity** → valuation compression risk even if earnings hold."
    )

    what_if = (
        f"- Rates **+{rate_bump:.1f}%** with current mix → **~{net:+.1f} pp** illustrative return shift\n"
        f"- If long-duration bonds trimmed → duration drag eases\n"
        f"- If REIT weight cut → rate sensitivity falls\n"
        f"- If T-Bill sleeve added → partial offset via higher cash yields"
    )

    actions: list[str] = []
    if prof["long_duration_bonds"] >= 5 or prof["bonds"] >= 25:
        actions.append(
            "Consider shortening bond duration (e.g. more aggregate/T-Bills, less long Treasury) if rate risk feels high."
        )
    if prof["reit"] >= 15:
        actions.append(
            f"REIT weight is **{prof['reit']:.0f}%** — monitor rate-sensitive real estate exposure in a rising-rate path."
        )
    if prof["growth_proxy"] >= 20:
        actions.append(
            "Growth tilt may face valuation compression — balance with value/dividend or defensive sleeves if uncomfortable."
        )
    if prof["tbills"] < 5 and net < -1.5:
        actions.append(
            "A modest cash or T-Bill sleeve can improve resilience when rates rise unexpectedly."
        )
    if not actions:
        actions.append(
            "Your mix is not heavily duration- or growth-concentrated — focus on whether the illustrative shock fits your risk tolerance."
        )

    sections = build_analyst_sections(
        direct_answer=direct,
        portfolio_analyst_view=analyst,
        key_variables="\n".join(key_lines),
        tradeoffs=tradeoffs,
        what_if_scenarios=what_if if not beginner else "",
        recommended_actions=" ".join(actions),
        risk_notes=_default_risk_notes(beginner),
        beginner=beginner,
    )
    conf = 80 if prof["bonds"] + prof["reit"] + prof["equity"] > 0 else 60
    return InvestmentSolverResult(
        short_answer=direct,
        analyst_sections=sections,
        problem_type="macro_rates",
        model_name="Interest rate scenario analyst",
        math_idea="Scaled Rising Rates coefficients × portfolio sleeve weights × rate bump size.",
        confidence_pct=conf,
        computed={
            "rate_bump_pct": rate_bump,
            "net_return_shift_pp": net,
            **{k: v for k, v in comps.items()},
            **prof,
        },
    )
