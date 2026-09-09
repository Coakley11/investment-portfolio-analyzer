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


def _session_get(session_state: Any, key: str, default: Any = None) -> Any:
    """Read a session key without using ``.get`` (AppTest SafeSessionState lacks it)."""
    try:
        if key in session_state:
            return session_state[key]
    except Exception:
        pass
    if isinstance(session_state, dict):
        return session_state.get(key, default)
    return default


def ensure_shared_macro_session_defaults(session_state: Any | None = None) -> None:
    """Ensure canonical macro keys exist (safe every rerun; never overwrites user values)."""
    ss = st.session_state if session_state is None else session_state
    for key, default in SHARED_MACRO_DEFAULTS.items():
        if key not in ss or _session_get(ss, key) in (None, ""):
            ss[key] = default


FORWARD_HORIZON_MIN = 1
FORWARD_HORIZON_MAX = 15
FORWARD_HORIZON_FALLBACK = 5
FORWARD_HORIZON_PERSIST_KEY = "fwd_years"
PLAN_HORIZON_SESSION_KEY = "plan_horizon"


def _coerce_horizon_int(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def clamp_forward_horizon_years(
    raw: Any,
    *,
    min_years: int = FORWARD_HORIZON_MIN,
    max_years: int = FORWARD_HORIZON_MAX,
    fallback: int = FORWARD_HORIZON_FALLBACK,
) -> int:
    """Clamp a horizon into the Forward slider range; invalid values use fallback."""
    n = _coerce_horizon_int(raw)
    if n is None:
        return int(fallback)
    return int(min(max_years, max(min_years, n)))


def planning_horizon_years(session_state: Any) -> int | None:
    """Canonical planning 'Investment time horizon' if present."""
    if PLAN_HORIZON_SESSION_KEY not in session_state:
        return None
    return _coerce_horizon_int(_session_get(session_state, PLAN_HORIZON_SESSION_KEY))


def seed_forward_horizon_from_plan_if_needed(session_state: Any | None = None) -> int:
    """
    First initialization only: seed Forward horizon from persisted ``plan_horizon``.

    Does not overwrite an existing Forward-page value (manual override or prior seed).
    """
    ss = st.session_state if session_state is None else session_state
    persist = FORWARD_HORIZON_PERSIST_KEY
    if persist in ss:
        ss[persist] = clamp_forward_horizon_years(_session_get(ss, persist))
        return int(ss[persist])
    plan = planning_horizon_years(ss)
    if plan is None:
        ss[persist] = FORWARD_HORIZON_FALLBACK
    else:
        ss[persist] = clamp_forward_horizon_years(plan)
    return int(ss[persist])


def harvest_forward_horizon_widget_to_persist(session_state: Any | None = None) -> None:
    """Copy live Forward horizon widget → persist before Streamlit tears the widget down."""
    ss = st.session_state if session_state is None else session_state
    wkey = macro_widget_key(FORWARD_HORIZON_PERSIST_KEY)
    if wkey in ss:
        ss[FORWARD_HORIZON_PERSIST_KEY] = clamp_forward_horizon_years(ss[wkey])


def _on_forward_horizon_change() -> None:
    harvest_forward_horizon_widget_to_persist()


def render_forward_projection_horizon_slider() -> int:
    """Forward Macro horizon slider — seeds from planning horizon once, then persists overrides."""
    seed_forward_horizon_from_plan_if_needed()
    persist = FORWARD_HORIZON_PERSIST_KEY
    wkey = macro_widget_key(persist)
    if wkey not in st.session_state:
        st.session_state[wkey] = st.session_state[persist]
    value = st.slider(
        "Forward projection horizon (years)",
        FORWARD_HORIZON_MIN,
        FORWARD_HORIZON_MAX,
        step=1,
        key=wkey,
        on_change=_on_forward_horizon_change,
        help=(
            "Defaults from your planning Investment time horizon. "
            "Changing this slider is a Forward-page override and will not reset on navigation."
        ),
    )
    harvest_forward_horizon_widget_to_persist()
    return int(value)


MC_HORIZON_MIN = 1
MC_HORIZON_MAX = 15
MC_HORIZON_FALLBACK = 5
MC_HORIZON_PERSIST_KEY = "mc_years"


def clamp_mc_horizon_years(
    raw: Any,
    *,
    min_years: int = MC_HORIZON_MIN,
    max_years: int = MC_HORIZON_MAX,
    fallback: int = MC_HORIZON_FALLBACK,
) -> int:
    """Clamp a horizon into the Monte Carlo slider range; invalid values use fallback."""
    return clamp_forward_horizon_years(
        raw, min_years=min_years, max_years=max_years, fallback=fallback
    )


def seed_mc_horizon_from_plan_if_needed(session_state: Any | None = None) -> int:
    """
    First initialization only: seed Monte Carlo horizon from persisted ``plan_horizon``.

    Independent of ``fwd_years``. Does not overwrite an existing MC-page value.
    """
    ss = st.session_state if session_state is None else session_state
    persist = MC_HORIZON_PERSIST_KEY
    if persist in ss:
        ss[persist] = clamp_mc_horizon_years(_session_get(ss, persist))
        return int(ss[persist])
    plan = planning_horizon_years(ss)
    if plan is None:
        ss[persist] = MC_HORIZON_FALLBACK
    else:
        ss[persist] = clamp_mc_horizon_years(plan)
    return int(ss[persist])


def harvest_mc_horizon_widget_to_persist(session_state: Any | None = None) -> None:
    """Copy live Monte Carlo horizon widget → persist before Streamlit tears the widget down."""
    ss = st.session_state if session_state is None else session_state
    wkey = macro_widget_key(MC_HORIZON_PERSIST_KEY)
    if wkey in ss:
        ss[MC_HORIZON_PERSIST_KEY] = clamp_mc_horizon_years(ss[wkey])


def _on_mc_horizon_change() -> None:
    harvest_mc_horizon_widget_to_persist()


def render_monte_carlo_projection_years_slider() -> int:
    """Monte Carlo Projection years — seeds from planning horizon once, then persists overrides."""
    seed_mc_horizon_from_plan_if_needed()
    persist = MC_HORIZON_PERSIST_KEY
    wkey = macro_widget_key(persist)
    if wkey not in st.session_state:
        st.session_state[wkey] = st.session_state[persist]
    value = st.slider(
        "Projection years",
        MC_HORIZON_MIN,
        MC_HORIZON_MAX,
        step=1,
        key=wkey,
        on_change=_on_mc_horizon_change,
        help=(
            "Defaults from your planning Investment time horizon. "
            "Changing this slider is a Monte Carlo override and stays independent of Forward horizon."
        ),
    )
    harvest_mc_horizon_widget_to_persist()
    return int(value)


def harvest_shared_macro_widgets_to_persist(session_state: Any | None = None) -> None:
    """
    Copy any live macro widget values into canonical persist keys.

    Call at the start of every app run (before tab gates / st.rerun).

    Why: after a selectbox change, Streamlit stores the new value on ``_w_*``
    immediately, but ``health_*`` persist keys are only updated when Health
    controls render and commit. If the post-select run skips Health (navigation,
    early rerun, analytics gate), Streamlit then deletes ``_w_*`` at end-of-run
    and the user's choice is lost — typically resetting Valuation to Fair Value.
    """
    ss = st.session_state if session_state is None else session_state
    ensure_shared_macro_session_defaults(ss)
    for persist_key in SHARED_MACRO_PERSIST_KEYS:
        wkey = macro_widget_key(persist_key)
        if wkey in ss:
            ss[persist_key] = ss[wkey]


def _on_macro_widget_change(persist_key: str) -> None:
    """Streamlit on_change: commit widget → persist on the selection event itself."""
    commit_macro_widget_to_persist(persist_key)


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
    session_state.pop(macro_widget_key(FORWARD_HORIZON_PERSIST_KEY), None)
    session_state.pop(macro_widget_key(MC_HORIZON_PERSIST_KEY), None)


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
    # on_change commits on the selection event — before any later navigation/teardown.
    # Do not pass index= — it fights session_state and re-defaults after navigation.
    value = st.selectbox(
        label,
        list(options),
        key=wkey,
        help=help,
        on_change=_on_macro_widget_change,
        args=(persist_key,),
    )
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
    value = st.slider(
        label,
        min_value,
        max_value,
        step=step,
        key=wkey,
        on_change=_on_macro_widget_change,
        args=(persist_key,),
    )
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
        rate_environment=str(_session_get(ss, "health_rate_env", "Stable Rates")),
        inflation=str(_session_get(ss, "health_inflation", "Moderate Inflation")),
        recession_probability=float(_session_get(ss, "health_recession", 25)) / 100.0,
        valuation=str(_session_get(ss, "health_valuation", "Fair Value")),
        economic_regime=str(_session_get(ss, "health_regime", "Expansion")),
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
    """Legacy cache key: historical window + macro settings (+ horizon and asset count)."""
    return (
        f"{historical_window_fingerprint(start, end)}|"
        f"{macro_assumptions_fingerprint(assumptions)}|y{years:.4f}|n{n_assets}"
    )


FORWARD_ENGINE_INPUTS_KEY = "_forward_engine_inputs"
FORWARD_PROJECTION_KEY = "forward_projection"
FORWARD_PROJECTION_FP_KEY = "forward_projection_fp"


def build_canonical_forward_fingerprint(
    assumptions: core.ForwardMacroAssumptions,
    *,
    start: str,
    end: str,
    years: float,
    tickers: Sequence[str],
    weights: Any,
    risk_free_rate: float,
    initial_value: float,
) -> str:
    """
    Validity fingerprint for cached Forward projections.

    Includes holdings, weights, lookback window, shared macro assumptions,
    projection years, risk-free rate, and initial value — everything the
    canonical Forward engine consumes for portfolio-level return/vol/Sharpe.
    """
    import numpy as np

    t = tuple(str(x).strip().upper() for x in tickers)
    w = tuple(round(float(x), 8) for x in np.asarray(weights, dtype=float).ravel())
    return "|".join(
        [
            historical_window_fingerprint(str(start), str(end)),
            macro_assumptions_fingerprint(assumptions),
            f"y{float(years):.4f}",
            f"rf{float(risk_free_rate):.8f}",
            f"iv{round(float(initial_value), 2):.2f}",
            f"t{','.join(t)}",
            f"w{','.join(f'{x:.8f}' for x in w)}",
        ]
    )


def store_forward_engine_inputs(
    session_state: Any | None = None,
    *,
    metrics: Any,
    mean_returns: Any,
    cov: Any,
    tickers: Sequence[str],
    weights: Any,
    asset_types: Sequence[str],
    start: str,
    end: str,
    initial_value: float,
    risk_free_rate: float,
) -> None:
    """Persist analytics inputs so AMI/MC/Optimizer can resolve Forward without re-fetching."""
    import numpy as np

    ss = st.session_state if session_state is None else session_state
    ss[FORWARD_ENGINE_INPUTS_KEY] = {
        "metrics": metrics,
        "mean_returns": np.asarray(mean_returns, dtype=float).copy(),
        "cov": np.asarray(cov, dtype=float).copy(),
        "tickers": [str(t).strip().upper() for t in tickers],
        "weights": np.asarray(weights, dtype=float).copy(),
        "asset_types": [str(a) for a in asset_types],
        "start": str(start),
        "end": str(end),
        "initial_value": float(initial_value),
        "risk_free_rate": float(risk_free_rate),
    }


def _forward_years_from_session(session_state: Any) -> float:
    seed_forward_horizon_from_plan_if_needed(session_state)
    return float(
        clamp_forward_horizon_years(
            _session_get(session_state, FORWARD_HORIZON_PERSIST_KEY, FORWARD_HORIZON_FALLBACK)
        )
    )


def peek_valid_forward_projection(session_state: Any | None = None) -> core.ForwardProjectionResult | None:
    """Return cached ForwardProjectionResult only when fingerprint matches current inputs."""
    ss = st.session_state if session_state is None else session_state
    inputs = _session_get(ss, FORWARD_ENGINE_INPUTS_KEY)
    cached = _session_get(ss, FORWARD_PROJECTION_KEY)
    fp_cached = _session_get(ss, FORWARD_PROJECTION_FP_KEY)
    if not isinstance(inputs, dict) or cached is None or not fp_cached:
        return None
    assumptions = macro_assumptions_from_session(ss)
    years = _forward_years_from_session(ss)
    fp = build_canonical_forward_fingerprint(
        assumptions,
        start=str(inputs.get("start") or ""),
        end=str(inputs.get("end") or ""),
        years=years,
        tickers=list(inputs.get("tickers") or []),
        weights=inputs.get("weights"),
        risk_free_rate=float(inputs.get("risk_free_rate") or 0.0),
        initial_value=float(inputs.get("initial_value") or 0.0),
    )
    if str(fp_cached) != fp:
        return None
    return cached  # type: ignore[return-value]


def resolve_canonical_forward_projection(
    session_state: Any | None = None,
    *,
    years: float | None = None,
    assumptions: core.ForwardMacroAssumptions | None = None,
) -> core.ForwardProjectionResult | None:
    """
    Shared Forward path for UI / MC / Optimizer / AMI.

    Reuses a fingerprint-valid cache; otherwise computes via
    ``portfolio_core.compute_forward_projection_with_profile`` using stored engine inputs.
    Returns None when analytics inputs are not yet available.
    """
    import numpy as np

    ss = st.session_state if session_state is None else session_state
    inputs = _session_get(ss, FORWARD_ENGINE_INPUTS_KEY)
    if not isinstance(inputs, dict):
        return peek_valid_forward_projection(ss)

    assumptions = assumptions or macro_assumptions_from_session(ss)
    years_f = float(years) if years is not None else _forward_years_from_session(ss)
    tickers = list(inputs.get("tickers") or [])
    weights = np.asarray(inputs.get("weights"), dtype=float)
    fp = build_canonical_forward_fingerprint(
        assumptions,
        start=str(inputs.get("start") or ""),
        end=str(inputs.get("end") or ""),
        years=years_f,
        tickers=tickers,
        weights=weights,
        risk_free_rate=float(inputs.get("risk_free_rate") or 0.0),
        initial_value=float(inputs.get("initial_value") or 0.0),
    )

    cached = _session_get(ss, FORWARD_PROJECTION_KEY)
    if cached is not None and str(_session_get(ss, FORWARD_PROJECTION_FP_KEY) or "") == fp:
        return cached  # type: ignore[return-value]

    metrics = inputs.get("metrics")
    mean_returns = np.asarray(inputs.get("mean_returns"), dtype=float)
    cov = np.asarray(inputs.get("cov"), dtype=float)
    asset_types = list(inputs.get("asset_types") or [])
    if metrics is None or mean_returns.size == 0 or cov.size == 0 or not tickers:
        return None

    forward = core.compute_forward_projection_with_profile(
        metrics=metrics,
        mean_returns=mean_returns.copy(),
        cov=cov.copy(),
        tickers=tickers,
        weights=weights,
        asset_types=asset_types,
        assumptions=assumptions,
        initial_value=float(inputs.get("initial_value") or 0.0),
        years=years_f,
        risk_free_rate=float(inputs.get("risk_free_rate") or 0.0),
    )
    ss[FORWARD_PROJECTION_KEY] = forward
    ss[FORWARD_PROJECTION_FP_KEY] = fp
    ss[f"forward_proj_{fp}"] = forward
    return forward


def clear_forward_projection_cache() -> None:
    """Drop cached forward projections (e.g. after date or macro changes)."""
    for key in list(st.session_state.keys()):
        if (
            key in (FORWARD_PROJECTION_KEY, FORWARD_PROJECTION_FP_KEY, FORWARD_ENGINE_INPUTS_KEY)
            or key.startswith("forward_proj_")
        ):
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
    session_state: Any | None = None,
) -> core.ForwardProjectionResult:
    """Compute (or reuse cached) forward macro projection for the current session assumptions."""
    ss = st.session_state if session_state is None else session_state
    store_forward_engine_inputs(
        ss,
        metrics=metrics,
        mean_returns=mean_returns,
        cov=cov,
        tickers=tickers,
        weights=weights,
        asset_types=asset_types,
        start=start,
        end=end,
        initial_value=initial_value,
        risk_free_rate=risk_free_rate,
    )
    assumptions = macro_assumptions_from_session(ss)
    resolved = resolve_canonical_forward_projection(ss, years=float(years), assumptions=assumptions)
    if resolved is not None:
        return resolved
    # Fallback (should be rare): compute directly without relying on stored inputs.
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
    fp = build_canonical_forward_fingerprint(
        assumptions,
        start=start,
        end=end,
        years=float(years),
        tickers=tickers,
        weights=weights,
        risk_free_rate=risk_free_rate,
        initial_value=initial_value,
    )
    ss[FORWARD_PROJECTION_KEY] = forward
    ss[FORWARD_PROJECTION_FP_KEY] = fp
    return forward


def macro_assumption_summary(session_state: Any | None = None) -> str:
    """One-line summary of current macro settings for UI captions."""
    a = macro_assumptions_from_session(session_state)
    return (
        f"{a.inflation} · {a.rate_environment} · "
        f"Recession {a.recession_probability * 100:.0f}% · {a.valuation} · {a.economic_regime}"
    )
