"""Macro scenario analysts for Investment AMI — rates, recession, inflation, unemployment."""

from __future__ import annotations

import re
from typing import Any

import numpy as np

import etf_holdings as eh
import portfolio_core as core
from investment_ami_answer_format import build_analyst_sections
from investment_ami_instant_solver import InvestmentSolverResult, _weight_rows


def parse_rate_rise_pct(question: str, *, default: float = 2.0, scenario_params: dict[str, Any] | None = None) -> float:
    """Parse explicit rate rise magnitude from scenario params or question text (percentage points)."""
    params = dict(scenario_params or {})
    raw_param = params.get("rate_rise_pct")
    if raw_param not in (None, ""):
        try:
            val = float(raw_param)
            if 0 <= val <= 10:
                return val
        except (TypeError, ValueError):
            pass
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
    params = dict(ctx.get("scenario_params") or {})
    rate_bump = parse_rate_rise_pct(question, scenario_params=params)
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


def _recession_probability_from_ctx(ctx: dict[str, Any]) -> float | None:
    """Return recession probability 0–1 from Portfolio Health settings when available."""
    for key in ("health_recession", "recession_probability"):
        raw = ctx.get(key)
        if raw is None or raw == "":
            continue
        try:
            val = float(raw)
            if val > 1.0:
                return min(1.0, val / 100.0)
            return min(1.0, max(0.0, val))
        except (TypeError, ValueError):
            continue
    params = dict(ctx.get("scenario_params") or {})
    raw = params.get("recession_scenario") or params.get("recession_probability")
    if raw not in (None, ""):
        try:
            val = float(str(raw).replace("%", "").strip())
            return min(1.0, val / 100.0 if val > 1.0 else val)
        except (TypeError, ValueError):
            pass
    return None


def recession_portfolio_impacts(
    profile: dict[str, float | int | str],
    *,
    severity_scale: float = 1.0,
) -> dict[str, Any]:
    """
    Educational recession stress model using portfolio_core Recession regime coefficients.

    Illustrative annual return shift in percentage points for a recession scenario.
    """
    eq = float(profile.get("equity") or 0)
    bonds = float(profile.get("bonds") or 0)
    tbills = float(profile.get("tbills") or 0)
    reit = float(profile.get("reit") or 0)
    dividend = float(profile.get("dividend") or 0)
    growth = float(profile.get("qqq_spy") or 0) + float(profile.get("tech") or 0) * 0.4

    scale = max(0.3, min(1.6, float(severity_scale or 1.0)))
    # Mirrors portfolio_core economic_regime "Recession" mapping.
    equity_earnings_drag = -0.180 * eq * 100 * scale
    reit_drag = -0.030 * reit * 100 * scale
    tbill_defensive = 0.020 * tbills * 100 * scale
    bond_defensive = 0.015 * bonds * 100 * scale
    growth_earnings_drag = -0.050 * growth * 100 * scale
    dividend_cushion = 0.010 * dividend * 100 * scale

    components = {
        "equity_earnings_drag_pp": round(equity_earnings_drag, 2),
        "reit_drag_pp": round(reit_drag, 2),
        "growth_cyclical_drag_pp": round(growth_earnings_drag, 2),
        "tbill_defensive_pp": round(tbill_defensive, 2),
        "bond_defensive_pp": round(bond_defensive, 2),
        "dividend_cushion_pp": round(dividend_cushion, 2),
    }
    net_pp = sum(components.values())
    defensive_pct = round((bonds + tbills + dividend) * 100, 1)
    return {
        "components_pp": components,
        "net_return_shift_pp": round(net_pp, 2),
        "volatility_multiplier": round(1.65 * scale, 2),
        "severity_scale": round(scale, 2),
        "defensive_sleeve_pct": defensive_pct,
        "profile_pct": {
            "equity": round(eq * 100, 1),
            "bonds": round(bonds * 100, 1),
            "tbills": round(tbills * 100, 1),
            "reit": round(reit * 100, 1),
            "dividend": round(dividend * 100, 1),
            "growth_proxy": round(growth * 100, 1),
        },
    }


