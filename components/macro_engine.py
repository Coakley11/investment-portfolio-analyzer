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
    """Fingerprint for objective + macro + bond constraint — invalidates health cache when changed."""
    return "|".join(
        [
            str(st.session_state.get("health_rate_env", "Stable Rates")),
            str(st.session_state.get("health_recession", 25)),
            str(st.session_state.get("health_inflation", "Moderate Inflation")),
            str(st.session_state.get("health_valuation", "Fair Value")),
            str(st.session_state.get("health_regime", "Expansion")),
            str(st.session_state.get("health_objective", "balanced growth")),
            str(st.session_state.get("health_bond_min", 0)),
        ]
    )


def macro_assumptions_fingerprint(assumptions: core.ForwardMacroAssumptions) -> str:
    return (
        f"{assumptions.rate_environment}|{assumptions.inflation}|"
        f"{assumptions.recession_probability:.2f}|{assumptions.valuation}|"
        f"{assumptions.economic_regime}"
    )


def get_forward_projection(
    *,
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
    fp = macro_assumptions_fingerprint(assumptions)
    cache_key = f"forward_proj_{fp}_{len(tickers)}"
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
