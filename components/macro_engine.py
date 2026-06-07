"""Shared macro assumption helpers — unify Health, MC, Optimizer, and Frontier."""

from __future__ import annotations

import streamlit as st

import portfolio_core as core


def macro_assumptions_from_session() -> core.ForwardMacroAssumptions:
    """Build assumptions from Portfolio Health widget session keys (shared app-wide)."""
    return core.ForwardMacroAssumptions(
        rate_environment=st.session_state.get("health_rate_env", "Stable Rates"),
        inflation=st.session_state.get("health_inflation", "Moderate Inflation"),
        recession_probability=float(st.session_state.get("health_recession", 25)) / 100.0,
        valuation=st.session_state.get("health_valuation", "Fair Value"),
        economic_regime=st.session_state.get("health_regime", "Expansion"),
    )


def health_settings_fingerprint() -> str:
    """Fingerprint for objective + macro + bond constraint + lookback — invalidates health cache when changed."""
    start = st.session_state.get("analysis_start_date")
    end = st.session_state.get("analysis_end_date")
    start_s = start.isoformat() if hasattr(start, "isoformat") else str(start or "")
    end_s = end.isoformat() if hasattr(end, "isoformat") else str(end or "")
    return "|".join(
        [
            str(st.session_state.get("health_rate_env", "Stable Rates")),
            str(st.session_state.get("health_recession", 25)),
            str(st.session_state.get("health_inflation", "Moderate Inflation")),
            str(st.session_state.get("health_valuation", "Fair Value")),
            str(st.session_state.get("health_regime", "Expansion")),
            str(st.session_state.get("health_objective", "balanced growth")),
            str(st.session_state.get("health_bond_min", 0)),
            start_s,
            end_s,
        ]
    )


def macro_assumptions_fingerprint(assumptions: core.ForwardMacroAssumptions) -> str:
    return (
        f"{assumptions.rate_environment}|{assumptions.inflation}|"
        f"{assumptions.recession_probability:.2f}|{assumptions.valuation}|"
        f"{assumptions.economic_regime}"
    )


def historical_window_fingerprint(start: str, end: str) -> str:
    return f"{start}|{end}"


def forward_projection_cache_fingerprint(
    start: str,
    end: str,
    assumptions: core.ForwardMacroAssumptions,
    *,
    years: float,
    n_assets: int,
) -> str:
    """Cache key: historical window + macro settings (+ horizon and asset count)."""
    return (
        f"{historical_window_fingerprint(start, end)}|"
        f"{macro_assumptions_fingerprint(assumptions)}|y{years:.4f}|n{n_assets}"
    )


def clear_forward_projection_cache() -> None:
    """Drop cached forward projections (e.g. after date or macro changes)."""
    for key in list(st.session_state.keys()):
        if key == "forward_projection" or key == "forward_projection_fp" or key.startswith("forward_proj_"):
            st.session_state.pop(key, None)


def get_forward_projection(
    *,
    start: str,
    end: str,
    metrics: core.ExtendedPortfolioMetrics,
    mean_returns,
    cov,
    tickers: list[str],
    weights,
    asset_types: list[str],
    initial_value: float,
    risk_free_rate: float,
    years: float = 5.0,
) -> core.ForwardProjectionResult:
    """Compute (or reuse cached) forward macro projection for the current session assumptions."""
    assumptions = macro_assumptions_from_session()
    fp = forward_projection_cache_fingerprint(
        start, end, assumptions, years=years, n_assets=len(tickers)
    )
    cache_key = f"forward_proj_{fp}"
    if st.session_state.get("forward_projection_fp") == fp and cache_key in st.session_state:
        return st.session_state[cache_key]

    forward = core.compute_forward_projection_with_profile(
        metrics=metrics,
        mean_returns=mean_returns,
        cov=cov,
        tickers=tickers,
        weights=weights,
        asset_types=asset_types,
        assumptions=assumptions,
        initial_value=initial_value,
        years=years,
        risk_free_rate=risk_free_rate,
    )
    st.session_state[cache_key] = forward
    st.session_state.forward_projection_fp = fp
    st.session_state.forward_projection = forward
    return forward


def macro_assumption_summary() -> str:
    """One-line summary of current macro settings for UI captions."""
    a = macro_assumptions_from_session()
    return (
        f"{a.inflation} · {a.rate_environment} · "
        f"Recession {a.recession_probability * 100:.0f}% · {a.valuation} · {a.economic_regime}"
    )