def _recession_risk_notes(beginner: bool) -> str:
    if beginner:
        return (
            "Educational recession scenario based on your fund weights — not personal financial advice. "
            "Real recessions vary in depth, length, and policy response."
        )
    return (
        "Educational recession stress model only; not investment advice. "
        "Return shifts use portfolio_core Recession regime coefficients; volatility multiplier ≈ 1.65×."
    )


def macro_recession_answer(ctx: dict[str, Any], *, beginner: bool, question: str = "") -> InvestmentSolverResult:
    """Analyze portfolio vulnerability in a recession scenario."""
    profile = allocation_profile_from_ctx(ctx)
    params = dict(ctx.get("scenario_params") or {})
    try:
        from investment_ami_sliders import parse_recession_severity

        severity = parse_recession_severity(params)
    except ImportError:
        severity = float(params.get("recession_severity_scale") or 1.0)
    impacts = recession_portfolio_impacts(profile, severity_scale=severity)
    comps = impacts["components_pp"]
    prof = impacts["profile_pct"]
    net = float(impacts["net_return_shift_pp"])
    recession_prob = _recession_probability_from_ctx(ctx)
    regime = str(ctx.get("health_regime") or ctx.get("scenario_params", {}).get("economic_regime") or "").strip()

    if prof["equity"] + prof["bonds"] + prof["reit"] + prof["tbills"] <= 0:
        direct = "Add holdings with weights first — I need your portfolio mix to estimate recession vulnerability."
        sections = build_analyst_sections(
            direct_answer=direct,
            portfolio_analyst_view="Recessions usually pressure earnings and cyclical assets; defensive sleeves can partially offset.",
            recommended_actions="Enter tickers and weights, then ask again.",
            risk_notes=_recession_risk_notes(beginner),
            beginner=beginner,
        )
        return InvestmentSolverResult(
            short_answer=direct,
            analyst_sections=sections,
            problem_type="macro_recession",
            model_name="Recession scenario analyst",
            confidence_pct=55,
        )

    defensive = float(impacts["defensive_sleeve_pct"])
    if beginner:
        direct = (
            f"In a recession scenario, your portfolio could face an illustrative "
            f"**{abs(net):.1f} percentage-point** return headwind (simple model)."
        )
        if prof["equity"] >= 70 and defensive < 20:
            direct += " Your portfolio is **equity-heavy** with limited defensive ballast."
        elif defensive >= 30:
            direct += f" Your **{defensive:.0f}%** bond/cash/dividend sleeve may provide some cushion."
        analyst = (
            "Recessions typically hit **corporate earnings** and **cyclical growth** first. "
            "**Bonds, cash, and dividend** sleeves often hold up better — though not always. "
            "Fund-level diversification still matters because even broad ETFs can fall together in a downturn."
        )
    else:
        direct = (
            f"Recession stress implies an illustrative portfolio return shift of **{net:+.1f} pp** "
            f"(volatility ≈ **{impacts['volatility_multiplier']:.2f}×** historical)."
        )
        analyst = (
            f"Equity earnings drag ≈ **{comps['equity_earnings_drag_pp']:+.1f} pp** ({prof['equity']:.0f}% equity). "
            f"Growth/cyclical drag ≈ **{comps['growth_cyclical_drag_pp']:+.1f} pp** ({prof['growth_proxy']:.0f}% growth proxy). "
            f"REIT drag ≈ **{comps['reit_drag_pp']:+.1f} pp**. "
            f"Defensive offset: bonds **{comps['bond_defensive_pp']:+.1f} pp**, T-Bills **{comps['tbill_defensive_pp']:+.1f} pp**, "
            f"dividend cushion **{comps['dividend_cushion_pp']:+.1f} pp**."
        )
        if recession_prob is not None:
            analyst += f" Portfolio Health recession probability: **{recession_prob * 100:.0f}%**."
        if regime:
            analyst += f" Economic regime setting: **{regime}**."

    key_lines = [
        f"- Equity sleeve: **{prof['equity']:.1f}%**",
        f"- Growth / cyclical proxy: **{prof['growth_proxy']:.1f}%**",
        f"- Bonds: **{prof['bonds']:.1f}%**",
        f"- T-Bills / cash-like: **{prof['tbills']:.1f}%**",
        f"- Dividend sleeve: **{prof['dividend']:.1f}%**",
        f"- REIT: **{prof['reit']:.1f}%**",
        f"- Defensive sleeves (bonds + cash + dividend): **{defensive:.1f}%**",
        f"- Equity earnings drag (est.): **{comps['equity_earnings_drag_pp']:+.1f} pp**",
        f"- Growth/cyclical drag (est.): **{comps['growth_cyclical_drag_pp']:+.1f} pp**",
        f"- Net illustrative shift: **{net:+.1f} pp**",
        f"- Volatility multiplier (est.): **{impacts['volatility_multiplier']:.2f}×**",
    ]

    tradeoffs = (
        "**High equity / growth tilt** → larger recession drawdown potential, higher recovery upside later.\n"
        "**More defensive sleeves** → smaller recession hit, but may lag in expansions.\n"
        "**Concentrated fund sleeves** → recession outcomes still depend on a few ETFs, not hundreds of stocks."
    )

    what_if = (
        f"- Full recession scenario → **~{net:+.1f} pp** illustrative return shift\n"
        f"- If defensive sleeve raised to ~30% → recession drag likely eases\n"
        f"- If growth proxy trimmed → cyclical earnings hit falls\n"
        f"- Volatility could run **~{impacts['volatility_multiplier']:.0f}×** normal in stress"
    )

    actions: list[str] = []
    if prof["equity"] >= 75 and defensive < 25:
        actions.append(
            "Consider whether your equity-heavy mix matches recession tolerance — adding bonds, cash, or dividend sleeves can improve ballast."
        )
    if prof["growth_proxy"] >= 25:
        actions.append(
            f"Growth/cyclical proxy is **{prof['growth_proxy']:.0f}%** — monitor whether that tilt feels too aggressive for a downturn."
        )
    if prof["reit"] >= 15:
        actions.append(
            f"REIT sleeve **{prof['reit']:.0f}%** can be cyclical in recessions — confirm it fits your defensive plan."
        )
    if defensive >= 30:
        actions.append(
            f"Defensive allocation **{defensive:.0f}%** should help relative resilience — focus on whether the mix matches your goals."
        )
    if ctx.get("rebalance_recommendation"):
        recs = ctx.get("rebalance_recommendation")
        if isinstance(recs, list) and recs:
            actions.append(f"Health check suggests: {recs[0]}")
    if not actions:
        actions.append(
            "Compare this recession stress to your risk tolerance — adjust fund sleeves if the illustrative drawdown feels too large."
        )

    sections = build_analyst_sections(
        direct_answer=direct,
        portfolio_analyst_view=analyst,
        key_variables="\n".join(key_lines),
        tradeoffs=tradeoffs,
        what_if_scenarios=what_if if not beginner else "",
        recommended_actions=" ".join(actions),
        risk_notes=_recession_risk_notes(beginner),
        beginner=beginner,
    )
    conf = 82 if prof["equity"] + defensive > 0 else 60
    return InvestmentSolverResult(
        short_answer=direct,
        analyst_sections=sections,
        problem_type="macro_recession",
        model_name="Recession scenario analyst",
        math_idea="portfolio_core Recession regime coefficients × portfolio sleeve weights.",
        confidence_pct=conf,
        computed={
            "net_return_shift_pp": net,
            "defensive_sleeve_pct": defensive,
            "volatility_multiplier": impacts["volatility_multiplier"],
            **comps,
            **prof,
            **({"recession_probability_pct": round(recession_prob * 100, 1)} if recession_prob is not None else {}),
        },
    )


