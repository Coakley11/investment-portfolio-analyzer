"""Shared macro assumption helpers — unify Health, MC, Optimizer, and Frontier."""

from __future__ import annotations

from typing import Any, Sequence

import streamlit as st

import portfolio_core as core

# Canonical shared macro profile — NOT used as Streamlit widget keys.
# Widget keys are `_w_<persist_key>`; Streamlit deletes widget keys when the
# Health expander is not rendered (e.g. navigating to Forward Macro).
SHARED_MACRO_PERSIST_KEYS: tuple[str, ...] = (
    "health_rate_env",
    "health_inflation",
    "health_recession",
    "health_valuation",
    "health_regime",
)

SHARED_MACRO_DEFAULTS: dict[str, Any] = {
    "health_rate_env": "Stable Rates",
    "health_inflation": "Moderate Inflation",
    "health_recession": 25,
    "health_valuation": "Fair Value",
    "health_regime": "Expansion",
}

RATE_ENV_OPTIONS: tuple[str, ...] = (
    "Falling Rates",
    "Stable Rates",
    "Rising Rates",
    "High Rate Environment",
)
INFLATION_OPTIONS: tuple[str, ...] = (
    "Low Inflation",
    "Moderate Inflation",
    "High Inflation",
    "Deflation",
)
VALUATION_OPTIONS: tuple[str, ...] = (
    "Cheap",
    "Fair Value",
    "Expensive",
    "Bubble-like",
)
REGIME_OPTIONS: tuple[str, ...] = (
    "Expansion",
    "Slow Growth",
    "Recession",
    "Recovery",
    "Stagflation",
    "AI / Tech Boom",
    "Credit Crisis",
)


def macro_widget_key(persist_key: str) -> str:
    """Transient Streamlit widget key for a shared macro persist key."""
    return f"_w_{persist_key}"


def ensure_shared_macro_session_defaults(session_state: Any | None = None) -> None:
    """Ensure canonical macro keys exist (safe every rerun; never overwrites user values)."""
    ss = st.session_state if session_state is None else session_state
    for key, default in SHARED_MACRO_DEFAULTS.items():
        if key not in ss or ss.get(key) in (None, ""):
            ss[key] = default


def seed_macro_widget_from_persist(persist_key: str, session_state: Any | None = None) -> None:
    """Copy persist → widget key when Streamlit deleted the widget key after navigation."""
    ss = st.session_state if session_state is None else session_state
    ensure_shared_macro_session_defaults(ss)
    wkey = macro_widget_key(persist_key)
    if wkey not in ss:
        ss[wkey] = ss[persist_key]


def commit_macro_widget_to_persist(persist_key: str, session_state: Any | None = None) -> None:
    """Copy widget → persist after render so values survive widget teardown."""
    ss = st.session_state if session_state is None else session_state
    wkey = macro_widget_key(persist_key)
    if wkey in ss:
        ss[persist_key] = ss[wkey]


def simulate_macro_widget_teardown(session_state: dict[str, Any]) -> None:
    """Test helper: mimic Streamlit deleting unrendered widget keys."""
    for key in SHARED_MACRO_PERSIST_KEYS:
        session_state.pop(macro_widget_key(key), None)


def _selectbox_persisted(
    label: str,
    options: Sequence[str],
    persist_key: str,
    *,
    help: str | None = None,
) -> str:
    seed_macro_widget_from_persist(persist_key)
    wkey = macro_widget_key(persist_key)
    current = st.session_state.get(persist_key, SHARED_MACRO_DEFAULTS[persist_key])
    if current not in options:
        current = SHARED_MACRO_DEFAULTS[persist_key]
        st.session_state[persist_key] = current
        st.session_state[wkey] = current
    # Do not pass index= — it fights session_state and re-defaults after navigation.
    value = st.selectbox(label, list(options), key=wkey, help=help)
    commit_macro_widget_to_persist(persist_key)
    return str(value)


def _slider_persisted(
    label: str,
    persist_key: str,
    *,
    min_value: int,
    max_value: int,
    step: int,
) -> int:
    seed_macro_widget_from_persist(persist_key)
    wkey = macro_widget_key(persist_key)
    # value comes from session_state[wkey] after seed — do not pass a competing default.
    value = st.slider(label, min_value, max_value, step=step, key=wkey)
    commit_macro_widget_to_persist(persist_key)
    return int(value)


def render_shared_macro_assumption_controls() -> dict[str, Any]:
    """Portfolio Health expander: shared macro controls with navigation-safe persistence."""
    ensure_shared_macro_session_defaults()
    h1, h2, h3 = st.columns(3)
    with h1:
        rate = _selectbox_persisted(
            "Interest Rate Environment",
            RATE_ENV_OPTIONS,
            "health_rate_env",
        )
        recession = _slider_persisted(
            "Recession Probability (%)",
            "health_recession",
            min_value=0,
            max_value=100,
            step=5,
        )
    with h2:
        inflation = _selectbox_persisted(
            "Inflation Assumption",
            INFLATION_OPTIONS,
            "health_inflation",
        )
        valuation = _selectbox_persisted(
            "Valuation Environment",
            VALUATION_OPTIONS,
            "health_valuation",
        )
    with h3:
        regime = _selectbox_persisted(
            "Economic Regime",
            REGIME_OPTIONS,
            "health_regime",
        )
    return {
        "health_rate_env": rate,
        "health_inflation": inflation,
        "health_recession": recession,
        "health_valuation": valuation,
        "health_regime": regime,
    }


def macro_assumptions_from_session(session_state: Any | None = None) -> core.ForwardMacroAssumptions:
    """Build assumptions from canonical shared macro persist keys (app-wide)."""
    ss = st.session_state if session_state is None else session_state
    ensure_shared_macro_session_defaults(ss)
    return core.ForwardMacroAssumptions(
        rate_environment=str(ss.get("health_rate_env", "Stable Rates")),
        inflation=str(ss.get("health_inflation", "Moderate Inflation")),
        recession_probability=float(ss.get("health_recession", 25)) / 100.0,
        valuation=str(ss.get("health_valuation", "Fair Value")),
        economic_regime=str(ss.get("health_regime", "Expansion")),
    )


def health_settings_fingerprint() -> str:
    """Fingerprint for objective + macro + bond constraint + lookback — invalidates health cache when changed."""
    ensure_shared_macro_session_defaults()
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