def parse_inflation_pct(params: dict[str, Any], *, default: float = 4.0) -> float:
    raw = params.get("inflation_pct")
    if raw in (None, ""):
        return default
    try:
        return max(2.0, min(10.0, float(raw)))
    except (TypeError, ValueError):
        return default


def inflation_portfolio_impacts(
    profile: dict[str, float | int | str],
    inflation_pct: float,
    *,
    nominal_return_assumption: float = 7.0,
) -> dict[str, Any]:
    """Illustrative inflation stress on portfolio sleeves (educational model)."""
    scale = float(inflation_pct) / 4.0
    eq = float(profile.get("equity") or 0)
    bonds = float(profile.get("bonds") or 0)
    tbills = float(profile.get("tbills") or 0)
    reit = float(profile.get("reit") or 0)
    growth = float(profile.get("qqq_spy") or 0) + float(profile.get("tech") or 0) * 0.35
    dividend = float(profile.get("dividend") or 0)

    bond_price_drag = (-0.050 * bonds - 0.030 * float(profile.get("long_duration_bonds") or 0)) * scale * 100
    equity_valuation_drag = (-0.022 * growth) * scale * 100
    earnings_real_erosion = (-0.015 * eq) * max(0.0, (inflation_pct - 2.0) / 2.0) * 100
    tbill_lift = (0.018 * tbills) * max(0.0, (inflation_pct - 2.0) / 2.0) * 100
    reit_mixed = (-0.012 * reit) * scale * 100 + (0.006 * reit) * max(0.0, inflation_pct - 3.0) / 3.0 * 100
    dividend_cushion = (0.008 * dividend) * max(0.0, inflation_pct - 2.5) / 2.5 * 100

    components = {
        "bond_price_drag_pp": round(bond_price_drag, 2),
        "equity_valuation_drag_pp": round(equity_valuation_drag, 2),
        "earnings_real_erosion_pp": round(earnings_real_erosion, 2),
        "tbill_rate_lift_pp": round(tbill_lift, 2),
        "reit_mixed_pp": round(reit_mixed, 2),
        "dividend_cushion_pp": round(dividend_cushion, 2),
    }
    net_pp = sum(components.values())
    real_return_est = round(nominal_return_assumption - inflation_pct, 1)
    return {
        "inflation_pct": inflation_pct,
        "nominal_return_assumption_pct": nominal_return_assumption,
        "real_return_estimate_pct": real_return_est,
        "components_pp": components,
        "net_return_shift_pp": round(net_pp, 2),
        "profile_pct": {
            "equity": round(eq * 100, 1),
            "bonds": round(bonds * 100, 1),
            "tbills": round(tbills * 100, 1),
            "reit": round(reit * 100, 1),
            "growth_proxy": round(growth * 100, 1),
            "dividend": round(dividend * 100, 1),
        },
    }


def _inflation_risk_notes(beginner: bool) -> str:
    if beginner:
        return (
            "Educational inflation scenario based on your fund weights — not personal financial advice. "
            "Real returns depend on earnings growth, starting yields, and policy response."
        )
    return (
        "Educational inflation stress model only; not investment advice. "
        "Illustrative shifts scale with inflation assumption and sleeve mix."
    )


def macro_inflation_answer(ctx: dict[str, Any], *, beginner: bool, question: str = "") -> InvestmentSolverResult:
    """Portfolio-specific inflation / purchasing-power analysis."""
    profile = allocation_profile_from_ctx(ctx)
    params = dict(ctx.get("scenario_params") or {})
    inflation_pct = parse_inflation_pct(params)
    q = str(question or "").lower()
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", q)
    if m and "inflation" in q:
        try:
            inflation_pct = max(2.0, min(10.0, float(m.group(1))))
        except (TypeError, ValueError):
            pass
    impacts = inflation_portfolio_impacts(profile, inflation_pct)
    comps = impacts["components_pp"]
    prof = impacts["profile_pct"]
    net = float(impacts["net_return_shift_pp"])
    real_ret = float(impacts["real_return_estimate_pct"])

    if prof["equity"] + prof["bonds"] + prof["reit"] + prof["tbills"] <= 0:
        direct = "Add holdings with weights first — I need your portfolio mix to estimate inflation exposure."
        sections = build_analyst_sections(
            direct_answer=direct,
            portfolio_analyst_view="Inflation erodes purchasing power; sleeve mix determines whether nominal returns keep up.",
            recommended_actions="Enter tickers and weights, then ask again.",
            risk_notes=_inflation_risk_notes(beginner),
            beginner=beginner,
        )
        return InvestmentSolverResult(
            short_answer=direct,
            analyst_sections=sections,
            problem_type="macro_inflation",
            model_name="Inflation scenario analyst",
            confidence_pct=55,
        )

    if inflation_pct >= 8:
        level = "severe inflation stress"
    elif inflation_pct >= 6:
        level = "high inflation"
    elif inflation_pct >= 4:
        level = "elevated inflation"
    else:
        level = "moderate inflation"

    if beginner:
        direct = (
            f"At **{inflation_pct:.0f}%** inflation ({level}), the main risk is **real-return erosion**. "
            f"If nominal returns are ~**{impacts['nominal_return_assumption_pct']:.0f}%**, illustrative real return is about **{real_ret:.1f}%**."
        )
        analyst = (
            "Inflation reduces purchasing power even when account balances rise. "
            "Equity-heavy portfolios need earnings growth to outpace inflation; "
            "bond-heavy portfolios can face yield/price pressure when inflation pushes rates higher."
        )
    else:
        direct = (
            f"At **{inflation_pct:.1f}%** inflation ({level}), illustrative portfolio return shift **{net:+.1f} pp** "
            f"with real-return estimate **{real_ret:.1f}%** (nominal **{impacts['nominal_return_assumption_pct']:.0f}%** − inflation)."
        )
        analyst = (
            f"Bond price drag ≈ **{comps['bond_price_drag_pp']:+.1f} pp** ({prof['bonds']:.0f}% bonds). "
            f"Growth valuation drag ≈ **{comps['equity_valuation_drag_pp']:+.1f} pp** ({prof['growth_proxy']:.0f}% growth proxy). "
            f"T-Bill lift ≈ **{comps['tbill_rate_lift_pp']:+.1f} pp** ({prof['tbills']:.0f}% cash-like). "
            f"REIT mixed effect ≈ **{comps['reit_mixed_pp']:+.1f} pp** ({prof['reit']:.0f}% REIT)."
        )

    key_lines = [
        f"- Inflation assumption: **{inflation_pct:.1f}%**",
        f"- Equity sleeve: **{prof['equity']:.1f}%**",
        f"- Bonds: **{prof['bonds']:.1f}%**",
        f"- T-Bills / cash-like: **{prof['tbills']:.1f}%**",
        f"- REIT: **{prof['reit']:.1f}%**",
        f"- Growth exposure proxy: **{prof['growth_proxy']:.1f}%**",
        f"- Dividend / value proxy: **{prof['dividend']:.1f}%**",
        f"- Illustrative real return: **{real_ret:.1f}%**",
        f"- Net illustrative shift: **{net:+.1f} pp**",
    ]

    tradeoffs = (
        "**High growth / long-duration bonds** → more valuation and price pressure if inflation stays high.\n"
        "**Short-duration bonds / T-Bills** → may benefit as rates rise, but must still beat inflation for real gains.\n"
        "**Dividend / value sleeves** → pricing power can help, but not immune to rate-driven compression."
    )

    what_if = (
        f"- Inflation **2%** → easier to preserve real purchasing power\n"
        f"- Inflation **{inflation_pct:.0f}%** (current assumption) → purchasing-power pressure rises\n"
        f"- Inflation **8%+** → valuation/rate stress increases for growth and long bonds"
    )

    actions: list[str] = []
    if prof["bonds"] >= 35 and inflation_pct >= 5:
        actions.append("Consider **short-duration bonds** or **T-Bills** if long bond price pressure is uncomfortable.")
    if prof["growth_proxy"] >= 40 and inflation_pct >= 6:
        actions.append("Trim **growth concentration** if higher rates compress valuations.")
    if prof["tbills"] < 10 and inflation_pct >= 5:
        actions.append("A modest **cash / T-Bill** sleeve can add flexibility when rates rise with inflation.")
    if not actions:
        actions.append("Monitor **real return** (nominal minus inflation), not headline account growth alone.")

    sections = build_analyst_sections(
        direct_answer=direct,
        portfolio_analyst_view=analyst,
        key_variables="\n".join(key_lines),
        tradeoffs=tradeoffs,
        what_if_scenarios=what_if if not beginner else "",
        recommended_actions=" ".join(actions[:3]),
        risk_notes=_inflation_risk_notes(beginner),
        beginner=beginner,
    )
    return InvestmentSolverResult(
        short_answer=direct,
        analyst_sections=sections,
        problem_type="macro_inflation",
        model_name="Inflation scenario analyst",
        math_idea="Inflation → real return erosion + sleeve-specific rate/valuation pressure.",
        confidence_pct=81,
        computed={
            "inflation_pct": inflation_pct,
            "real_return_estimate_pct": real_ret,
            "net_return_shift_pp": net,
            **comps,
            **prof,
        },
    )
