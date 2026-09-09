"""
Investment Portfolio Analyzer — professional finance dashboard UI.
Core calculations: portfolio_core.py | Charts: dashboard_charts.py
"""

from __future__ import annotations

import datetime as dt
import importlib
import io
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

import dashboard_charts as charts
import portfolio_core as core
import portfolio_polish as pp
import portfolio_demo as pdemo
from components.decision_coach import (
    render_action_plan,
    render_action_plan_placeholder,
    render_recommendations_panel,
)
from components.beginner_navigation import (
    ADVANCED_TAB_LABELS,
    BEGINNER_TAB_LABELS,
    OBJECTIVE_TO_PRESET,
    _holdings_fingerprint,
    active_main_tab,
    is_etf_holdings_tab,
    is_real_portfolio_tab,
    mark_portfolio_built,
    render_beginner_sidebar_checklist,
    render_recommended_next_step_card,
)
_calc_transparency = importlib.import_module("components.calculation_transparency")
render_how_calculated_section = getattr(
    _calc_transparency, "render_how_calculated_section", lambda *_a, **_k: None
)
render_future_model_improvements = getattr(
    _calc_transparency,
    "render_future_model_improvements",
    getattr(_calc_transparency, "render_methodology_footer", lambda **_kw: None),
)
render_macro_why_it_matters = getattr(
    _calc_transparency, "render_macro_why_it_matters", lambda: None
)
render_objective_alignment_summary = getattr(
    _calc_transparency, "render_objective_alignment_summary", lambda *_a, **_k: None
)
render_optimizer_confidence = getattr(
    _calc_transparency, "render_optimizer_confidence", lambda: None
)
try:
    from components.calculation_transparency import (
        is_forward_optimizer_basis,
        optimizer_results_methodology_lead,
        STRESS_ADJUSTED_MAX_DRAWDOWN_HELP,
        STRESS_ADJUSTED_MAX_DRAWDOWN_LABEL,
        FORWARD_OPTIMIZER_SNAPSHOT_SCOPE,
        FORWARD_OPTIMIZER_SNAPSHOT_SUBTITLE,
    )
except ImportError:  # pragma: no cover — Cloud partial-reload fallback
    def is_forward_optimizer_basis(basis: str) -> bool:
        return str(basis or "").strip().lower().startswith("forward")

    def optimizer_results_methodology_lead(basis: str) -> str:
        return _calc_transparency.optimizer_results_methodology_lead(basis)

    STRESS_ADJUSTED_MAX_DRAWDOWN_LABEL = getattr(
        _calc_transparency, "STRESS_ADJUSTED_MAX_DRAWDOWN_LABEL", "Stress-Adjusted Max Drawdown"
    )
    STRESS_ADJUSTED_MAX_DRAWDOWN_HELP = getattr(
        _calc_transparency,
        "STRESS_ADJUSTED_MAX_DRAWDOWN_HELP",
        "Historical peak-to-trough drawdown scaled by recession probability — not a "
        "forward-simulated drawdown.",
    )
    FORWARD_OPTIMIZER_SNAPSHOT_SUBTITLE = getattr(
        _calc_transparency,
        "FORWARD_OPTIMIZER_SNAPSHOT_SUBTITLE",
        "Mean-variance outputs using forward-adjusted covariance and sleeve return shifts.",
    )
    FORWARD_OPTIMIZER_SNAPSHOT_SCOPE = getattr(
        _calc_transparency,
        "FORWARD_OPTIMIZER_SNAPSHOT_SCOPE",
        "Optimizer uses forward-adjusted covariance plus sleeve return shifts from rates, "
        "inflation, and applicable economic-regime assumptions. Valuation Environment "
        "adjusts portfolio-level forward return/volatility but does not currently alter "
        "the optimizer's per-asset expected-return vector.",
    )
_beginner_coach = importlib.import_module("components.beginner_coach")
render_goal_cards = _beginner_coach.render_goal_cards
render_beginner_goal_tab = _beginner_coach.render_beginner_goal_tab
render_portfolio_visual_table = getattr(_beginner_coach, "render_portfolio_visual_table", lambda *_a, **_k: None)
render_beginner_analyze_results = _beginner_coach.render_beginner_analyze_results
render_beginner_rebalance_cards = getattr(_beginner_coach, "render_beginner_rebalance_cards", lambda *_a, **_k: None)
render_beginner_analysis_pipeline = getattr(
    _beginner_coach, "render_beginner_analysis_pipeline", lambda: None
)
from components.beginner_copy import translate_for_beginner
from components.getting_started_guide import PRESET_RATIONALE, render_getting_started_guide
from components.guided_adjustment import render_guided_portfolio_adjustment
from components.implementation_guide import render_implementation_guide
from components.investment_planning import render_how_much_to_invest
from components.beginner_macro import render_beginner_macro_panel
from components.macro_assumptions_guide import render_macro_assumptions_guide
from components.macro_data import ensure_beginner_macro_defaults
from components.macro_engine_loader import load_macro_engine

_macro_engine = load_macro_engine()
get_forward_projection = _macro_engine.get_forward_projection
store_forward_engine_inputs = getattr(_macro_engine, "store_forward_engine_inputs", None)
build_canonical_forward_fingerprint = getattr(_macro_engine, "build_canonical_forward_fingerprint", None)
resolve_canonical_forward_projection = getattr(_macro_engine, "resolve_canonical_forward_projection", None)
peek_valid_forward_projection = getattr(_macro_engine, "peek_valid_forward_projection", None)
health_settings_fingerprint = _macro_engine.health_settings_fingerprint
macro_assumption_summary = _macro_engine.macro_assumption_summary
macro_assumptions_from_session = _macro_engine.macro_assumptions_from_session
ensure_shared_macro_session_defaults = _macro_engine.ensure_shared_macro_session_defaults
harvest_shared_macro_widgets_to_persist = _macro_engine.harvest_shared_macro_widgets_to_persist
harvest_forward_horizon_widget_to_persist = _macro_engine.harvest_forward_horizon_widget_to_persist
harvest_mc_horizon_widget_to_persist = _macro_engine.harvest_mc_horizon_widget_to_persist
render_shared_macro_assumption_controls = _macro_engine.render_shared_macro_assumption_controls
render_forward_projection_horizon_slider = _macro_engine.render_forward_projection_horizon_slider
render_monte_carlo_projection_years_slider = _macro_engine.render_monte_carlo_projection_years_slider
from components.monthly_review import render_monthly_review_workflow
from components.rebalancing_panel import render_rebalancing_panel
from components.ui_helpers import (
    APP_DISCLAIMER as UI_DISCLAIMER,
    RUN_PORTFOLIO_ANALYSIS_LABEL,
    HISTORICAL_LOOKBACK_DATE_HELP,
    HISTORICAL_PERIOD_DATE_INPUT_HELP,
    HISTORICAL_PERIOD_HELP_ADVANCED,
    HISTORICAL_PERIOD_HELP_BEGINNER,
    apply_pending_sidebar_portfolio_value,
    coach_card,
    is_beginner_mode,
    metric_help,
    refresh_market_data_sidebar,
    render_beginner_lookback_vs_horizon_education,
    render_historical_metrics_banner,
    render_historical_period_sidebar_help,
    render_historical_window_summary,
    render_macro_assumptions_banner,
    what_why_do,
)

APP_DISCLAIMER = UI_DISCLAIMER

# ── Page config & styling ─────────────────────────────────────────────────────

st.set_page_config(
    page_title="Daniel Cohen Investment Portfolio Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

try:
    from suite_query_param_preservation import (
        capture_incoming_query_params,
        restore_preserved_query_params,
    )

    capture_incoming_query_params(st)
    restore_preserved_query_params(st)
except Exception:
    pass

try:
    from investment_persistence_trace import init_developer_mode_from_query

    init_developer_mode_from_query(st)
except Exception:
    pass

try:
    from suite_cloud_state import purge_stale_investment_ami_restore_blockers

    purge_stale_investment_ami_restore_blockers(st, "investment")
    try:
        from investment_persistence_trace import record_emergency_restore_trace

        record_emergency_restore_trace(st)
    except Exception:
        pass
except Exception:
    pass

try:
    from suite_workspace import bootstrap_suite_workspace

    bootstrap_suite_workspace(st)
except Exception:
    pass

try:
    from suite_app_shell import apply_suite_auth_gate

    apply_suite_auth_gate(st)
except Exception:
    pass
try:
    from suite_ami_startup_hydrate import (
        hydrate_applied_intelligence_from_url,
        probe_suite_resume_launch_compat,
    )

    if not st.session_state.get("_suite_resume_launch_probe_done"):
        st.session_state["_suite_resume_launch_probe"] = probe_suite_resume_launch_compat()
        st.session_state["_suite_resume_launch_probe_done"] = True
    hydrate_applied_intelligence_from_url(st, "investment")
except Exception as _ami_startup_hydrate_exc:
    st.session_state["_ami_startup_hydrate_error"] = repr(_ami_startup_hydrate_exc)

try:
    from suite_resume_launch import apply_suite_resume_launch

    apply_suite_resume_launch(st, "investment")
except Exception:
    pass

_PERSISTENCE_OK = False

# Safe defaults when investment_persistent_state fails to import (must never crash sidebar).
EXPERIENCE_KEY = "experience"
EXPERIENCE_OPTIONS = ("Beginner Mode", "Advanced Mode")
PERSISTED_EXPERIENCE_KEY = "_suite_persisted_experience"
INVESTMENT_ACTIVE_TAB_KEY = "investment_active_tab"


def _fallback_validate_state_option(
    st_obj: Any,
    key: str,
    options: list[str] | tuple[str, ...],
    default: str | None = None,
) -> None:
    opts = list(options)
    if not opts:
        return
    fallback = default if default is not None and default in opts else opts[0]
    if key not in st_obj.session_state:
        st_obj.session_state[key] = fallback
    elif st_obj.session_state[key] not in opts:
        st_obj.session_state[key] = fallback


def _fallback_ensure_analysis_date_defaults(st_obj: Any) -> None:
    end_default = dt.date.today()
    start_default = end_default - dt.timedelta(days=365 * 5)
    if "analysis_start_date" not in st_obj.session_state:
        st_obj.session_state["analysis_start_date"] = start_default
    if "analysis_end_date" not in st_obj.session_state:
        st_obj.session_state["analysis_end_date"] = end_default


def _fallback_ensure_experience_mode(st_obj: Any) -> None:
    ss = st_obj.session_state
    if ss.get(EXPERIENCE_KEY) in EXPERIENCE_OPTIONS:
        return
    persisted = ss.get(PERSISTED_EXPERIENCE_KEY)
    if persisted in EXPERIENCE_OPTIONS:
        ss[EXPERIENCE_KEY] = persisted
    else:
        ss[EXPERIENCE_KEY] = EXPERIENCE_OPTIONS[0]
        ss[PERSISTED_EXPERIENCE_KEY] = EXPERIENCE_OPTIONS[0]


def _fallback_sync_experience_after_widget(st_obj: Any) -> None:
    ss = st_obj.session_state
    mode = ss.get(EXPERIENCE_KEY)
    if mode in EXPERIENCE_OPTIONS:
        ss[PERSISTED_EXPERIENCE_KEY] = mode


def _fallback_ensure_investment_active_tab(
    st_obj: Any,
    tab_labels: list[str],
    *,
    beginner_mode: bool = False,
) -> None:
    del beginner_mode
    if tab_labels:
        _fallback_validate_state_option(
            st_obj, INVESTMENT_ACTIVE_TAB_KEY, tab_labels, tab_labels[0]
        )


def _fallback_noop_persistence(_st: Any, **_kwargs: Any) -> None:
    pass


validate_state_option = _fallback_validate_state_option
ensure_analysis_date_defaults = _fallback_ensure_analysis_date_defaults
ensure_experience_mode = _fallback_ensure_experience_mode
sync_experience_after_widget = _fallback_sync_experience_after_widget
ensure_investment_active_tab = _fallback_ensure_investment_active_tab
autosave_investment_state = _fallback_noop_persistence
default_reset_investment_session = _fallback_noop_persistence
finalize_persistence_debug = _fallback_noop_persistence
finalize_init_holdings_defaults = _fallback_noop_persistence
finalize_startup_holdings_restore = _fallback_noop_persistence
reconcile_investment_cloud_drift_if_needed = _fallback_noop_persistence
restore_investment_disk_state_once = _fallback_noop_persistence
render_persistence_debug_sidebar = _fallback_noop_persistence

try:
    from investment_persistent_state import (
        EXPERIENCE_KEY,
        EXPERIENCE_OPTIONS,
        INVESTMENT_ACTIVE_TAB_KEY,
        autosave_investment_state,
        default_reset_investment_session,
        ensure_analysis_date_defaults,
        ensure_experience_mode,
        ensure_investment_active_tab,
        finalize_persistence_debug,
        finalize_init_holdings_defaults,
        finalize_startup_holdings_restore,
        reconcile_investment_cloud_drift_if_needed,
        render_persistence_debug_sidebar,
        restore_investment_disk_state_once,
        sync_experience_after_widget,
        validate_state_option,
    )
    from suite_user_persistence import render_reset_controls, show_persistence_messages

    _PERSISTENCE_OK = True
except Exception as _persist_import_exc:
    _PERSISTENCE_OK = False
    st.session_state["_suite_persist_import_error"] = str(_persist_import_exc)

    def render_reset_controls(*_args: Any, **_kwargs: Any) -> None:
        return None

    def show_persistence_messages(*_args: Any, **_kwargs: Any) -> None:
        return None

if _PERSISTENCE_OK:
    try:
        if not st.session_state.get("_suite_inv_persistence_bootstrapped"):
            restore_investment_disk_state_once(st)
            reconcile_investment_cloud_drift_if_needed(st)
            try:
                from applied_math_return_insight import (
                    hydrate_investment_ami_return_state,
                    insight_return_query_id,
                )
                from suite_resume_launch import finalize_ami_return_restore

                if insight_return_query_id(st):
                    hydrate_investment_ami_return_state(st, "investment")
                    finalize_ami_return_restore(st, "investment")
            except Exception:
                pass
            st.session_state["_suite_inv_persistence_bootstrapped"] = True
            if st.session_state.pop("_ami_defer_insight_autosave", False):
                try:
                    from investment_persistent_state import notify_pending_insight_change

                    notify_pending_insight_change(st, source="insight_hydrate_deferred")
                except Exception:
                    pass
    except Exception as _persist_restore_exc:
        st.session_state["_suite_persist_restore_error"] = str(_persist_restore_exc)
        st.session_state["_suite_inv_persistence_bootstrapped"] = True
        try:
            from investment_persistent_state import ensure_investment_safe_startup_after_restore_error

            ensure_investment_safe_startup_after_restore_error(st)
        except Exception as _safe_startup_exc:
            st.session_state["_suite_inv_safe_startup_error"] = str(_safe_startup_exc)
    try:
        from planning_portfolio_value import reset_sidebar_portfolio_widget_gate_for_run

        reset_sidebar_portfolio_widget_gate_for_run(st.session_state)
    except Exception:
        pass
    apply_pending_sidebar_portfolio_value()
    show_persistence_messages(st)

# Single Account & Workspace entry (Command Center + Saved Sessions + Log out).
# Replaces the former top-level Saved session expander + suite account shell chrome.
try:
    from investment_account_workspace import render_investment_account_workspace_control

    render_investment_account_workspace_control(
        st,
        on_reset=default_reset_investment_session,
        reset_label="Reset to default",
        reset_help=(
            "Clears saved portfolio, workflow progress, local disk, and cloud session for this app."
        ),
    )
except Exception as _acct_ws_exc:
    st.session_state["_suite_inv_account_workspace_error"] = str(_acct_ws_exc)
    if _PERSISTENCE_OK:
        try:
            render_reset_controls(
                st,
                "investment",
                on_reset=default_reset_investment_session,
                label="Reset to default",
                help_text=(
                    "Clears saved portfolio, workflow progress, local disk, and cloud session for this app."
                ),
            )
        except Exception:
            pass

st.markdown(
    """
    <style>
    :root {
        --dc-bg: #0b1220;
        --dc-surface: #141c2b;
        --dc-surface-2: #1a2436;
        --dc-border: #2d3f57;
        --dc-text: #e8eef7;
        --dc-muted: #94a3b8;
        --dc-accent: #4da3ff;
        --dc-gold: #f5a623;
    }
    .block-container {
        padding-top: 1.25rem;
        padding-bottom: 2.75rem;
        max-width: 1320px;
    }
    .hero-header {
        background: linear-gradient(135deg, #0c1524 0%, #152238 45%, #1a2d4a 100%);
        border: 1px solid var(--dc-border);
        border-radius: 16px;
        padding: 1.35rem 1.55rem 1.2rem;
        margin: 0 0 1.35rem 0;
        box-shadow: 0 10px 28px rgba(0, 0, 0, 0.28);
        position: relative;
        overflow: hidden;
    }
    .hero-header::before {
        content: "";
        position: absolute;
        top: -40%;
        right: -8%;
        width: 280px;
        height: 280px;
        background: radial-gradient(circle, rgba(77, 163, 255, 0.18) 0%, rgba(77, 163, 255, 0) 70%);
        pointer-events: none;
    }
    .hero-inner { position: relative; z-index: 1; }
    .hero-eyebrow {
        font-size: 0.72rem;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: var(--dc-accent);
        font-weight: 600;
        margin: 0 0 0.45rem 0;
    }
    .hero-title {
        font-size: clamp(1.45rem, 2.6vw, 2.05rem);
        font-weight: 700;
        color: var(--dc-text);
        margin: 0;
        letter-spacing: -0.03em;
        line-height: 1.15;
    }
    .hero-subtitle {
        color: var(--dc-muted);
        font-size: 0.95rem;
        margin: 0.55rem 0 0.85rem 0;
        line-height: 1.5;
        max-width: 920px;
    }
    .hero-badges {
        display: flex;
        flex-wrap: wrap;
        gap: 0.45rem;
    }
    .hero-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.3rem;
        background: rgba(20, 28, 43, 0.85);
        border: 1px solid #334155;
        color: #cbd5e1;
        font-size: 0.74rem;
        padding: 0.28rem 0.62rem;
        border-radius: 999px;
        white-space: nowrap;
    }
    .health-header-badge {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 0.55rem 0.85rem;
        padding: 0.55rem 0.9rem;
        margin: -0.45rem 0 1.1rem 0;
        border-radius: 10px;
        border: 1px solid #334155;
        background: rgba(20, 28, 43, 0.72);
        font-size: 0.82rem;
        color: #cbd5e1;
    }
    .health-header-badge-green {
        border-color: rgba(46, 204, 113, 0.45);
        background: linear-gradient(90deg, rgba(46, 204, 113, 0.10) 0%, rgba(20, 28, 43, 0.85) 100%);
    }
    .health-header-badge-yellow {
        border-color: rgba(245, 166, 35, 0.45);
        background: linear-gradient(90deg, rgba(245, 166, 35, 0.10) 0%, rgba(20, 28, 43, 0.85) 100%);
    }
    .health-header-badge-orange {
        border-color: rgba(230, 126, 34, 0.45);
        background: linear-gradient(90deg, rgba(230, 126, 34, 0.10) 0%, rgba(20, 28, 43, 0.85) 100%);
    }
    .health-header-badge-red {
        border-color: rgba(231, 76, 60, 0.45);
        background: linear-gradient(90deg, rgba(231, 76, 60, 0.10) 0%, rgba(20, 28, 43, 0.85) 100%);
    }
    .health-header-badge-neutral {
        border-color: #334155;
        background: rgba(20, 28, 43, 0.72);
    }
    .health-header-score {
        font-size: 1.05rem;
        font-weight: 700;
        color: #f1f5f9;
        letter-spacing: -0.02em;
    }
    .health-header-label {
        font-weight: 600;
        color: #e2e8f0;
    }
    .health-header-note {
        font-size: 0.72rem;
        color: #94a3b8;
        margin-left: auto;
    }
    .health-header-prompt {
        color: #94a3b8;
        font-style: italic;
    }
    .section-title {
        font-size: 1.05rem;
        font-weight: 600;
        color: #f1f5f9;
        margin: 0 0 0.35rem 0;
        letter-spacing: -0.01em;
    }
    .section-lead {
        color: var(--dc-muted);
        font-size: 0.88rem;
        margin: 0 0 0.7rem 0;
        line-height: 1.45;
    }
    .section-divider {
        border-top: 1px solid var(--dc-border);
        margin: 0 0 1.15rem 0;
    }
    .section-spacer { margin-top: 0.35rem; }
    [data-testid="stMetric"] {
        background: linear-gradient(160deg, #1e2a3a 0%, #141c28 100%);
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 0.75rem 0.9rem;
        box-shadow: 0 2px 6px rgba(0,0,0,0.18);
    }
    [data-testid="stMetric"] label {
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #94a3b8 !important;
    }
    [data-testid="stMetric"] [data-testid="stMetricValue"] {
        font-size: 1.35rem;
        font-weight: 600;
        color: #f1f5f9;
    }
    .insight-card {
        background: linear-gradient(90deg, #1a2332 0%, #172030 100%);
        border-left: 3px solid var(--dc-accent);
        padding: 0.65rem 0.9rem;
        margin-bottom: 0.5rem;
        border-radius: 0 8px 8px 0;
        font-size: 0.9rem;
        color: #cbd5e1;
    }
    .health-card {
        border-radius: 12px;
        padding: 1rem 1.15rem;
        margin-bottom: 0.75rem;
        border: 1px solid #334155;
    }
    .health-card-green {
        background: linear-gradient(135deg, rgba(46, 204, 113, 0.12) 0%, rgba(20, 28, 43, 0.95) 100%);
        border-left: 4px solid #2ecc71;
    }
    .health-card-yellow {
        background: linear-gradient(135deg, rgba(245, 166, 35, 0.12) 0%, rgba(20, 28, 43, 0.95) 100%);
        border-left: 4px solid #f5a623;
    }
    .health-card-orange {
        background: linear-gradient(135deg, rgba(230, 126, 34, 0.12) 0%, rgba(20, 28, 43, 0.95) 100%);
        border-left: 4px solid #e67e22;
    }
    .health-card-red {
        background: linear-gradient(135deg, rgba(231, 76, 60, 0.12) 0%, rgba(20, 28, 43, 0.95) 100%);
        border-left: 4px solid #e74c3c;
    }
    .health-working {
        background: linear-gradient(90deg, rgba(46, 204, 113, 0.08) 0%, #141c2b 100%);
        border-left: 3px solid #2ecc71;
        padding: 0.55rem 0.85rem;
        margin-bottom: 0.45rem;
        border-radius: 0 8px 8px 0;
        font-size: 0.88rem;
        color: #cbd5e1;
    }
    .health-not {
        background: linear-gradient(90deg, rgba(231, 76, 60, 0.08) 0%, #141c2b 100%);
        border-left: 3px solid #e74c3c;
        padding: 0.55rem 0.85rem;
        margin-bottom: 0.45rem;
        border-radius: 0 8px 8px 0;
        font-size: 0.88rem;
        color: #cbd5e1;
    }
    div[data-baseweb="tab-list"] {
        gap: 0.5rem;
        border-bottom: 2px solid var(--dc-border);
        margin-bottom: 0.5rem;
        flex-wrap: wrap;
        padding-bottom: 0.15rem;
    }
    button[data-baseweb="tab"] {
        background-color: rgba(20, 28, 43, 0.6);
        border-radius: 10px 10px 0 0;
        color: #94a3b8;
        font-weight: 500;
        font-size: 0.88rem;
        padding: 0.55rem 0.85rem;
        border: 1px solid transparent;
        min-height: 2.5rem;
    }
    button[data-baseweb="tab"]:hover {
        color: #e2e8f0;
        background-color: rgba(26, 40, 64, 0.85);
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        background: linear-gradient(180deg, #1e3a5f 0%, #152238 100%);
        color: #f8fafc;
        border: 1px solid var(--dc-accent);
        border-bottom-color: transparent;
        font-weight: 600;
        box-shadow: 0 -2px 12px rgba(77, 163, 255, 0.15);
    }
    [data-testid="stDataFrame"], [data-testid="stTable"] {
        border: 1px solid #2a3a52;
        border-radius: 10px;
        overflow: hidden;
    }
    @media (max-width: 768px) {
        .block-container { padding-left: 1rem; padding-right: 1rem; }
        .hero-header { padding: 1rem 1rem 0.95rem; }
        [data-testid="stMetric"] [data-testid="stMetricValue"] { font-size: 1.1rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

pp.inject_polish_css(st, app_slug="investment")

HELP_BEGINNER = {
    "sharpe": "Whether your return is worth the risk you're taking. Higher is generally better.",
    "sortino": "Risk/reward score that cares more about bad drops than normal ups and downs.",
    "volatility": "How much your portfolio tends to move up and down.",
    "correlation": "Whether investments move together. Spreading out helps smooth the ride.",
    "monte_carlo": "Many random 'what if' future paths — a range of possibilities, not a prediction.",
    "efficient_frontier": "Chart of best risk vs. return mixes the model can find.",
    "drawdown": "The biggest drop from a previous high — your worst historical dip.",
    "beta": "How much you move compared to the broad market. About 1.0 = similar to the market.",
}

HELP_ADVANCED = {
    "sharpe": "Return per unit of total risk. Above ~1.0 is strong.",
    "sortino": "Like Sharpe, but penalizes only downside volatility.",
    "volatility": "Annualized standard deviation of daily returns.",
    "correlation": "How assets move together (-1 to +1). Lower can mean better diversification.",
    "monte_carlo": (
        "Parametric simulation of portfolio paths from return/vol assumptions "
        "(historical or macro-adjusted) — a modeled range, not a forecast."
    ),
    "efficient_frontier": "Optimal risk/return combinations from mean-variance optimization.",
    "drawdown": "Largest peak-to-trough decline over the analysis period.",
    "beta": "Sensitivity vs SPY: 1.0 moves with the market; >1 is more aggressive.",
}


def _pct(x: float) -> str:
    return core.format_weight_pct(float(x), decimals=2)


def _money(x: float) -> str:
    return f"${x:,.0f}"


def render_branded_header(beginner: bool = True):
    screenshot = pp.is_screenshot_mode(st)
    if screenshot:
        pp.render_hero_banner(
            st,
            "Investment Portfolio Dashboard",
            "Live market data · Risk metrics · Monte Carlo · Efficient frontier · Portfolio optimization",
        )
        return
    if beginner:
        st.markdown(
            """
            <div class="hero-header">
              <div class="hero-inner">
                <p class="hero-eyebrow">🧭 Your Portfolio Coach</p>
                <h1 class="hero-title">Daniel Cohen Investment Portfolio Analyzer</h1>
                <p class="hero-subtitle">
                  Tell you what to do, explain why, and help you check if your portfolio is on track.
                </p>
                <p style="color:#64748b;font-size:0.78rem;margin:0 0 0.85rem 0;">Educational model-based analysis, not financial advice.</p>
                <div class="hero-badges">
                  <span class="hero-badge">📘 Start with the Guide</span>
                  <span class="hero-badge">📊 Auto market data</span>
                  <span class="hero-badge">🩺 Health score</span>
                  <span class="hero-badge">💡 Plain-English tips</span>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div class="hero-header">
              <div class="hero-inner">
                <p class="hero-eyebrow">📈 Institutional Portfolio Analytics</p>
                <h1 class="hero-title">Daniel Cohen Investment Portfolio Analyzer</h1>
                <p class="hero-subtitle">
                  Quantitative Portfolio Analytics • Risk Analysis • Monte Carlo Simulation • Optimization
                </p>
                <p style="color:#64748b;font-size:0.78rem;margin:0 0 0.85rem 0;">Educational model-based analysis, not financial advice.</p>
                <div class="hero-badges">
                  <span class="hero-badge">📘 Getting Started Guide</span>
                  <span class="hero-badge">📊 Real market data</span>
                  <span class="hero-badge">⚖️ Risk metrics</span>
                  <span class="hero-badge">🩺 Portfolio Health</span>
                  <span class="hero-badge">🎲 Monte Carlo</span>
                  <span class="hero-badge">📐 Efficient frontier</span>
                  <span class="hero-badge">🌐 Macro stress testing</span>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def section_header(title: str, lead: str = ""):
    st.markdown('<div class="section-spacer"></div>', unsafe_allow_html=True)
    st.markdown(f'<h4 class="section-title">{title}</h4>', unsafe_allow_html=True)
    if lead:
        st.markdown(f'<p class="section-lead">{lead}</p>', unsafe_allow_html=True)
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def load_market_data(tickers: tuple[str, ...], start: str, end: str | None):
    return core.fetch_price_history(list(tickers), start, end)


@st.cache_data(show_spinner=False)
def load_benchmark_returns(start: str, end: str | None):
    prices = core.fetch_price_history([core.BENCHMARK_TICKER], start, end)
    return core.daily_returns(prices).iloc[:, 0]


@st.cache_data(show_spinner=False)
def load_policy_benchmark_bundle(start: str, end: str | None, objective: str):
    """Load SPY/AGG/BIL proxies and build the objective-aware policy return series."""
    proxies = list(core.policy_benchmark_proxy_tickers())
    prices = core.fetch_price_history(proxies, start, end)
    proxy_rets = core.daily_returns(prices)
    series, meta = core.build_policy_benchmark_returns(proxy_rets, objective)
    return series, meta


@st.cache_data(show_spinner=False)
def load_comparison_prices(start: str, end: str | None):
    return core.fetch_price_history(list(core.BENCHMARK_TICKERS), start, end)


@st.cache_data(show_spinner=False)
def compute_daily_returns(prices: pd.DataFrame):
    return core.daily_returns(prices)


@st.cache_data(show_spinner=False)
def compute_risk_pack(
    returns: pd.DataFrame,
    weights_tuple: tuple[float, ...],
    initial_value: float,
    tickers_tuple: tuple[str, ...] | None = None,
):
    """Streamlit entry — delegates to core.build_risk_pack (aligned, 2-arg helpers)."""
    tickers = list(tickers_tuple) if tickers_tuple else None
    return core.build_risk_pack(
        returns,
        weights_tuple,
        initial_value,
        tickers=tickers,
    )


@st.cache_data(show_spinner=False)
def compute_optimizer_pack(
    mean_rets_tuple: tuple[float, ...],
    cov_matrix: pd.DataFrame,
    risk_free: float,
):
    mean_rets = np.asarray(mean_rets_tuple, dtype=float)
    cov = cov_matrix.values
    return {
        "max_sharpe": core.optimize_max_sharpe(mean_rets, cov, risk_free, len(mean_rets)),
        "min_vol": core.optimize_min_volatility(mean_rets, cov, risk_free, len(mean_rets)),
    }


@st.cache_data(show_spinner=False)
def compute_frontier(mean_rets_tuple: tuple[float, ...], cov_matrix: pd.DataFrame, risk_free: float, n_points: int):
    mean_rets = np.asarray(mean_rets_tuple, dtype=float)
    return core.efficient_frontier(mean_rets, cov_matrix.values, risk_free, n_points=n_points)


@st.cache_data(show_spinner=False)
def compute_monte_carlo(
    returns: pd.DataFrame,
    weights_tuple: tuple[float, ...],
    initial_value: float,
    years: int,
    simulations: int,
    target_value: float,
    expected_annual_return: float | None = None,
    expected_annual_volatility: float | None = None,
    tickers_tuple: tuple[str, ...] | None = None,
):
    weights = np.asarray(weights_tuple, dtype=float)
    tickers = list(tickers_tuple) if tickers_tuple else None
    return core.monte_carlo_simulation(
        returns=returns,
        weights=weights,
        initial_value=initial_value,
        years=years,
        simulations=simulations,
        target_value=target_value,
        expected_annual_return=expected_annual_return,
        expected_annual_volatility=expected_annual_volatility,
        tickers=tickers,
        seed=42,
    )


def render_insights(insights: list[str], *, beginner: bool = False):
    for text in insights:
        plain = text.replace("**", "")
        if beginner:
            plain = translate_for_beginner(plain)
        st.markdown(f'<div class="insight-card">💡 {plain}</div>', unsafe_allow_html=True)


def render_health_score_card(health: core.PortfolioHealthResult):
    color_class = {
        "green": "health-card-green",
        "yellow": "health-card-yellow",
        "orange": "health-card-orange",
        "red": "health-card-red",
    }.get(health.score_color, "health-card-yellow")
    st.markdown(
        f"""
        <div class="health-card {color_class}">
            <div style="font-size:0.75rem;text-transform:uppercase;letter-spacing:0.08em;color:#94a3b8;">
                Portfolio Health Score
            </div>
            <div style="font-size:2.4rem;font-weight:700;color:#f1f5f9;line-height:1.1;">
                {health.score:.0f}<span style="font-size:1rem;color:#94a3b8;"> / 100</span>
            </div>
            <div style="font-size:1rem;font-weight:600;color:#e2e8f0;margin-top:0.25rem;">
                {health.score_label}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _portfolio_fingerprint(tickers: list[str], weights: np.ndarray) -> str:
    w = core.normalize_weights(weights)
    return "|".join(f"{t}:{w[i]:.4f}" for i, t in enumerate(tickers))


def get_health_cache_status(tickers: list[str], weights: np.ndarray) -> str:
    """fresh | missing | portfolio_stale | settings_stale"""
    if not st.session_state.get("health_result"):
        return "missing"
    if st.session_state.get("health_result_fingerprint") != _portfolio_fingerprint(tickers, weights):
        return "portfolio_stale"
    if st.session_state.get("health_settings_fingerprint") != health_settings_fingerprint():
        return "settings_stale"
    # Diagnostic schema mismatch (e.g. Sharpe-vs-policy key fix) → force refresh.
    health_obj = st.session_state.get("health_result")
    diag = getattr(health_obj, "health_diagnostics", None) or {}
    if not core.health_diagnostics_schema_is_current(diag):
        st.session_state.pop("health_result", None)
        st.session_state.pop("health_result_fingerprint", None)
        st.session_state.pop("health_summary", None)
        return "missing"
    return "fresh"


def render_sharpe_vs_policy_metric(diag: dict) -> str:
    """Exact UI/caller path for Sharpe-vs-policy. Keyword floats only — never Sortino."""
    port = diag.get("portfolio_sharpe", diag.get("raw_sharpe"))
    pol = diag.get("policy_benchmark_sharpe", diag.get("policy_sharpe"))
    try:
        port_f = float(port)
        pol_f = float(pol)
    except (TypeError, ValueError):
        return "n/a"
    # Integrity: refuse if policy slot equals portfolio Sortino while policy Sortino differs.
    sortino = diag.get("sortino")
    pol_sortino = diag.get("policy_sortino")
    try:
        if (
            sortino is not None
            and abs(pol_f - float(sortino)) < 1e-12
            and pol_sortino is not None
            and abs(pol_f - float(pol_sortino)) > 1e-4
        ):
            return "n/a"
    except (TypeError, ValueError):
        pass
    return core.build_sharpe_vs_policy_metric_value(
        portfolio_sharpe=port_f,
        policy_benchmark_sharpe=pol_f,
    )


def cache_health_summary(health: core.PortfolioHealthResult, tickers: list[str], weights: np.ndarray) -> None:
    fp = _portfolio_fingerprint(tickers, weights)
    settings_fp = health_settings_fingerprint()
    st.session_state.health_summary = {
        "score": float(health.score),
        "score_label": health.score_label,
        "score_color": health.score_color,
        "fingerprint": fp,
        "settings_fingerprint": settings_fp,
    }
    st.session_state.health_result = health
    st.session_state.health_result_fingerprint = fp
    st.session_state.health_settings_fingerprint = settings_fp
    try:
        from applied_math_context import record_rebalance_from_health

        record_rebalance_from_health(st.session_state, health)
    except Exception:
        pass
    try:
        from investment_workflow import mark_analysis_complete, record_workflow_health_status

        mark_analysis_complete(st)
        record_workflow_health_status("fresh", st)
    except ImportError:
        st.session_state.portfolio_analyzed = True
    try:
        from investment_activity import log_portfolio_health_checked

        log_portfolio_health_checked(
            st,
            score=float(health.score),
            score_label=health.score_label,
            tickers=list(tickers),
        )
    except Exception:
        pass


def get_cached_health(tickers: list[str], weights: np.ndarray) -> core.PortfolioHealthResult | None:
    if get_health_cache_status(tickers, weights) != "fresh":
        return None
    return st.session_state.get("health_result")


def sync_workflow_health_status(tickers: list[str], weights: np.ndarray) -> str:
    """Align workflow checklist flags with the health cache (after reconcile)."""
    status = get_health_cache_status(tickers, weights)
    try:
        from investment_workflow import record_workflow_health_status

        record_workflow_health_status(status, st)
    except ImportError:
        pass
    return status


def evaluate_portfolio_health_if_needed(
    *,
    settings: dict,
    tickers: list[str],
    weights: np.ndarray,
    asset_types: list[str],
    metrics: core.ExtendedMetrics,
    returns: pd.DataFrame,
    mean_rets: np.ndarray,
    cov: np.ndarray,
    base_risk_pack: dict,
    bench_rets: pd.Series | None,
) -> core.PortfolioHealthResult | None:
    """Run portfolio health when ``run_health`` is set; return cached result when fresh."""
    if not st.session_state.get("run_health", False):
        return get_cached_health(tickers, weights)

    cached = get_cached_health(tickers, weights)
    if cached is not None:
        return cached

    health_objective = st.session_state.get("health_objective", "balanced growth")
    health_run_optimizer = bool(st.session_state.get("health_run_optimizer", False))
    health_bond_min = float(st.session_state.get("health_bond_min", 0) or 0)
    health_assumptions = macro_assumptions_from_session()
    opt_weights = None
    if health_run_optimizer:
        with st.spinner("Running optimizer for drift comparison…"):
            opt_pack = compute_optimizer_pack(tuple(mean_rets.tolist()), cov, settings["risk_free"])
            opt_weights = opt_pack["max_sharpe"].weights

    policy_rets = None
    policy_meta: dict = {}
    try:
        policy_rets, policy_meta = load_policy_benchmark_bundle(
            settings["start"], settings["end"], str(health_objective)
        )
    except Exception as _policy_exc:
        policy_meta = {"ok": False, "error": str(_policy_exc)}

    rec = core.recommend_portfolio(35, 15, "Medium", "Medium", health_objective)
    with st.spinner("Evaluating portfolio health…"):
        health = core.evaluate_portfolio_health(
            tickers=tickers,
            weights=weights,
            asset_types=asset_types,
            metrics=metrics,
            asset_returns=returns,
            corr=base_risk_pack["corr"],
            risk_contrib_df=base_risk_pack["risk_contrib"],
            assumptions=health_assumptions,
            objective=health_objective,
            risk_free_rate=settings["risk_free"],
            initial_value=settings["initial_value"],
            benchmark_returns=bench_rets,
            optimizer_weights=opt_weights,
            recommended_type_mix=rec.allocation,
            bond_min_pct=float(health_bond_min) if health_bond_min > 0 else None,
            policy_benchmark_returns=policy_rets,
            policy_benchmark_meta=policy_meta,
        )
    cache_health_summary(health, tickers, weights)
    st.session_state.run_health = False
    st.session_state["_workflow_analysis_just_completed"] = True
    return health


def get_health_badge_state(tickers: list[str], weights: np.ndarray) -> tuple[str, dict | None]:
    status = get_health_cache_status(tickers, weights)
    summary = st.session_state.get("health_summary")
    if status == "fresh" and summary:
        return "ok", summary
    if status == "settings_stale":
        return "settings_stale", summary
    if status == "portfolio_stale":
        return "stale", None
    return "missing", None


def render_health_header_badge(slot, tickers: list[str], weights: np.ndarray) -> None:
    state, summary = get_health_badge_state(tickers, weights)
    disclaimer = APP_DISCLAIMER

    if state == "ok" and summary:
        color_class = {
            "green": "health-header-badge-green",
            "yellow": "health-header-badge-yellow",
            "orange": "health-header-badge-orange",
            "red": "health-header-badge-red",
        }.get(summary["score_color"], "health-header-badge-yellow")
        html = f"""
        <div class="health-header-badge {color_class}">
            <span>🩺 <strong>Portfolio Health</strong></span>
            <span class="health-header-score">{summary['score']:.0f}<span style="font-weight:500;color:#94a3b8;"> / 100</span></span>
            <span class="health-header-label">{summary['score_label']}</span>
            <span class="health-header-note">{disclaimer}</span>
        </div>
        """
    elif state == "stale":
        html = f"""
        <div class="health-header-badge health-header-badge-neutral">
            <span>🩺 <strong>Portfolio Health</strong></span>
            <span class="health-header-prompt">Portfolio changed — run Portfolio Health analysis for updated score.</span>
            <span class="health-header-note">{disclaimer}</span>
        </div>
        """
    elif state == "settings_stale" and summary:
        html = f"""
        <div class="health-header-badge health-header-badge-yellow">
            <span>🩺 <strong>Portfolio Health</strong></span>
            <span class="health-header-score">{summary['score']:.0f}<span style="font-weight:500;color:#94a3b8;"> / 100</span></span>
            <span class="health-header-label">May be outdated — objective or macro settings changed</span>
            <span class="health-header-note">{disclaimer}</span>
        </div>
        """
    else:
        html = f"""
        <div class="health-header-badge health-header-badge-neutral">
            <span>🩺 <strong>Portfolio Health</strong></span>
            <span class="health-header-prompt">Run Portfolio Health analysis for updated score.</span>
            <span class="health-header-note">{disclaimer}</span>
        </div>
        """
    slot.markdown(html, unsafe_allow_html=True)


def metrics_row_primary(m: core.ExtendedPortfolioMetrics, initial: float, settings: dict):
    h = metric_help(settings)
    beginner = is_beginner_mode(settings)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Average Yearly Return (Historical)" if beginner else "Historical Annualized Return",
        _pct(m.annual_return),
        help=h["annual_return"],
    )
    c2.metric(
        "Typical Ups & Downs (Historical)" if beginner else "Historical Annualized Volatility",
        _pct(m.volatility),
        help=h["volatility"],
    )
    c3.metric(
        "Risk/Reward Score (Historical)" if beginner else "Historical Sharpe Ratio",
        f"{m.sharpe_ratio:.2f}",
        help=h["sharpe"],
    )
    c4.metric(
        "Estimated Value (1 Year)" if beginner else "Projected Value (1Y)",
        _money(m.projected_value),
        delta=_money(m.projected_value - initial),
        help=h["projected"],
    )


def metrics_row_extended(m: core.ExtendedPortfolioMetrics, settings: dict):
    h = metric_help(settings)
    beginner = is_beginner_mode(settings)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Worst Drop (Historical)" if beginner else "Historical Maximum Drawdown",
        _pct(m.max_drawdown),
        help=h["drawdown"],
    )
    c2.metric(
        "Downside Risk Score" if beginner else "Sortino Ratio",
        f"{m.sortino_ratio:.2f}",
        help=h["sortino"],
    )
    c3.metric(
        "Steady Growth Rate" if beginner else "CAGR",
        _pct(m.cagr),
        help=h["cagr"],
    )
    c4.metric(
        "Vs. Market Move" if beginner else "Beta vs SPY",
        f"{m.beta_spy:.2f}",
        help=h["beta"],
    )


def render_sidebar() -> dict:
    try:
        from planning_portfolio_value import reset_sidebar_portfolio_widget_gate_for_run

        reset_sidebar_portfolio_widget_gate_for_run(st.session_state)
    except Exception:
        pass
    apply_pending_sidebar_portfolio_value()
    try:
        from investment_persistence_trace import bump_pr1_render_pass

        bump_pr1_render_pass(st)
    except Exception:
        pass
    if _PERSISTENCE_OK:
        try:
            from investment_persistence_trace import render_persistence_trace_sidebar

            render_persistence_trace_sidebar(st, persistence_ok=_PERSISTENCE_OK)
        except Exception as _pr1_trace_exc:
            st.session_state["_pr1_trace_sidebar_error"] = str(_pr1_trace_exc)
        try:
            from investment_persistence_trace import render_investment_diagnostics_controls

            render_investment_diagnostics_controls(st, persistence_ok=_PERSISTENCE_OK)
        except Exception as _pr1_diag_exc:
            st.session_state["_pr1_diag_checkbox_error"] = str(_pr1_diag_exc)
    # Account & Workspace (CC / Saved Sessions / Log out) renders earlier at module
    # scope. Keep suite shell only for developer diagnostics — no duplicate account
    # panel or Command Center link.
    try:
        from suite_app_shell import render_suite_sidebar_account_shell

        render_suite_sidebar_account_shell(
            st,
            show_account_panel=False,
            show_command_center_link=False,
            command_center_divider=False,
        )
    except Exception:
        pass
    _inv_dev = False
    try:
        from suite_workspace import can_show_developer_tools

        _inv_dev = can_show_developer_tools(st=st)
    except Exception:
        pass
    try:
        from suite_analytical_question import render_applied_math_sidebar_entry

        try:
            from applied_math_context import (
                build_investment_applied_math_context,
                ensure_investment_source_state,
            )
        except Exception:
            build_investment_applied_math_context = None  # type: ignore[misc, assignment]
            ensure_investment_source_state = None  # type: ignore[misc, assignment]

        _inv_tab = str(st.session_state.get("investment_active_tab") or "Overview")

        render_applied_math_sidebar_entry(
            st,
            source_app="investment",
            source_page=_inv_tab,
            session_state=st.session_state,
            developer_mode=_inv_dev,
            context_extra_builder=(
                lambda: build_investment_applied_math_context(_inv_tab, st.session_state)
                if build_investment_applied_math_context
                else None
            ),
            source_state_builder=(
                lambda: ensure_investment_source_state(_inv_tab, st.session_state)
                if ensure_investment_source_state
                else None
            ),
        )
    except Exception as _ami_sidebar_exc:
        st.session_state["_pr1_ami_sidebar_error"] = str(_ami_sidebar_exc)
    pp.render_sidebar_toggle(st)
    if _PERSISTENCE_OK:
        try:
            from investment_workflow import developer_access_available, render_developer_sidebar_controls

            render_developer_sidebar_controls(st)
            if developer_access_available(st):
                from investment_workflow import developer_diagnostics_enabled
                from investment_persistent_state import render_persistence_debug_sidebar

                if developer_diagnostics_enabled(st):
                    render_persistence_debug_sidebar(st)
        except ImportError:
            pass
    st.sidebar.markdown("### Experience")
    ensure_analysis_date_defaults(st)
    ensure_experience_mode(st)
    experience = st.sidebar.radio(
        "Experience level",
        list(EXPERIENCE_OPTIONS),
        key=EXPERIENCE_KEY,
        help="Beginner: simpler language and fewer charts. Advanced: full analytics.",
        label_visibility="collapsed",
    )
    sync_experience_after_widget(st)
    st.session_state["_suite_inv_debug_experience_end_of_sidebar"] = {
        "widget": st.session_state.get(EXPERIENCE_KEY),
        "persisted": st.session_state.get(PERSISTED_EXPERIENCE_KEY),
        "user_choice": st.session_state.get("_suite_inv_experience_user_choice"),
        "active": experience,
        "restore_ran": st.session_state.get("_suite_inv_debug_restore_ran"),
        "cloud_resync_ran": st.session_state.get("_suite_inv_cloud_resync_ran"),
    }
    beginner = experience == "Beginner Mode"

    if beginner:
        render_beginner_sidebar_checklist()
        try:
            from investment_workflow import render_workflow_state_trace

            render_workflow_state_trace(st, beginner=True)
        except ImportError:
            pass

    refresh_market_data_sidebar()

    st.sidebar.divider()
    st.sidebar.markdown("### Investment amount")
    st.sidebar.caption("Used for dollar amounts across all tables and suggestions.")
    from investment_persistent_state import (
        _PORTFOLIO_VALUE_USER_SET_KEY,
        ensure_sidebar_portfolio_value_default,
        notify_global_settings_change,
    )
    from planning_portfolio_value import (
        initialize_sidebar_portfolio_value_before_widget,
        mark_sidebar_portfolio_widget_instantiated,
    )

    apply_pending_sidebar_portfolio_value()
    initialize_sidebar_portfolio_value_before_widget(st.session_state)
    ensure_sidebar_portfolio_value_default(st)

    def _on_portfolio_value_widget_change() -> None:
        st.session_state[_PORTFOLIO_VALUE_USER_SET_KEY] = True
        notify_global_settings_change(st, source="portfolio_value_widget")

    initial_value = st.sidebar.number_input(
        "Portfolio value ($)",
        min_value=1_000,
        max_value=10_000_000,
        step=5_000,
        help="Total investable amount for allocation dollar estimates.",
        key="sidebar_portfolio_value",
        on_change=_on_portfolio_value_widget_change,
    )
    mark_sidebar_portfolio_widget_instantiated(st.session_state)

    st.sidebar.divider()
    st.sidebar.markdown("### Portfolio Presets")
    st.sidebar.caption(
        "Sample allocation mixes only — they do **not** change your investment goal. "
        "Pick a goal on Step 1; use presets here to load example holdings."
    )
    preset_names = ["— custom —", *core.PORTFOLIO_PRESETS.keys()]
    validate_state_option(st, "portfolio_preset", preset_names, "— custom —")
    portfolio_preset = st.sidebar.selectbox(
        "Strategy",
        preset_names,
        key="portfolio_preset",
        label_visibility="collapsed",
    )
    if st.sidebar.button("Apply preset", use_container_width=True, type="primary"):
        if portfolio_preset in core.PORTFOLIO_PRESETS:
            try:
                from investment_workflow import invalidate_workflow_from

                invalidate_workflow_from("portfolio")
            except ImportError:
                pass
            st.session_state.holdings_df = pd.DataFrame(core.PORTFOLIO_PRESETS[portfolio_preset])
            st.session_state.preset_applied = portfolio_preset
            if _PERSISTENCE_OK:
                try:
                    from investment_persistent_state import notify_portfolio_change

                    notify_portfolio_change(st, source="apply_preset")
                except Exception:
                    pass
            if beginner:
                from components.beginner_navigation import OBJECTIVE_TO_PRESET, sync_beginner_goal_keys_from_portfolio

                for objective, preset_name in OBJECTIVE_TO_PRESET.items():
                    if preset_name == portfolio_preset:
                        st.session_state.health_objective = objective
                        break
                st.session_state.guide_portfolio_loaded = False
                st.session_state.portfolio_built = False
                sync_beginner_goal_keys_from_portfolio(st)
            st.session_state.pop("health_summary", None)
            st.rerun()

    st.sidebar.divider()
    st.sidebar.markdown("### Historical Lookback")
    st.sidebar.caption(HISTORICAL_LOOKBACK_DATE_HELP)
    ca, cb = st.sidebar.columns(2)
    with ca:
        start_date = st.date_input(
            "Historical Lookback Start",
            key="analysis_start_date",
            help=HISTORICAL_LOOKBACK_DATE_HELP,
        )
    with cb:
        end_date = st.date_input(
            "Historical Lookback End",
            key="analysis_end_date",
            help=HISTORICAL_LOOKBACK_DATE_HELP,
        )
    render_historical_window_summary(start=start_date, end=end_date)
    render_historical_period_sidebar_help(beginner=beginner)

    from investment_persistent_state import ensure_risk_free_pct_default

    ensure_risk_free_pct_default(st)

    def _on_risk_free_widget_change() -> None:
        notify_global_settings_change(st, source="risk_free_widget")

    st.sidebar.slider(
        "Risk-free rate (%)",
        0.0,
        10.0,
        4.0,
        0.25,
        help="Return on very safe assets like T-Bills. Used in risk/reward scores." if beginner
        else "Risk-free rate for Sharpe/Sortino.",
        key="risk_free_pct",
        on_change=_on_risk_free_widget_change,
    )
    risk_free = float(st.session_state.get("risk_free_pct", 4.0)) / 100.0

    st.sidebar.divider()
    st.sidebar.markdown("### Quick-add asset")
    asset_preset = st.sidebar.selectbox("ETF preset", ["—"] + list(core.ASSET_PRESETS.keys()))

    st.sidebar.divider()
    st.sidebar.markdown("### Export")
    st.sidebar.caption("Downloads appear after analysis loads.")

    st.sidebar.divider()
    st.sidebar.caption(APP_DISCLAIMER)

    frontier_points = 2000
    if not beginner:
        st.sidebar.divider()
        st.sidebar.markdown("### Performance")
        frontier_points = st.sidebar.select_slider(
            "Frontier granularity",
            options=[200, 500, 1000, 2000],
            value=2000,
            help="Lower values run faster. 2,000 is default institutional setting.",
        )

    if _PERSISTENCE_OK:
        try:
            from investment_persistent_state import sync_global_settings_after_widgets

            sync_global_settings_after_widgets(st)
        except Exception:
            pass
        try:
            from investment_persistence_trace import (
                ensure_pr1_trace_snapshot,
                render_pr1_verification_sidebar,
            )

            ensure_pr1_trace_snapshot(st, persistence_ok=_PERSISTENCE_OK)
            render_pr1_verification_sidebar(st, persistence_ok=_PERSISTENCE_OK)
        except Exception as _pr1_verify_exc:
            st.sidebar.warning(f"PR1 verification panel failed: {_pr1_verify_exc}")

    return {
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "initial_value": float(initial_value),
        "risk_free": float(risk_free),
        "portfolio_preset": portfolio_preset,
        "asset_preset": asset_preset,
        "experience": experience,
        "frontier_points": int(frontier_points),
    }


def init_holdings():
    if "holdings_df" not in st.session_state:
        if _PERSISTENCE_OK:
            cloud_saved = False
            try:
                from investment_persistent_state import _cloud_has_saved_portfolio

                cloud_state, _ = _cloud_has_saved_portfolio()
                cloud_saved = cloud_state is not None
            except Exception:
                cloud_saved = False
            st.session_state.holdings_df = pd.DataFrame()
            st.session_state["default_holdings_applied"] = False
            if cloud_saved:
                st.session_state["_suite_inv_holdings_restore_issue"] = "holdings_pending_startup_cloud_fixup"
                st.session_state["default_holdings_apply_reason"] = "deferred_for_cloud_fixup"
            else:
                st.session_state["default_holdings_apply_reason"] = "deferred_for_persistence_bootstrap"
        elif st.session_state.get("portfolio_built") or st.session_state.get("_suite_inv_holdings_restore_issue"):
            st.session_state.holdings_df = pd.DataFrame()
            st.session_state["default_holdings_applied"] = False
        else:
            st.session_state.holdings_df = pd.DataFrame(core.DEFAULT_HOLDINGS)
            st.session_state["default_holdings_applied"] = True
            st.session_state["default_holdings_apply_reason"] = "init_holdings_no_saved_portfolio"


def apply_asset_preset(name: str):
    if name == "—":
        return
    info = core.ASSET_PRESETS[name]
    df = st.session_state.holdings_df.copy()
    if info["ticker"] not in df["Ticker"].astype(str).str.upper().values:
        try:
            import etf_holdings as eh

            fund = eh.infer_portfolio_fund_info(info["ticker"])
            asset_type = fund["asset_type"]
        except Exception:
            asset_type = info["category"]
        df = pd.concat(
            [df, pd.DataFrame([{"Ticker": info["ticker"], "Weight (%)": 0.0, "Asset Type": asset_type}])],
            ignore_index=True,
        )
        st.session_state.holdings_df = df
        try:
            from investment_activity import log_ticker_analyzed

            log_ticker_analyzed(st, ticker=info["ticker"])
        except Exception:
            pass


def parse_holdings(df: pd.DataFrame):
    clean = df.dropna(subset=["Ticker"]).copy()
    clean["Ticker"] = clean["Ticker"].astype(str).str.strip().str.upper()
    clean = clean[clean["Ticker"] != ""]
    if clean.empty:
        raise ValueError("Add at least one ticker.")
    wp = clean["Weight (%)"].fillna(0).astype(float).values
    weights = np.ones(len(clean)) / len(clean) if wp.sum() <= 0 else core.normalize_weights(wp / 100.0)
    types = clean.get("Asset Type", pd.Series(["Equity"] * len(clean))).fillna("Equity").tolist()
    return clean["Ticker"].tolist(), weights, types


def render_overview_health_snapshot(tickers: list[str], weights: np.ndarray) -> None:
    status = get_health_cache_status(tickers, weights)
    state, summary = get_health_badge_state(tickers, weights)

    if status == "settings_stale":
        st.warning(
            "⚠️ **Health analysis may be outdated.** Your objective or macro assumptions changed. "
            "Click **Analyze Portfolio** below to refresh."
        )
        stale = st.session_state.get("health_result")
        if stale:
            st.caption(f"Previous score (earlier settings): **{stale.score:.0f}/100** — {stale.score_label}")

    if state == "ok" and summary:
        color_class = {
            "green": "health-card-green",
            "yellow": "health-card-yellow",
            "orange": "health-card-orange",
            "red": "health-card-red",
        }.get(summary["score_color"], "health-card-yellow")
        st.markdown(
            f"""
            <div class="health-card {color_class}">
                <div style="font-size:0.75rem;text-transform:uppercase;letter-spacing:0.08em;color:#94a3b8;">
                    Portfolio Health Score
                </div>
                <div style="font-size:2.4rem;font-weight:700;color:#f1f5f9;line-height:1.1;">
                    {summary['score']:.0f}<span style="font-size:1rem;color:#94a3b8;"> / 100</span>
                </div>
                <div style="font-size:1rem;font-weight:600;color:#e2e8f0;margin-top:0.25rem;">
                    {summary['score_label']}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        if status != "settings_stale":
            st.info(
                "No health score yet. Click **Analyze Portfolio** below or open **Portfolio Health** "
                "and click **Refresh Portfolio Health**."
            )


def _render_recommendation_engine(
    beginner: bool = False,
    initial_value: float | None = None,
    key_prefix: str = "recommendation",
) -> None:
    if initial_value is None:
        initial_value = float(
            st.session_state.get("sidebar_portfolio_value", st.session_state.get("initial_value", 100_000))
        )

    section_header(
        "Get a suggested portfolio" if beginner else "Portfolio Recommendation Engine",
        "Answer a few questions for a starting mix you can apply with one click." if beginner
        else "Generate a suggested allocation from age, horizon, risk, liquidity, and objective.",
    )
    r1, r2, r3 = st.columns(3)
    with r1:
        rec_age = st.number_input(
            "Age", min_value=18, max_value=100, value=35, key=f"{key_prefix}_age_input"
        )
        rec_horizon = st.slider(
            "Years until you need the money", 1, 40, 15, key=f"{key_prefix}_horizon_slider"
        )
    with r2:
        rec_risk = st.selectbox(
            "Comfort with ups and downs", ["Low", "Medium", "High"], index=1, key=f"{key_prefix}_risk_sel"
        )
        rec_liq = st.selectbox(
            "Need cash soon?", ["Low", "Medium", "High"], index=1, key=f"{key_prefix}_liq_sel"
        )
    with r3:
        rec_obj = st.selectbox(
            "Main goal",
            [
                "capital preservation",
                "balanced growth",
                "aggressive growth",
                "income",
                "retirement",
                "short-term cash management",
            ],
            index=1,
            key=f"{key_prefix}_obj_sel",
        )
    rec = core.recommend_portfolio(rec_age, rec_horizon, rec_risk, rec_liq, rec_obj)
    for reason in rec.rationale:
        st.markdown(f"- {reason}")
    rec_df = pd.DataFrame(rec.suggested_holdings)
    rec_df["Value ($)"] = rec_df["Weight (%)"] / 100.0 * initial_value
    rec_display = rec_df.copy()
    rec_display["Value ($)"] = rec_display["Value ($)"].map(_money)
    st.dataframe(rec_display, use_container_width=True, hide_index=True)
    if st.button(
        "Use this suggested portfolio",
        use_container_width=False,
        key=f"{key_prefix}_apply_rec",
    ):
        st.session_state.holdings_df = rec_df
        st.session_state.pop("health_summary", None)
        try:
            from components.beginner_navigation import mark_portfolio_built

            mark_portfolio_built(st, holdings_df=rec_df)
        except Exception:
            pass
        st.success("Applied to Portfolio Inputs.")
        st.rerun()


def render_overview_tab(
    settings: dict,
    metrics: core.ExtendedPortfolioMetrics,
    holdings_df: pd.DataFrame,
    growth: pd.Series,
    insights: list[str],
    explanation: core.PortfolioExplanation,
    returns: pd.DataFrame,
    weights: np.ndarray,
    tickers: list[str],
    asset_types: list[str],
    base_risk_pack: dict,
) -> None:
    beginner = is_beginner_mode(settings)
    cached_health = get_cached_health(tickers, weights)
    health_status = get_health_cache_status(tickers, weights)

    if beginner:
        if render_recommended_next_step_card():
            st.rerun()

        _ov_subtab_labels = [
            "📍 Your Plan",
            "❤️ Health",
            "📋 Recommendations",
            "🔄 Rebalancing",
            "📈 Performance",
            "📅 Monthly",
        ]
        from investment_persistent_state import validate_state_option

        validate_state_option(st, "overview_subtab", _ov_subtab_labels, _ov_subtab_labels[0])
        _ov_active = st.radio(
            "Overview section",
            _ov_subtab_labels,
            key="overview_subtab",
            horizontal=True,
            label_visibility="collapsed",
        )

        if _ov_active == _ov_subtab_labels[0]:
            if cached_health:
                objective = st.session_state.get("health_objective", "balanced growth")
                render_action_plan(
                    cached_health.action_plan,
                    score=cached_health.score,
                    objective=objective,
                    beginner=True,
                )
            elif health_status == "settings_stale" and st.session_state.get("health_result"):
                stale = st.session_state.health_result
                st.warning("Action plan may be outdated — click **Analyze Portfolio** on the Health tab.")
                render_action_plan(stale.action_plan, score=stale.score, objective=st.session_state.get("health_objective", "balanced growth"), beginner=True)
            else:
                render_action_plan_placeholder(True)
            if st.button(RUN_PORTFOLIO_ANALYSIS_LABEL, type="primary", key="overview_analyze_btn"):
                st.session_state.run_health = True
                st.session_state.health_refresh = st.session_state.get("health_refresh", 0) + 1
                try:
                    from investment_workflow import request_core_step_navigation

                    request_core_step_navigation("analyze", beginner=True)
                except ImportError:
                    pass

        if _ov_active == _ov_subtab_labels[1]:
            what_why_do(
                "Portfolio Health Score",
                "A 0–100 summary of return, risk, diversification, and goal fit.",
                "Quick checkup — not a grade on you.",
                "Click Analyze Portfolio on **Your Plan**, then open **❤️ Portfolio Health** for details.",
            )
            render_overview_health_snapshot(tickers, weights)
            if explanation.portfolio_overview:
                for item in explanation.portfolio_overview[:3]:
                    st.markdown(f"- {item}")

        if _ov_active == _ov_subtab_labels[2]:
            if cached_health:
                render_recommendations_panel(cached_health, settings)
            elif health_status == "settings_stale" and st.session_state.get("health_result"):
                st.warning("Recommendations may be outdated — refresh analysis.")
                render_recommendations_panel(st.session_state.health_result, settings)
            else:
                st.caption("Run **Analyze Portfolio** on the Your Plan tab for full Why? explanations.")
                for item in explanation.suggested_improvements[:5]:
                    st.markdown(f'<div class="insight-card">💡 {translate_for_beginner(item.replace("**", ""))}</div>', unsafe_allow_html=True)

        if _ov_active == _ov_subtab_labels[3]:
            if cached_health:
                render_rebalancing_panel(cached_health, settings=settings, key_prefix="overview_rebal")
                with st.expander("Guided adjustment (optional)", expanded=False):
                    render_guided_portfolio_adjustment(
                        cached_health,
                        tickers=tickers,
                        weights=weights,
                        asset_types=asset_types,
                        settings=settings,
                        metrics=metrics,
                        returns=returns,
                        assumptions=macro_assumptions_from_session(),
                        key_prefix="overview_guided",
                    )
            else:
                st.info("Run **Analyze Portfolio** first to see dollar-based rebalance guidance.")

        if _ov_active == _ov_subtab_labels[4]:
            render_historical_metrics_banner()
            metrics_row_primary(metrics, settings["initial_value"], settings)
            if st.toggle("Show more detail numbers", value=False, key="overview_show_extended_metrics"):
                metrics_row_extended(metrics, settings)
            c1, c2 = st.columns(2)
            with c1:
                gdf = growth.reset_index()
                gdf.columns = ["Date", "Portfolio Value"]
                st.plotly_chart(charts.growth_chart(gdf), use_container_width=True)
            with c2:
                st.plotly_chart(charts.allocation_chart(holdings_df), use_container_width=True)

        if _ov_active == _ov_subtab_labels[5]:
            render_monthly_review_workflow(expanded=True)
            st.caption("Implementation steps: **💼 Portfolio Inputs** → **Implementation Guide** tab.")

        with st.expander("Get a suggested portfolio (optional)", expanded=False):
            _render_recommendation_engine(
                beginner=True,
                initial_value=settings["initial_value"],
                key_prefix="overview_rec_beginner",
            )
        return

    section_header("Dashboard", f"Portfolio overview. {APP_DISCLAIMER}")

    st.markdown("---")
    section_header(
        "Portfolio Journey / Action Plan",
        "Simple answers: what to look at today, this month, and this year." if beginner
        else "Decision-support timeline derived from Portfolio Health.",
    )
    if cached_health:
        objective = st.session_state.get("health_objective", "balanced growth")
        render_action_plan(
            cached_health.action_plan,
            score=cached_health.score,
            objective=objective,
            beginner=beginner,
        )
    elif health_status == "settings_stale":
        stale = st.session_state.get("health_result")
        if stale:
            st.warning("Action plan may be outdated — macro, objective, or historical lookback changed. Click **Analyze Portfolio** to refresh.")
            objective = st.session_state.get("health_objective", "balanced growth")
            render_action_plan(
                stale.action_plan,
                score=stale.score,
                objective=objective,
                beginner=beginner,
            )
        else:
            render_action_plan_placeholder(beginner)
    else:
        render_action_plan_placeholder(beginner)

    # ── Priority 1–3: Health, status, recommendations ───────────────────────
    section_header(
        "Portfolio Health" if beginner else "Portfolio Health Snapshot",
        "Your portfolio checkup — higher is generally better in this model." if beginner
        else "Cached health score from Portfolio Health analysis.",
    )
    if beginner:
        what_why_do(
            "Portfolio Health Score",
            "A 0–100 summary of how your mix looks on return, risk, diversification, and goal fit.",
            "It helps you see at a glance whether your portfolio may need attention.",
            "Click Analyze Portfolio, then read What's Working and suggestions on the Portfolio Health tab.",
        )
    col_a, col_b = st.columns([1, 1.2])
    with col_a:
        render_overview_health_snapshot(tickers, weights)
    with col_b:
        if explanation.portfolio_overview:
            st.markdown("**Status summary**")
            for item in explanation.portfolio_overview[:3]:
                st.markdown(f"- {item}")

    if st.button(RUN_PORTFOLIO_ANALYSIS_LABEL, type="primary", key="overview_analyze_btn_adv"):
        st.session_state.run_health = True
        st.session_state.health_refresh = st.session_state.get("health_refresh", 0) + 1
        try:
            from investment_workflow import request_core_step_navigation

            request_core_step_navigation("analyze", beginner=False)
        except ImportError:
            pass

    st.markdown("---")
    section_header(
        "Recommendations & why" if beginner else "Recommendations with model reasoning",
        "Every suggestion includes a Why? explanation — no black box." if beginner
        else "Issue, trigger metrics, and tradeoffs for each model flag.",
    )
    if cached_health:
        render_recommendations_panel(cached_health, settings)
        st.markdown("---")
        render_guided_portfolio_adjustment(
            cached_health,
            tickers=tickers,
            weights=weights,
            asset_types=asset_types,
            settings=settings,
            metrics=metrics,
            returns=returns,
            assumptions=macro_assumptions_from_session(),
            key_prefix="overview_guided",
        )
        if beginner:
            st.markdown("---")
            render_implementation_guide(
                tickers=tickers,
                weights=weights,
                asset_types=asset_types,
                settings=settings,
                health=cached_health,
                key_prefix="overview_impl",
            )
    elif health_status == "settings_stale" and st.session_state.get("health_result"):
        st.warning("Recommendations may be outdated — refresh analysis to update.")
        stale_h = st.session_state.health_result
        render_recommendations_panel(stale_h, settings)
        if beginner:
            st.markdown("---")
            render_implementation_guide(
                tickers=tickers,
                weights=weights,
                asset_types=asset_types,
                settings=settings,
                health=stale_h,
                key_prefix="overview_impl_stale",
            )
    else:
        if beginner and explanation.suggested_improvements:
            st.caption("Run **Analyze Portfolio** above for full Why? explanations tied to your metrics.")
            for item in explanation.suggested_improvements[:5]:
                plain = translate_for_beginner(item.replace("**", "")) if beginner else item.replace("**", "")
                st.markdown(f'<div class="insight-card">💡 {plain}</div>', unsafe_allow_html=True)
        render_insights(insights, beginner=beginner)
        if explanation.weaknesses and beginner:
            st.markdown("**Areas to watch**")
            for item in explanation.weaknesses[:3]:
                st.markdown(f"- {item}")
        if beginner:
            st.markdown("---")
            render_implementation_guide(
                tickers=tickers,
                weights=weights,
                asset_types=asset_types,
                settings=settings,
                health=None,
                key_prefix="overview_impl_basic",
            )

    # ── Priority 4: Performance ───────────────────────────────────────────────
    st.markdown("---")
    section_header(
        "How your portfolio has performed" if beginner else "Portfolio Summary",
        "Based on past market data for your current mix — not a forecast." if beginner
        else f"Historical risk/return based on daily returns. {APP_DISCLAIMER}",
    )
    if beginner:
        what_why_do(
            "Performance numbers",
            "These describe how your mix behaved in the past over the dates in the sidebar.",
            "They help you compare options and set expectations about risk.",
            "Focus on return vs. how bumpy the ride was. Use Refresh Market Data monthly.",
        )
    render_historical_metrics_banner()
    metrics_row_primary(metrics, settings["initial_value"], settings)
    if not beginner:
        metrics_row_extended(metrics, settings)
    elif st.toggle("Show more detail numbers", value=False, key="overview_show_extended_metrics"):
        metrics_row_extended(metrics, settings)

    c1, c2 = st.columns([1.2, 1])
    with c1:
        section_header("Growth over time" if beginner else "Growth Over Time")
        gdf = growth.reset_index()
        gdf.columns = ["Date", "Portfolio Value"]
        st.plotly_chart(charts.growth_chart(gdf), use_container_width=True)
    with c2:
        section_header("Your mix" if beginner else "Allocation")
        st.plotly_chart(charts.allocation_chart(holdings_df), use_container_width=True)

    st.markdown("---")
    section_header("Your holdings")
    disp = holdings_df.copy()
    disp["Weight (%)"] = disp["Weight (%)"].map(lambda x: f"{x:.1f}%")
    disp["Value ($)"] = disp["Value ($)"].map(_money)
    st.dataframe(disp, use_container_width=True, hide_index=True)

    # ── Recommendation engine ───────────────────────────────────────────
    st.markdown("---")
    _render_recommendation_engine(
        beginner=beginner,
        initial_value=settings["initial_value"],
        key_prefix="overview_rec_advanced",
    )

    # ── Advanced sections ─────────────────────────────────────────
    advanced_label = "Optional: benchmarks & advanced charts" if beginner else "Benchmarks & advanced analytics"

    with st.expander(advanced_label, expanded=not beginner):
        if beginner:
            st.caption("These tools are useful once you're comfortable with the basics.")

        from components.benchmark_comparison_panel import render_benchmark_alternative_comparison

        render_benchmark_alternative_comparison(
            returns=returns,
            weights=weights,
            tickers=tickers,
            settings=settings,
            load_comparison_prices=load_comparison_prices,
            compute_daily_returns=compute_daily_returns,
            key_prefix="overview_benchmark_alt",
            section_title="Benchmark & Alternative Comparison",
            as_expander=False,
        )

        if not beginner:
            section_header("Rolling Analytics", f"{core.ROLLING_WINDOW}-trading-day window (~3 months).")
            if st.button("Run Rolling Analytics", key="run_rolling_btn"):
                st.session_state.run_rolling = True
            if st.session_state.get("run_rolling", False):
                r1, r2 = st.columns(2)
                with r1:
                    st.plotly_chart(
                        charts.rolling_chart(
                            base_risk_pack["roll_ret"].to_frame("Rolling Return"),
                            "Rolling Annualized Return",
                            "Return",
                        ),
                        use_container_width=True,
                    )
                with r2:
                    st.plotly_chart(
                        charts.rolling_chart(
                            base_risk_pack["roll_vol"].to_frame("Rolling Volatility"),
                            "Rolling Volatility",
                            "Volatility",
                        ),
                        use_container_width=True,
                    )

def export_buttons(
    holdings_df: pd.DataFrame,
    metrics: core.ExtendedPortfolioMetrics,
    scenarios: pd.DataFrame,
    vol_rank: pd.DataFrame,
    risk_contrib: pd.DataFrame,
    report_text: str,
):
    buf = io.StringIO()
    holdings_df.to_csv(buf, index=False)
    st.sidebar.download_button("Holdings (CSV)", buf.getvalue(), "holdings.csv", "text/csv", use_container_width=True)

    summary_df = pd.DataFrame(
        [
            {"Metric": "Annual Return", "Value": metrics.annual_return},
            {"Metric": "Volatility", "Value": metrics.volatility},
            {"Metric": "Sharpe", "Value": metrics.sharpe_ratio},
            {"Metric": "Sortino", "Value": metrics.sortino_ratio},
            {"Metric": "CAGR", "Value": metrics.cagr},
            {"Metric": "Max Drawdown", "Value": metrics.max_drawdown},
            {"Metric": "Beta vs SPY", "Value": metrics.beta_spy},
        ]
    )
    b2 = io.StringIO()
    summary_df.to_csv(b2, index=False)
    st.sidebar.download_button("Metrics (CSV)", b2.getvalue(), "metrics.csv", "text/csv", use_container_width=True)

    b3 = io.StringIO()
    scenarios.to_csv(b3, index=False)
    st.sidebar.download_button("Scenarios (CSV)", b3.getvalue(), "scenarios.csv", "text/csv", use_container_width=True)

    st.sidebar.download_button(
        "Summary report (.txt)",
        report_text,
        "portfolio_report.txt",
        "text/plain",
        use_container_width=True,
    )


# ── Header ──────────────────────────────────────────────────────────────────────

pdemo.apply_pending_portfolio_demo(st)
if pp.is_demo_mode(st) and not pp.demo_applied(st, "portfolio"):
    pdemo.schedule_sample_portfolio_demo(st)

settings = render_sidebar()
beginner_mode = is_beginner_mode(settings)
try:
    from investment_ami_submit_runtime import process_investment_ami_submit_queue

    process_investment_ami_submit_queue(st)
except Exception as _ami_submit_queue_exc:
    st.session_state["_ami_submit_queue_error"] = repr(_ami_submit_queue_exc)
# Beginner live/cache seed must run before shared defaults fill empty keys,
# otherwise ensure_shared would mark all health_* present and skip live init.
if beginner_mode:
    ensure_beginner_macro_defaults()
ensure_shared_macro_session_defaults()
# Harvest before tab gates / workflow st.rerun so a post-select navigation run
# still copies `_w_*` → canonical `health_*` before Streamlit tears widgets down.
harvest_shared_macro_widgets_to_persist()
harvest_forward_horizon_widget_to_persist()
harvest_mc_horizon_widget_to_persist()
HELP = HELP_BEGINNER if beginner_mode else HELP_ADVANCED
render_branded_header(beginner_mode)
try:
    from investment_persistence_trace import render_main_startup_diagnostics

    render_main_startup_diagnostics(st, persistence_ok=_PERSISTENCE_OK)
except Exception:
    pass
health_badge_slot = st.empty()
init_holdings()
if _PERSISTENCE_OK:
    try:
        finalize_startup_holdings_restore(st)
    except Exception:
        pass
    try:
        finalize_init_holdings_defaults(st)
    except Exception:
        pass
apply_asset_preset(settings["asset_preset"])

_main_tab_labels = BEGINNER_TAB_LABELS if beginner_mode else ADVANCED_TAB_LABELS
try:
    from components.beginner_navigation import sync_beginner_goal_keys_from_portfolio

    sync_beginner_goal_keys_from_portfolio(st)
except Exception:
    pass
try:
    from components.workflow_navigator import apply_workflow_navigation
    from investment_workflow import (
        apply_pending_investment_tab,
        render_plan_context_banner,
        render_workflow_intent_banner,
    )

    apply_pending_investment_tab(st, _main_tab_labels, beginner_mode=beginner_mode)
    ensure_investment_active_tab(st, _main_tab_labels, beginner_mode=beginner_mode)
    if apply_workflow_navigation(
        st, beginner_mode=beginner_mode, tab_labels=_main_tab_labels
    ):
        st.rerun()
    render_plan_context_banner(st, beginner=beginner_mode)
    render_workflow_intent_banner(st, beginner=beginner_mode)
except ImportError:
    ensure_investment_active_tab(st, _main_tab_labels, beginner_mode=beginner_mode)
    st.radio(
        "Section",
        _main_tab_labels,
        key="investment_active_tab",
        horizontal=True,
        label_visibility="collapsed",
    )
    try:
        from investment_persistent_state import sync_investment_active_tab_after_widget

        sync_investment_active_tab_after_widget(st)
    except Exception:
        pass
_active_tab = st.session_state["investment_active_tab"]

from suite_analytical_question import render_suite_applied_math_insight

try:
    from applied_math_return_insight import (
        hydrate_applied_math_insight_for_session,
        investment_insight_main_render_needed,
        prepare_insight_card_widget_rerun,
        render_ami_insight_submit_feedback,
    )

    hydrate_applied_math_insight_for_session(st, "investment")
    prepare_insight_card_widget_rerun(st)
except Exception:
    investment_insight_main_render_needed = None  # type: ignore[misc, assignment]
    render_ami_insight_submit_feedback = None  # type: ignore[misc, assignment]

_insight_rendered = False
if investment_insight_main_render_needed and investment_insight_main_render_needed(st.session_state):
    _insight_rendered = bool(
        render_suite_applied_math_insight(st, source_app="investment", source_page=_active_tab)
    )
elif investment_insight_main_render_needed is None:
    _insight_rendered = bool(
        render_suite_applied_math_insight(st, source_app="investment", source_page=_active_tab)
    )

if (
    st.session_state.get("_ami_render_requested")
    and isinstance(st.session_state.get("_ami_pending_insight"), dict)
    and not _insight_rendered
):
    st.caption("⏳ Pending Applied Investment Insight — rendering on this page…")

if render_ami_insight_submit_feedback:
    render_ami_insight_submit_feedback(st, insight_rendered=_insight_rendered)

try:
    from investment_persistence_trace import render_ami_insight_lifecycle_runtime_diagnostics

    render_ami_insight_lifecycle_runtime_diagnostics(st)
except Exception:
    pass

try:
    from investment_persistence_trace import render_ami_reasoning_laboratory

    render_ami_reasoning_laboratory(st)
except Exception:
    pass

if active_main_tab(_active_tab, "getting_started", beginner=beginner_mode):
    if beginner_mode:
        _change_goal_mode = st.session_state.get("_workflow_intent") == "change_goal"
        render_beginner_goal_tab(change_goal_mode=_change_goal_mode)
        try:
            from investment_workflow import render_goal_change_workflow_debug

            render_goal_change_workflow_debug(
                st,
                beginner_mode=beginner_mode,
                tab_labels=_main_tab_labels,
                expanded=False,
            )
        except ImportError:
            pass
    else:
        section_header(
            "Getting Started Guide",
            f"Step-by-step tutorial. {APP_DISCLAIMER}",
        )
        render_getting_started_guide(beginner_mode=False)

if active_main_tab(_active_tab, "portfolio", beginner=beginner_mode):
    try:
        from investment_workflow import record_workflow_action

        record_workflow_action("open_portfolio", st)
    except ImportError:
        pass
    section_header(
        "Portfolio Inputs",
        "Enter fund tickers (like SPY) and what percent of your portfolio each one is." if beginner_mode
        else "Tickers and target weights. Normalized to 100% if needed.",
    )
    try:
        from components.portfolio_holdings_editor import render_portfolio_inputs_section

        edited = render_portfolio_inputs_section(
            st,
            beginner_mode=beginner_mode,
            apply_asset_preset=apply_asset_preset,
        )
        if edited is None:
            st.rerun()
    except ImportError:
        edited = st.data_editor(
            st.session_state.holdings_df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Ticker": st.column_config.TextColumn(help="Yahoo Finance symbol"),
                "Weight (%)": st.column_config.NumberColumn(min_value=0, max_value=100, format="%.1f"),
                "Asset Type": st.column_config.SelectboxColumn(
                    options=["Equity", "Bonds", "T-Bills", "REIT", "Dividend ETF", "Other"]
                ),
            },
            key="holdings_editor",
        )
        st.session_state.holdings_df = edited
    if not beginner_mode:
        try:
            import etf_holdings as eh
            from components.etf_holdings_explorer import render_etf_ticker_chip_bar

            render_etf_ticker_chip_bar([t for t, _ in eh.portfolio_etf_tickers(edited)], key_prefix="inputs_etf")
        except ImportError:
            pass
    try:
        from investment_workflow import track_holdings_dataframe

        track_holdings_dataframe(edited, st)
    except ImportError:
        pass
    try:
        from investment_activity import log_holdings_updated

        _h_fp = _holdings_fingerprint(edited)
        if st.session_state.get("_activity_holdings_fp") != _h_fp:
            if st.session_state.get("_activity_holdings_fp") is not None:
                _clean = edited.dropna(subset=["Ticker"]).copy()
                _tickers = [
                    str(t).strip().upper()
                    for t in _clean["Ticker"]
                    if str(t).strip()
                ]
                log_holdings_updated(st, tickers=_tickers)
            st.session_state["_activity_holdings_fp"] = _h_fp
    except Exception:
        pass
    ws = edited["Weight (%)"].fillna(0).sum()
    if abs(ws - 100) > 0.5:
        st.warning(f"Weights sum to **{ws:.1f}%** — auto-normalized in calculations.")
    try:
        from components.beginner_navigation import mark_portfolio_built, _holdings_fingerprint

        _fp = _holdings_fingerprint(edited)
        _confirmed_fp = st.session_state.get("_portfolio_confirmed_fp")
        if bool(st.session_state.get("portfolio_built")) and _confirmed_fp == _fp:
            st.success("Portfolio confirmed — step complete.")
        confirm_label = "Use this portfolio" if beginner_mode else "Confirm portfolio"
        if st.button(
            confirm_label,
            type="primary",
            use_container_width=True,
            key="confirm_portfolio_holdings",
        ):
            mark_portfolio_built(st, holdings_df=edited)
            try:
                from investment_activity import log_portfolio_created

                log_portfolio_created(st, holdings_count=len(edited.dropna(subset=["Ticker"])))
            except Exception:
                pass
            st.rerun()
        if not beginner_mode:
            st.caption(
                f"Click **Confirm portfolio** when weights look right, then run **{RUN_PORTFOLIO_ANALYSIS_LABEL}**."
            )
    except ImportError:
        pass
    if beginner_mode:
        st.caption("Scroll down for investment planning and implementation guides.")

try:
    tickers, weights, asset_types = parse_holdings(st.session_state.holdings_df)
    try:
        from investment_workflow import (
            needs_analytics_load,
            record_workflow_health_status,
            reconcile_workflow_health,
            track_holdings_dataframe,
        )

        track_holdings_dataframe(st.session_state.holdings_df, st)
    except ImportError:
        needs_analytics_load = lambda *_a, **_k: True  # type: ignore[misc, assignment]
except ValueError as e:
    st.error(str(e))
    if _PERSISTENCE_OK:
        autosave_investment_state(st)
    st.stop()

_analytics_ready = False
prices = returns = mean_rets = cov = metrics = growth = bench_rets = None
base_risk_pack = None
insights: list[str] = []
explanation = None
report_text = ""
holdings_df = None
mc_summary = st.session_state.get("mc_cached_summary")

try:
    _load_analytics = needs_analytics_load(_active_tab, _main_tab_labels, st)
except NameError:
    _load_analytics = True

_capture_fp = None
if pp.skip_heavy_work(st):
    _capture_fp = pp.capture_analytics_fingerprint(
        tickers, weights, settings["start"], settings["end"], _active_tab
    )
if pp.skip_heavy_work(st) and _load_analytics and _capture_fp is not None:
    _cached_bundle = pp.restore_capture_analytics(st, _capture_fp)
    if _cached_bundle:
        prices = _cached_bundle["prices"]
        returns = _cached_bundle["returns"]
        metrics = _cached_bundle["metrics"]
        growth = _cached_bundle["growth"]
        bench_rets = _cached_bundle.get("bench_rets")
        holdings_df = _cached_bundle["holdings_df"]
        base_risk_pack = _cached_bundle["base_risk_pack"]
        insights = _cached_bundle.get("insights") or []
        explanation = _cached_bundle.get("explanation")
        report_text = _cached_bundle.get("report_text") or ""
        # Re-align μ/Σ to holdings order (cached bundles may predate this fix).
        _ticker_labels = [str(t).strip().upper() for t in tickers]
        mean_rets, cov, returns = core.annualized_mean_and_cov(
            returns, _ticker_labels, weights
        )
        st.session_state.plan_compare_return = metrics.annual_return
        export_buttons(
            holdings_df,
            metrics,
            base_risk_pack["scenarios"],
            base_risk_pack["vol_rank"],
            base_risk_pack["risk_contrib"],
            report_text,
        )
        _analytics_ready = True
        _load_analytics = False
        if store_forward_engine_inputs is not None:
            store_forward_engine_inputs(
                st.session_state,
                metrics=metrics,
                mean_returns=mean_rets,
                cov=cov.values if hasattr(cov, "values") else cov,
                tickers=tickers,
                weights=weights,
                asset_types=asset_types,
                start=settings["start"],
                end=settings["end"],
                initial_value=settings["initial_value"],
                risk_free_rate=settings["risk_free"],
            )

if _load_analytics:
    try:
        from investment_workflow import reconcile_workflow_health

        reconcile_workflow_health(tickers, weights, st)
        sync_workflow_health_status(tickers, weights)
    except ImportError:
        pass
    with st.spinner("Loading market data and running analytics…"):
        try:
            prices = load_market_data(tuple(tickers), settings["start"], settings["end"])
            bench_rets = load_benchmark_returns(settings["start"], settings["end"])
            returns = compute_daily_returns(prices)
            ticker_labels = [str(t).strip().upper() for t in tickers]
            # μ/Σ must match holdings ticker order (Yahoo columns are often A–Z).
            mean_rets, cov, returns = core.annualized_mean_and_cov(
                returns, ticker_labels, weights
            )
            metrics = core.compute_extended_metrics(
                returns,
                weights,
                settings["risk_free"],
                settings["initial_value"],
                benchmark_rets=bench_rets,
                tickers=ticker_labels,
            )
            growth = core.portfolio_growth_series(
                returns, weights, settings["initial_value"], tickers=ticker_labels
            )
            st.session_state.plan_compare_return = metrics.annual_return
        except Exception as ex:
            st.error(f"Analysis failed: {ex}")
            try:
                from investment_market_data import MarketDataFetchError, get_market_data_diagnostics

                if isinstance(ex, MarketDataFetchError):
                    last = get_market_data_diagnostics().last_fetch or {}
                    if last:
                        st.caption(
                            "Market-data diagnostics: "
                            f"symbols={last.get('symbols')}, start={last.get('start')}, "
                            f"end={last.get('end')}, attempts={last.get('attempts')}, "
                            f"shape={last.get('response_shape')}"
                        )
            except Exception:
                pass
            if _PERSISTENCE_OK:
                autosave_investment_state(st)
            st.stop()

    latest = prices.iloc[-1]
    holdings_df = core.holdings_breakdown(tickers, weights, asset_types, settings["initial_value"], latest)
    base_risk_pack = compute_risk_pack(
        returns,
        tuple(weights.tolist()),
        settings["initial_value"],
        tickers_tuple=tuple(str(t).strip().upper() for t in tickers),
    )
    insights = core.generate_portfolio_insights(
        tickers,
        weights,
        asset_types,
        metrics,
        base_risk_pack["corr"],
        base_risk_pack["risk_contrib"],
    )
    explanation = core.generate_portfolio_explanation(
        tickers, weights, asset_types, metrics, base_risk_pack["corr"], base_risk_pack["risk_contrib"], benchmark_rets=bench_rets
    )
    report_text = core.build_summary_report(
        tickers, weights, metrics, mc_summary, insights, settings
    )
    export_buttons(
        holdings_df,
        metrics,
        base_risk_pack["scenarios"],
        base_risk_pack["vol_rank"],
        base_risk_pack["risk_contrib"],
        report_text,
    )
    _analytics_ready = True
    if store_forward_engine_inputs is not None and mean_rets is not None and cov is not None and metrics is not None:
        store_forward_engine_inputs(
            st.session_state,
            metrics=metrics,
            mean_returns=mean_rets,
            cov=cov.values if hasattr(cov, "values") else cov,
            tickers=tickers,
            weights=weights,
            asset_types=asset_types,
            start=settings["start"],
            end=settings["end"],
            initial_value=settings["initial_value"],
            risk_free_rate=settings["risk_free"],
        )
    if pp.skip_heavy_work(st) and _capture_fp is not None:
        pp.store_capture_analytics(
            st,
            _capture_fp,
            prices=prices,
            returns=returns,
            mean_rets=mean_rets,
            cov=cov,
            metrics=metrics,
            growth=growth,
            bench_rets=bench_rets,
            holdings_df=holdings_df,
            base_risk_pack=base_risk_pack,
            insights=insights,
            explanation=explanation,
            report_text=report_text,
        )
else:
    try:
        from investment_workflow import reconcile_workflow_health

        reconcile_workflow_health(tickers, weights, st)
        sync_workflow_health_status(tickers, weights)
    except ImportError:
        pass


def _require_analytics(feature: str) -> bool:
    if _analytics_ready:
        return True
    st.info(
        f"**{feature}** needs market data. You're on a quick-edit screen — "
        "open **Analysis**, **Overview**, or **Health** (or run **Analyze Portfolio**) to load analytics."
    )
    return False

if active_main_tab(_active_tab, "portfolio", beginner=beginner_mode):
    try:
        from investment_workflow import render_rebuild_portfolio_panel

        if render_rebuild_portfolio_panel(st, beginner=beginner_mode):
            st.rerun()
    except ImportError:
        pass
    st.markdown("---")
    pv = float(settings["initial_value"])
    if beginner_mode:
        from components.investment_planning import BEGINNER_PLAN_INPUT_TABS

        chosen_input = st.radio(
            "Portfolio input section",
            BEGINNER_PLAN_INPUT_TABS,
            horizontal=True,
            key="beginner_plan_input_tab",
            label_visibility="collapsed",
        )
        if chosen_input == BEGINNER_PLAN_INPUT_TABS[0]:
            render_how_much_to_invest(
                settings, tickers=tickers, weights=weights, key_prefix="invest_plan_beginner"
            )
        elif chosen_input == BEGINNER_PLAN_INPUT_TABS[1]:
            from components.ui_helpers import format_money_cents, holding_dollar_from_weight

            alloc_preview = st.session_state.holdings_df.copy()
            weights = alloc_preview["Weight (%)"].fillna(0).astype(float)
            alloc_preview["Value ($)"] = [
                format_money_cents(holding_dollar_from_weight(pv, w))
                for w in weights
            ]
            st.caption(f"Dollar amounts use portfolio value **{_money(pv)}** from the sidebar.")
            st.dataframe(alloc_preview, use_container_width=True, hide_index=True)
        else:
            render_implementation_guide(
                tickers=tickers,
                weights=weights,
                asset_types=asset_types,
                settings=settings,
                health=st.session_state.get("health_result"),
                key_prefix="inputs_impl",
            )
    else:
        render_how_much_to_invest(
            settings, tickers=tickers, weights=weights, key_prefix="invest_plan_advanced"
        )
        st.markdown("#### Dollar amounts (based on portfolio value)")
        from components.ui_helpers import format_money_cents, holding_dollar_from_weight

        alloc_preview = st.session_state.holdings_df.copy()
        weights = alloc_preview["Weight (%)"].fillna(0).astype(float)
        alloc_preview["Value ($)"] = [
            format_money_cents(holding_dollar_from_weight(pv, w))
            for w in weights
        ]
        st.caption(
            f"Each row: portfolio value × weight (e.g. {_money(pv)} × 60% = "
            f"{format_money_cents(holding_dollar_from_weight(pv, 60.0))})."
        )
        st.dataframe(alloc_preview, use_container_width=True, hide_index=True)
        st.markdown("---")
        render_implementation_guide(
            tickers=tickers,
            weights=weights,
            asset_types=asset_types,
            settings=settings,
            health=st.session_state.get("health_result"),
            key_prefix="inputs_impl_adv",
        )
    try:
        from components.ui_helpers import apply_pending_scroll_to_target

        apply_pending_scroll_to_target(st)
    except ImportError:
        pass

# ── Explain This Portfolio ─────────────────────────────────────────────────────

if active_main_tab(_active_tab, "explain", beginner=beginner_mode) and _require_analytics("Explain This Portfolio"):
    if beginner_mode:
        st.session_state.visited_explain = True
    section_header(
        "Explain This Portfolio",
        "A plain-English summary of your portfolio — strengths, weaknesses, and ideas." if beginner_mode
        else (
            "Rule-based investment memo from allocation, historical risk metrics, and macro sensitivity "
            f"— not an LLM and not a forecast. {APP_DISCLAIMER}"
        ),
    )
    st.markdown("##### Portfolio Overview")
    for item in explanation.portfolio_overview:
        st.markdown(f"- {item}")
    st.markdown("##### Risk Analysis")
    for item in explanation.risk_analysis:
        st.markdown(f"- {item}")
    st.markdown("##### Macro Sensitivity")
    for item in explanation.macro_sensitivity:
        st.markdown(f"- {item}")
    st.markdown("##### Investor Suitability")
    for item in explanation.investor_suitability:
        st.markdown(f"- {item}")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Strengths")
        for item in explanation.strengths:
            st.markdown(f"- {item}")
    with c2:
        st.markdown("##### Weaknesses")
        for item in explanation.weaknesses:
            st.markdown(f"- {item}")
    st.markdown("##### Suggested Improvements")
    for item in explanation.suggested_improvements:
        st.markdown(f"- {item}")

    st.download_button(
        "Download Investment Memo (.txt)",
        explanation.full_memo,
        "portfolio_investment_memo.txt",
        "text/plain",
        use_container_width=False,
    )

# ── Risk Analysis ─────────────────────────────────────────────────────────────

if active_main_tab(_active_tab, "analytics", beginner=beginner_mode) and _require_analytics("Analyze Portfolio"):
    st.session_state.visited_risk = True
    if pp.is_demo_mode(st) or pp.is_screenshot_mode(st):
        pdemo.render_sample_portfolio_button(st)
    pp.render_executive_summary(
        st,
        "Analyzes portfolio risk, return, and diversification using live Yahoo Finance data.",
        "Translates quantitative metrics into actionable allocation insights for decision support.",
        "Sharpe/Sortino ratios, volatility, drawdown, correlation heatmap, and rolling performance charts.",
    )
    if beginner_mode:
        section_header("Portfolio Analysis", "Score your holdings in one click.")
        render_historical_metrics_banner()
        try:
            from components.workflow_actions import render_analysis_workflow_cta

            if render_analysis_workflow_cta(st, key="beg_analyze", beginner=True):
                try:
                    from investment_workflow import request_core_step_navigation

                    request_core_step_navigation("analyze", beginner=True, st_obj=st)
                except ImportError:
                    pass
        except ImportError:
            if st.button(RUN_PORTFOLIO_ANALYSIS_LABEL, type="primary", key="beg_analyze", use_container_width=True):
                st.session_state.run_health = True
                st.session_state.health_refresh = st.session_state.get("health_refresh", 0) + 1
        _beg_health = evaluate_portfolio_health_if_needed(
            settings=settings,
            tickers=tickers,
            weights=weights,
            asset_types=asset_types,
            metrics=metrics,
            returns=returns,
            mean_rets=mean_rets,
            cov=cov,
            base_risk_pack=base_risk_pack,
            bench_rets=bench_rets,
        )
        if _beg_health is None and st.session_state.get("run_health"):
            st.warning("Analysis did not complete. Check holdings and try again.")
        elif _beg_health is not None:
            render_beginner_analyze_results(
                _beg_health,
                objective=st.session_state.get("health_objective", "balanced growth"),
            )
            sync_workflow_health_status(tickers, weights)
            st.success("Analysis complete. Open **⑤ Portfolio Health** and click **Review Portfolio Health**.")
            if st.session_state.pop("_workflow_analysis_just_completed", False):
                st.rerun()
        else:
            pp.render_professional_empty(
                st,
                f"Configure your holdings on the Portfolio Inputs tab, then click "
                f"**{RUN_PORTFOLIO_ANALYSIS_LABEL}** to generate risk metrics, "
                "correlation analysis, and performance charts.",
                title=RUN_PORTFOLIO_ANALYSIS_LABEL,
            )
        try:
            from investment_workflow import render_rebuild_portfolio_panel

            if render_rebuild_portfolio_panel(st, beginner=True):
                st.rerun()
        except ImportError:
            pass
        st.caption("Tabs **⑦–⑩** are optional. Advanced Mode has full risk charts.")
    else:
        section_header(
            "Portfolio Analysis",
            f"Workflow step — use **{RUN_PORTFOLIO_ANALYSIS_LABEL}** before the optional risk charts below.",
        )
        render_historical_metrics_banner()
        try:
            from components.workflow_actions import render_analysis_workflow_cta

            if render_analysis_workflow_cta(st, key="adv_workflow_analyze", beginner=False):
                pass
        except ImportError:
            if st.button(RUN_PORTFOLIO_ANALYSIS_LABEL, type="primary", key="adv_workflow_analyze"):
                st.session_state.run_health = True
                st.session_state.health_refresh = st.session_state.get("health_refresh", 0) + 1
        _adv_workflow_health = evaluate_portfolio_health_if_needed(
            settings=settings,
            tickers=tickers,
            weights=weights,
            asset_types=asset_types,
            metrics=metrics,
            returns=returns,
            mean_rets=mean_rets,
            cov=cov,
            base_risk_pack=base_risk_pack,
            bench_rets=bench_rets,
        )
        if _adv_workflow_health is not None:
            sync_workflow_health_status(tickers, weights)
            c_s, c_d = st.columns([1, 2])
            with c_s:
                st.metric("Health Score", f"{_adv_workflow_health.score:.0f}/100")
            with c_d:
                st.caption(_adv_workflow_health.status_message)
            if st.session_state.pop("_workflow_analysis_just_completed", False):
                st.rerun()
        st.markdown("---")
        section_header(
            "Risk & Macro Tools (optional)",
            "Deep-dive charts — not required for the Analysis workflow step.",
        )
        if st.button("Run Risk & Macro Analysis", key="run_risk_macro_btn"):
            st.session_state.run_risk_macro = True
        if not st.session_state.get("run_risk_macro", False):
            st.caption("Run this section on demand to reduce startup time.")
        else:
            section_header("Correlation Matrix", HELP["correlation"])
            st.plotly_chart(charts.correlation_heatmap(base_risk_pack["corr"]), use_container_width=True)

            section_header("Volatility Ranking", "Annualized volatility by holding (highest first).")
            vr = base_risk_pack["vol_rank"].copy()
            vr["Annual Volatility"] = vr["Annual Volatility"].map(_pct)
            st.dataframe(vr, use_container_width=True, hide_index=True)

            section_header("Risk Contribution", "Share of total portfolio risk from each asset.")
            rc = base_risk_pack["risk_contrib"].copy()
            rc["Weight"] = rc["Weight"].map(_pct)
            rc["Risk Contribution (%)"] = rc["Risk Contribution (%)"].map(lambda x: f"{x:.1f}%")
            st.dataframe(rc.drop(columns=["Risk Contribution"]), use_container_width=True, hide_index=True)

            section_header("Scenario Analysis", "Hypothetical 1-year outcomes under return shocks.")
            st.caption(
                "One-period what-if shocks on the **current static-weight portfolio** "
                "(not Guided targets, not multi-year Monte Carlo). "
                "Stagflation-like is a −5% return assumption only — not a separate vol shock."
            )
            sd = base_risk_pack["scenarios"].copy()
            sd["Assumed 1Y Return"] = sd["Assumed 1Y Return"].map(_pct)
            sd["Projected Value"] = sd["Projected Value"].map(_money)
            sd["Gain / Loss ($)"] = sd["Gain / Loss ($)"].map(
                lambda x: f"+{_money(x)}" if x >= 0 else f"-{_money(abs(x))}"
            )
            st.dataframe(sd, use_container_width=True, hide_index=True)

            section_header(
                "Macro Regime Engine",
                "Adjusted return, volatility, Sharpe, and projection under major macro scenarios.",
            )
            if st.button("Run Macro Regime Analysis", key="run_macro_regime_btn"):
                st.session_state.run_macro_regime = True
            if st.session_state.get("run_macro_regime", False):
                macro_df = core.macro_regime_analysis(
                    metrics, settings["initial_value"], years=1, weights=weights, asset_types=asset_types
                )
                regime_choice = st.selectbox("Select macro regime", macro_df["Regime"].tolist(), index=0)
                regime_row = macro_df[macro_df["Regime"] == regime_choice].iloc[0]
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Adjusted Return", _pct(float(regime_row["Adjusted Return"])))
                c2.metric("Adjusted Volatility", _pct(float(regime_row["Adjusted Volatility"])))
                c3.metric("Adjusted Sharpe", f"{float(regime_row['Adjusted Sharpe']):.2f}")
                c4.metric("Adjusted Projected Value", _money(float(regime_row["Adjusted Projected Value"])))

                md = macro_df.copy()
                md["Adjusted Return"] = md["Adjusted Return"].map(_pct)
                md["Adjusted Volatility"] = md["Adjusted Volatility"].map(_pct)
                md["Adjusted Sharpe"] = md["Adjusted Sharpe"].map(lambda x: f"{x:.2f}")
                md["Adjusted Projected Value"] = md["Adjusted Projected Value"].map(_money)
                st.dataframe(md, use_container_width=True, hide_index=True)
            else:
                st.caption("Macro regime analysis runs only when requested.")

        from components.benchmark_comparison_panel import render_benchmark_alternative_comparison

        render_benchmark_alternative_comparison(
            returns=returns,
            weights=weights,
            tickers=tickers,
            settings=settings,
            load_comparison_prices=load_comparison_prices,
            compute_daily_returns=compute_daily_returns,
            key_prefix="analytics_benchmark_alt",
            section_title="Benchmark & Alternative Comparison",
            as_expander=False,
        )

# ── Portfolio Health ──────────────────────────────────────────────────────────

if active_main_tab(_active_tab, "health", beginner=beginner_mode) and _require_analytics("Portfolio Health"):
    from components.beginner_navigation import (
        HEALTH_SUBTAB_LABELS,
        RECOMMENDATIONS_HEALTH_SUBTAB,
        RECOMMENDATIONS_SCROLL_ANCHOR,
    )

    _pending_rec_focus = (
        st.session_state.get("_pending_scroll_target") == RECOMMENDATIONS_SCROLL_ANCHOR
        or st.session_state.get("_force_open_recommendations")
    )
    _health_prev_main = st.session_state.get("_health_section_prev_main_tab")
    if _health_prev_main != _active_tab:
        if _pending_rec_focus:
            if beginner_mode:
                st.session_state["health_subtab"] = RECOMMENDATIONS_HEALTH_SUBTAB
        else:
            if beginner_mode:
                st.session_state["health_subtab"] = HEALTH_SUBTAB_LABELS[0]
            st.session_state.pop("_force_open_recommendations", None)
    st.session_state["_health_section_prev_main_tab"] = _active_tab

    _health_debug_loaded = False
    section_header(
        "Portfolio Health",
        "Your portfolio checkup — what's working, what to watch, and ideas to consider." if beginner_mode
        else f"Model-based evaluation of performance, risk, drift, and macro fit. {APP_DISCLAIMER}",
    )
    if beginner_mode:
        st.caption("**Step 4:** Review your score, then click **Review Portfolio Health** to mark this step done.")
        render_macro_assumptions_guide(expanded=False)
    render_historical_metrics_banner()
    if st.button("Refresh Portfolio Health", key="refresh_health_btn", type="secondary"):
        st.session_state.health_refresh = st.session_state.get("health_refresh", 0) + 1
        st.session_state.run_health = True

    health_status = get_health_cache_status(tickers, weights)
    if health_status == "settings_stale" and st.session_state.get("run_health"):
        st.warning(
            "⚠️ **Objective, macro, or historical lookback settings changed** since the last health run. "
            "Analysis will refresh automatically below."
        )

    render_macro_assumptions_banner()
    macro_expander = st.expander("Macro & objective settings", expanded=not beginner_mode)
    with macro_expander:
        render_shared_macro_assumption_controls()
        health_objective = st.selectbox(
            "Portfolio Objective (alignment check)",
            [
                "balanced growth",
                "capital preservation",
                "aggressive growth",
                "income",
                "retirement",
                "short-term cash management",
            ],
            index=0,
            key="health_objective",
        )
        hc1, hc2 = st.columns(2)
        with hc1:
            health_bond_min = st.slider("Minimum bond/cash constraint (%)", 0, 80, 0, 5, key="health_bond_min")
        with hc2:
            health_run_optimizer = st.checkbox(
                "Include optimizer allocation in drift analysis",
                value=not beginner_mode,
                key="health_run_optimizer",
                help=(
                    "Adds a historical long-only mean-variance (Max Sharpe) column for comparison only. "
                    "It is not the Guided recommendation and may corner on a single asset (e.g. 100% BND)."
                ),
            )

    if beginner_mode:
        suggested_preset = OBJECTIVE_TO_PRESET.get(st.session_state.get("health_objective", "balanced growth"))
        if suggested_preset:
            st.caption(
                f"Suggested portfolio for your objective: **{suggested_preset}** — "
                f"{PRESET_RATIONALE.get(suggested_preset, '')}"
            )
            if st.button(
                f"Load {suggested_preset} portfolio for this goal",
                key="health_load_objective_preset",
                use_container_width=False,
            ):
                try:
                    from investment_workflow import invalidate_workflow_from

                    invalidate_workflow_from("portfolio")
                except ImportError:
                    st.session_state.run_health = False
                    st.session_state.pop("health_result", None)
                    st.session_state.pop("health_result_fingerprint", None)
                st.session_state.holdings_df = pd.DataFrame(core.PORTFOLIO_PRESETS[suggested_preset])
                st.session_state.preset_applied = suggested_preset
                st.session_state.guide_portfolio_loaded = False
                st.session_state.portfolio_built = False
                try:
                    from investment_activity import log_portfolio_created

                    log_portfolio_created(
                        st,
                        preset=suggested_preset,
                        holdings_count=len(st.session_state.holdings_df),
                    )
                except Exception:
                    pass
                st.rerun()

    health_objective = str(st.session_state.get("health_objective", "balanced growth"))
    _prev_obj = st.session_state.get("_activity_health_objective")
    if _prev_obj and _prev_obj != health_objective:
        try:
            from investment_workflow import invalidate_workflow_from

            invalidate_workflow_from("analysis")
        except ImportError:
            pass
        try:
            from investment_activity import log_risk_profile_changed

            log_risk_profile_changed(st, profile=health_objective)
        except Exception:
            pass
    st.session_state["_activity_health_objective"] = health_objective

    sync_workflow_health_status(tickers, weights)
    health: core.PortfolioHealthResult | None = get_cached_health(tickers, weights)
    cache_status = get_health_cache_status(tickers, weights)
    if health is None and cache_status == "fresh":
        health = st.session_state.get("health_result")
    if not st.session_state.get("run_health", False):
        if health is None:
            if cache_status == "settings_stale":
                st.warning(
                    "Macro or objective settings changed since your last analysis. "
                    "Click **Refresh Portfolio Health** to update the score for your current settings."
                )
            elif bool(st.session_state.get("portfolio_analyzed")):
                st.warning(
                    "Analysis was run, but the health cache is not available for this portfolio. "
                    "Click **Refresh Portfolio Health** below."
                )
            else:
                st.info(
                    f"Run **{RUN_PORTFOLIO_ANALYSIS_LABEL}** on the Analysis tab first, "
                    "or click **Refresh Portfolio Health** below."
                )
    else:
        health = evaluate_portfolio_health_if_needed(
            settings=settings,
            tickers=tickers,
            weights=weights,
            asset_types=asset_types,
            metrics=metrics,
            returns=returns,
            mean_rets=mean_rets,
            cov=cov,
            base_risk_pack=base_risk_pack,
            bench_rets=bench_rets,
        )
        sync_workflow_health_status(tickers, weights)
        if st.session_state.pop("_workflow_analysis_just_completed", False):
            st.rerun()

    if health is None:
        try:
            from components.workflow_actions import render_health_review_action

            render_health_review_action(
                st,
                tickers,
                weights,
                key="health_review_workflow_btn",
                health_loaded=False,
                beginner=beginner_mode,
            )
        except ImportError:
            pass

    if health is not None:
        _health_debug_loaded = True
        sync_workflow_health_status(tickers, weights)

        st.markdown(
            f'<div class="insight-card">📋 <b>Status:</b> {health.status_message}</div>',
            unsafe_allow_html=True,
        )
        try:
            from components.workflow_actions import render_health_review_action

            if render_health_review_action(
                st,
                tickers,
                weights,
                key="health_review_workflow_btn",
                health_loaded=True,
                beginner=beginner_mode,
            ):
                st.rerun()
        except ImportError:
            pass

        if beginner_mode:
            from components.beginner_navigation import HEALTH_SUBTAB_LABELS
            from investment_persistent_state import validate_state_option

            _health_subtab_labels = list(HEALTH_SUBTAB_LABELS)
            validate_state_option(
                st, "health_subtab", _health_subtab_labels, _health_subtab_labels[0]
            )
            _active_health_sub = st.radio(
                "Health section",
                _health_subtab_labels,
                key="health_subtab",
                horizontal=True,
                label_visibility="collapsed",
            )

            if _active_health_sub == _health_subtab_labels[0]:
                render_action_plan(
                    health.action_plan,
                    score=health.score,
                    objective=health_objective,
                    beginner=True,
                )
            elif _active_health_sub == _health_subtab_labels[1]:
                render_health_score_card(health)
            elif _active_health_sub == _health_subtab_labels[2]:
                wn1, wn2 = st.columns(2)
                with wn1:
                    st.markdown("**What's Working**")
                    for item in health.whats_working:
                        st.markdown(f'<div class="health-working">✓ {item}</div>', unsafe_allow_html=True)
                with wn2:
                    st.markdown("**What's Not Working**")
                    for item in health.whats_not_working:
                        st.markdown(f'<div class="health-not">⚠ {item}</div>', unsafe_allow_html=True)
            elif _active_health_sub == _health_subtab_labels[3]:
                render_recommendations_panel(health, settings)
                try:
                    from components.workflow_actions import render_recommendations_review_action

                    if render_recommendations_review_action(
                        st, key="beg_rec_review_btn", beginner=True
                    ):
                        st.rerun()
                except ImportError:
                    pass
            elif _active_health_sub == _health_subtab_labels[4]:
                render_rebalancing_panel(health, settings=settings, key_prefix="health_rebal")
                render_guided_portfolio_adjustment(
                    health,
                    tickers=tickers,
                    weights=weights,
                    asset_types=asset_types,
                    settings=settings,
                    metrics=metrics,
                    returns=returns,
                    assumptions=macro_assumptions_from_session(),
                    key_prefix="health_guided",
                )
            elif _active_health_sub == _health_subtab_labels[5]:
                st.caption("Optional charts — summary tabs above are enough for most checkups.")
                d1, d2 = st.columns(2)
                with d1:
                    st.plotly_chart(
                        charts.contribution_bar_chart(
                            health.return_contrib_df, "Return Contribution (%)", "Return by Asset",
                        ),
                        use_container_width=True,
                    )
                with d2:
                    st.plotly_chart(
                        charts.contribution_bar_chart(
                            health.risk_contrib_df, "Risk Contribution (%)", "Risk by Asset",
                        ),
                        use_container_width=True,
                    )
            try:
                from components.ui_helpers import apply_pending_scroll_to_target

                apply_pending_scroll_to_target(st)
            except ImportError:
                pass
            st.caption(
                f"Implementation guide: **💼 Portfolio Inputs** → **Implementation Guide** tab. {APP_DISCLAIMER}"
            )
        else:
            section_header(
                "Portfolio Journey / Action Plan",
                "Decision-support timeline from Portfolio Health.",
            )
            render_action_plan(
                health.action_plan,
                score=health.score,
                objective=health_objective,
                beginner=False,
            )

            section_header(
                "Portfolio Health Score",
                "Core Health = objective fit + construction + risk appropriateness + policy-relative delivery (100 pts).",
            )
            sc1, sc2 = st.columns([1, 2])
            with sc1:
                render_health_score_card(health)
            with sc2:
                pillar_rows = []
                for name, pts in health.score_breakdown.items():
                    mx = float(core.HEALTH_CORE_PILLAR_MAX.get(name, 0.0))
                    pillar_rows.append(
                        {
                            "Pillar": name,
                            "Points": round(float(pts), 2),
                            "Max": int(mx),
                        }
                    )
                st.dataframe(pd.DataFrame(pillar_rows), use_container_width=True, hide_index=True)
                for name, expl in (getattr(health, "pillar_explanations", None) or {}).items():
                    st.caption(expl)
                subs = getattr(health, "construction_subscores", None) or {}
                if subs:
                    st.caption(
                        "Construction split — "
                        f"Diversification {subs.get('Diversification', 0):.1f}/15 · "
                        f"Concentration {subs.get('Concentration', 0):.1f}/15."
                    )

            diag = getattr(health, "health_diagnostics", None) or {}
            section_header(
                "Health diagnostics (not part of the 100)",
                "Risk-adjusted ratios, drawdown, and correlations remain visible as analytics.",
            )
            st.caption(f"Runtime provenance: `{core.health_runtime_provenance()}`")
            dcols = st.columns(4)
            with dcols[0]:
                st.metric(
                    "Raw Sharpe",
                    f"{float(diag.get('portfolio_sharpe', diag.get('raw_sharpe', metrics.sharpe_ratio))):.3f}",
                )
                st.metric("Sortino", f"{float(diag.get('sortino', metrics.sortino_ratio)):.3f}")
            with dcols[1]:
                # Always rebuild from unambiguous float keys — never trust a cached display string.
                sharpe_vs = render_sharpe_vs_policy_metric(diag)
                st.metric("Sharpe vs policy", sharpe_vs)
                pol_bench = diag.get("policy_benchmark_sharpe", diag.get("policy_sharpe"))
                if pol_bench is not None and np.isfinite(float(pol_bench)):
                    st.caption(
                        "Left = **portfolio Sharpe**; right = **policy-benchmark Sharpe** "
                        f"({float(pol_bench):.3f}). "
                        "Built from portfolio_sharpe / policy_benchmark_sharpe only — not Sortino."
                    )
                else:
                    st.caption(
                        "Left = portfolio Sharpe; right = policy-benchmark Sharpe "
                        "(refresh Health if n/a)."
                    )
                st.metric(
                    "Ann. return",
                    f"{float(diag.get('annual_return', metrics.annual_return)) * 100:.2f}%",
                )
            with dcols[2]:
                st.metric(
                    "Ann. volatility",
                    f"{float(diag.get('annual_volatility', metrics.volatility)) * 100:.2f}%",
                )
                pol_vol = diag.get("policy_volatility")
                st.metric(
                    "Policy volatility",
                    f"{float(pol_vol) * 100:.2f}%" if pol_vol is not None and np.isfinite(float(pol_vol)) else "n/a",
                )
            with dcols[3]:
                st.metric(
                    "Max drawdown",
                    f"{float(diag.get('max_drawdown', metrics.max_drawdown)) * 100:.2f}%",
                )
                st.metric(
                    "Max |pairwise corr|",
                    f"{float(getattr(health, 'max_pairwise_abs_corr', 0.0)):.2f}",
                )
            # Standalone policy Sharpe so a combined-string bug cannot hide the true value.
            pol_only = diag.get("policy_benchmark_sharpe", diag.get("policy_sharpe"))
            if pol_only is not None and np.isfinite(float(pol_only)):
                st.caption(
                    f"**Policy-benchmark Sharpe (standalone):** {float(pol_only):.3f} · "
                    f"**Portfolio Sharpe:** "
                    f"{float(diag.get('portfolio_sharpe', diag.get('raw_sharpe', 0))):.3f}."
                )
            pol_sort = diag.get("policy_sortino")
            if pol_sort is not None and np.isfinite(float(pol_sort)):
                st.caption(
                    f"Policy Sortino (diagnostic): **{float(pol_sort):.3f}** · "
                    f"Portfolio Sortino: **{float(diag.get('sortino', metrics.sortino_ratio)):.3f}**."
                )
            if getattr(health, "policy_benchmark_label", ""):
                st.caption(
                    f"**Policy benchmark:** {health.policy_benchmark_label}. "
                    f"{getattr(health, 'policy_benchmark_detail', '')}"
                )
            st.caption(
                "Sharpe and Sortino are diagnostics — they do **not** add points to Core Health."
            )

            section_header("What's Working / What's Not", "Plain summary of strengths and things to watch.")
            wn1, wn2 = st.columns(2)
            with wn1:
                st.markdown("**What's Working**")
                for item in health.whats_working:
                    st.markdown(f'<div class="health-working">✓ {item}</div>', unsafe_allow_html=True)
            with wn2:
                st.markdown("**What's Not Working**")
                for item in health.whats_not_working:
                    st.markdown(f'<div class="health-not">⚠ {item}</div>', unsafe_allow_html=True)

            _open_recommendations = bool(
                st.session_state.pop("_force_open_recommendations", False)
                or st.session_state.get("_pending_scroll_target") == RECOMMENDATIONS_SCROLL_ANCHOR
            )
            try:
                from components.ui_helpers import render_portfolio_recommendations_anchor

                render_portfolio_recommendations_anchor()
            except ImportError:
                pass
            with st.expander(
                "📋 Recommendations with model reasoning",
                expanded=_open_recommendations,
            ):
                st.caption("Issue, triggers, and tradeoffs for each model recommendation.")
                render_recommendations_panel(health, settings)
                try:
                    from components.workflow_actions import render_recommendations_review_action

                    if render_recommendations_review_action(
                        st, key="adv_rec_review_btn", beginner=False
                    ):
                        st.rerun()
                except ImportError:
                    pass
            try:
                from components.ui_helpers import apply_pending_scroll_to_target

                apply_pending_scroll_to_target(st)
            except ImportError:
                pass

            st.markdown("---")
            render_guided_portfolio_adjustment(
                health,
                tickers=tickers,
                weights=weights,
                asset_types=asset_types,
                settings=settings,
                metrics=metrics,
                returns=returns,
                assumptions=macro_assumptions_from_session(),
                key_prefix="health_guided",
            )

            section_header(
                "Rebalance guidance ($ and %)",
                "Current vs objective with dollar changes — educational, not financial advice.",
            )
            reb_disp = health.rebalance_df.copy()
            for col in ("Current ($)", "Objective ($)", "Recommended ($)", "Dollar Change ($)"):
                if col in reb_disp.columns:
                    reb_disp[col] = reb_disp[col].map(lambda x: _money(float(x)) if pd.notna(x) else "")
            st.dataframe(reb_disp, use_container_width=True, hide_index=True)

            section_header("Category allocation ($)", "Current vs objective by asset category.")
            cat_disp = health.allocation_compare_df.copy()
            for col in cat_disp.columns:
                if "($)" in col:
                    cat_disp[col] = cat_disp[col].map(lambda x: _money(float(x)) if pd.notna(x) else x)
            st.dataframe(cat_disp, use_container_width=True, hide_index=True)
            section_header(
                "Environment / Macro Check",
                "Near-term regime commentary from your assumptions — not part of Core Portfolio Health.",
            )
            macro_pts = float(getattr(health, "macro_check_score", 0.0))
            macro_max = float(getattr(health, "macro_check_max", 10.0))
            st.caption(f"**Check score:** {macro_pts:.1f}/{macro_max:.0f} (diagnostic only).")
            for note in health.macro_fit:
                st.markdown(f"- {note}")

            section_header("Visual Portfolio Diagnostics", "Return/risk contributions and allocation comparison.")
            d1, d2 = st.columns(2)
            with d1:
                st.plotly_chart(
                    charts.contribution_bar_chart(
                        health.return_contrib_df,
                        "Return Contribution (%)",
                        "Contribution to Return by Asset",
                    ),
                    use_container_width=True,
                )
            with d2:
                st.plotly_chart(
                    charts.contribution_bar_chart(
                        health.risk_contrib_df,
                        "Risk Contribution (%)",
                        "Contribution to Risk by Asset",
                    ),
                    use_container_width=True,
                )
            d3, d4 = st.columns(2)
            with d3:
                st.plotly_chart(
                    charts.contribution_bar_chart(
                        health.drawdown_contrib_df,
                        "Drawdown Contribution (%)",
                        "Drawdown Contribution by Asset",
                    ),
                    use_container_width=True,
                )
            with d4:
                st.plotly_chart(
                    charts.allocation_comparison_chart(health.allocation_compare_df),
                    use_container_width=True,
                )
                st.caption(
                    "**Current** = holdings · **Objective** = Guided category policy · "
                    "**Recommended** = planning-style category mix (not optimizer) · "
                    "**Optimizer** = Max-Sharpe experiment when enabled (else mirrors Current). "
                    "Guided Suggested % follows Objective, not Optimizer."
                )
                if "Optimizer (%)" in health.allocation_compare_df.columns:
                    st.caption(
                        "**Optimizer** (when shown) is a historical long-only mean-variance experiment — "
                        "not the primary Guided recommendation. Guided follows your stated category objective. "
                        "A 100% weight in one asset (e.g. BND) is a mathematical corner solution, not an "
                        "instruction to put the entire portfolio into that holding."
                    )
            d5, d6 = st.columns(2)
            with d5:
                st.plotly_chart(
                    charts.macro_sensitivity_heatmap(health.macro_heatmap_df),
                    use_container_width=True,
                )
            with d6:
                try:
                    cmp_prices = load_comparison_prices(settings["start"], settings["end"])
                    cmp_rets = compute_daily_returns(cmp_prices)
                    port_rets = base_risk_pack["port_rets"]
                    mini = charts.build_aligned_benchmark_growth(
                        port_rets,
                        cmp_rets,
                        float(settings["initial_value"]),
                        benchmark_symbols=("SPY", "QQQ"),
                    )
                    finite_ok = all(
                        col in mini.columns
                        and np.isfinite(pd.to_numeric(mini[col], errors="coerce")).any()
                        for col in ("Portfolio", "SPY", "QQQ")
                    )
                    if finite_ok:
                        st.plotly_chart(
                            charts.benchmark_mini_chart(
                                mini,
                                title="Portfolio vs SPY / QQQ (market reference)",
                            ),
                            use_container_width=True,
                        )
                        st.caption(
                            "Market-reference chart (SPY/QQQ), date-aligned with the portfolio series. "
                            "Not the Health policy benchmark (objective-weighted SPY/AGG/BIL)."
                        )
                    else:
                        mini_port = mini[["Date", "Portfolio"]] if "Portfolio" in mini.columns else None
                        if mini_port is not None and np.isfinite(
                            pd.to_numeric(mini_port["Portfolio"], errors="coerce")
                        ).any():
                            st.plotly_chart(
                                charts.benchmark_mini_chart(mini_port, title="Portfolio Growth"),
                                use_container_width=True,
                            )
                        else:
                            raise ValueError("aligned benchmark growth has no finite observations")
                except Exception:
                    mini = pd.DataFrame({"Date": growth.index, "Portfolio": growth.values})
                    st.plotly_chart(charts.benchmark_mini_chart(mini, title="Portfolio Growth"), use_container_width=True)

        st.caption(
            f"Portfolio Health outputs are rule-based and model-driven. {APP_DISCLAIMER} "
            "Refresh after changing tickers, weights, or macro settings."
        )

    try:
        from investment_workflow import render_health_workflow_debug

        render_health_workflow_debug(
            st,
            beginner_mode=beginner_mode,
            tickers=tickers,
            weights=weights,
            cache_status=cache_status,
            health_loaded=_health_debug_loaded,
        )
    except ImportError:
        pass

# ── Overview ──────────────────────────────────────────────────────────────────

if active_main_tab(_active_tab, "overview", beginner=beginner_mode) and _require_analytics("Overview"):
    if pp.is_demo_mode(st) or pp.is_screenshot_mode(st):
        pdemo.render_sample_portfolio_button(st)
    render_overview_tab(
        settings,
        metrics,
        holdings_df,
        growth,
        insights,
        explanation,
        returns,
        weights,
        tickers,
        asset_types,
        base_risk_pack,
    )

# ── Forward-Looking Macro Analysis ─────────────────────────────────────────────

if active_main_tab(_active_tab, "macro", beginner=beginner_mode) and _require_analytics("Macro Analysis"):
    if beginner_mode:
        section_header(
            "Macro Analysis",
            "How economic conditions affect your portfolio — explained in plain English.",
        )
        render_macro_assumptions_guide(expanded=True)
        st.info(
            "Switch to **Advanced Mode** in the sidebar to run forward-looking macro stress tests "
            "with numeric projections."
        )
    else:
        st.session_state.visited_forward = True
        if st.button("Run Forward-Looking Macro Analysis", key="run_forward_macro_btn"):
            st.session_state.run_forward_macro = True
            st.session_state.pop("_activity_forward_macro_logged", None)
    if not beginner_mode and st.session_state.get("run_forward_macro", False):
        section_header(
            "Forward-Looking Macro Analysis",
            f"Stress-test projections using shared macro settings (same as Portfolio Health, Monte Carlo, Optimizer). {APP_DISCLAIMER}",
        )
        st.info(
            f"**Current macro settings:** {macro_assumption_summary()}  \n"
            "Change inflation, rates, recession probability, and regime on the **Portfolio Health** tab."
        )
        recession_prob_pct = int(macro_assumptions_from_session().recession_probability * 100)

        st.markdown("##### Optional Forward Return Overrides")
        o1, o2, o3, o4 = st.columns(4)
        with o1:
            use_eq = st.checkbox("Override equity return", value=False)
            eq_ret = st.number_input("Expected equity return (%)", -20.0, 30.0, 8.0, 0.5) / 100.0
        with o2:
            use_bond = st.checkbox("Override bond return", value=False)
            bond_ret = st.number_input("Expected bond return (%)", -10.0, 20.0, 4.0, 0.5) / 100.0
        with o3:
            use_infl = st.checkbox("Override inflation", value=False)
            exp_infl = st.number_input("Expected inflation (%)", -2.0, 15.0, 2.5, 0.25) / 100.0
        with o4:
            use_vol = st.checkbox("Override volatility", value=False)
            exp_vol = st.number_input("Expected volatility (%)", 1.0, 60.0, max(1.0, metrics.volatility * 100), 0.5) / 100.0

        base_assumptions = macro_assumptions_from_session()
        assumptions = core.ForwardMacroAssumptions(
            rate_environment=base_assumptions.rate_environment,
            inflation=base_assumptions.inflation,
            recession_probability=base_assumptions.recession_probability,
            valuation=base_assumptions.valuation,
            economic_regime=base_assumptions.economic_regime,
            override_equity_return=eq_ret if use_eq else None,
            override_bond_return=bond_ret if use_bond else None,
            override_inflation=exp_infl if use_infl else None,
            override_volatility=exp_vol if use_vol else None,
        )
        fwd_years = render_forward_projection_horizon_slider()
        with st.spinner("Running forward-looking macro analysis..."):
            forward = core.compute_forward_projection_with_profile(
                metrics=metrics,
                mean_returns=mean_rets.copy(),
                cov=cov.values.copy(),
                tickers=tickers,
                weights=weights,
                asset_types=asset_types,
                assumptions=assumptions,
                initial_value=settings["initial_value"],
                years=float(fwd_years),
                risk_free_rate=settings["risk_free"],
            )
            # Cache for AMI / shared consumers. Fingerprint includes overrides when present
            # so AMI (no-override path) will recompute rather than reuse override results.
            st.session_state.forward_projection = forward
            if store_forward_engine_inputs is not None:
                store_forward_engine_inputs(
                    st.session_state,
                    metrics=metrics,
                    mean_returns=mean_rets,
                    cov=cov.values if hasattr(cov, "values") else cov,
                    tickers=tickers,
                    weights=weights,
                    asset_types=asset_types,
                    start=settings["start"],
                    end=settings["end"],
                    initial_value=settings["initial_value"],
                    risk_free_rate=settings["risk_free"],
                )
            if build_canonical_forward_fingerprint is not None:
                st.session_state.forward_projection_fp = build_canonical_forward_fingerprint(
                    assumptions,
                    start=settings["start"],
                    end=settings["end"],
                    years=float(fwd_years),
                    tickers=tickers,
                    weights=weights,
                    risk_free_rate=settings["risk_free"],
                    initial_value=settings["initial_value"],
                )

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Forward Return", _pct(forward.adjusted_return))
        m2.metric("Forward Volatility", _pct(forward.adjusted_volatility))
        m3.metric("Forward Sharpe", f"{forward.adjusted_sharpe:.2f}")
        m4.metric("Forward Projected Value", _money(forward.projected_value))
        m5, m6 = st.columns(2)
        m5.metric(
            STRESS_ADJUSTED_MAX_DRAWDOWN_LABEL,
            _pct(forward.adjusted_max_drawdown),
            help=STRESS_ADJUSTED_MAX_DRAWDOWN_HELP,
        )
        m6.metric("Recession Probability", f"{recession_prob_pct}%")

        st.markdown("##### Forward-Looking Insights")
        for note in forward.forward_insights:
            st.markdown(f"- {note}")
        with st.expander("Rate Environment Effects"):
            for note in forward.rate_commentary:
                st.markdown(f"- {note}")
        with st.expander("Inflation Effects"):
            for note in forward.inflation_commentary:
                st.markdown(f"- {note}")

        section_header("Forward Optimizer Snapshot", FORWARD_OPTIMIZER_SNAPSHOT_SUBTITLE)
        st.caption(FORWARD_OPTIMIZER_SNAPSHOT_SCOPE)
        with st.spinner("Optimizing portfolio..."):
            f_max_sharpe = core.optimize_max_sharpe(
                forward.adjusted_mean_returns,
                forward.adjusted_cov,
                settings["risk_free"],
                len(tickers),
            )
            f_min_vol = core.optimize_min_volatility(
                forward.adjusted_mean_returns,
                forward.adjusted_cov,
                settings["risk_free"],
                len(tickers),
            )
        oc1, oc2 = st.columns(2)
        with oc1:
            st.metric("Forward Max Sharpe Return", _pct(f_max_sharpe.annual_return))
            st.metric("Forward Max Sharpe Volatility", _pct(f_max_sharpe.volatility))
            st.metric("Forward Max Sharpe Ratio", f"{f_max_sharpe.sharpe_ratio:.2f}")
        with oc2:
            st.metric("Forward Min Vol Return", _pct(f_min_vol.annual_return))
            st.metric("Forward Min Volatility", _pct(f_min_vol.volatility))
            st.metric("Forward Min Vol Sharpe", f"{f_min_vol.sharpe_ratio:.2f}")
    elif not beginner_mode:
        st.caption("Forward macro analysis is on-demand for faster initial load.")

# ── Monte Carlo ───────────────────────────────────────────────────────────────

if active_main_tab(_active_tab, "monte_carlo", beginner=beginner_mode) and _require_analytics("Monte Carlo"):
    section_header("Monte Carlo Simulation", f"{HELP['monte_carlo']} {APP_DISCLAIMER}")
    if beginner_mode:
        what_why_do(
            "Monte Carlo",
            "The app runs many random 'what if' futures to show a range of possible outcomes.",
            "Helps you think about best-case, typical, and worst-case scenarios — not a prediction.",
            "Switch to Advanced Mode when you want to explore this tool.",
        )
        st.info("Monte Carlo is available in **Advanced Mode**.")
    else:
        st.session_state.visited_mc = True
        st.caption(
            "Macro settings (from Portfolio Health): "
            + macro_assumption_summary()
        )
        mc_assumption_mode = st.radio(
            "Simulation basis",
            ["Historical returns", "Forward-looking (macro-adjusted)"],
            horizontal=True,
            key="mc_assumption_mode",
            help="Forward-looking adjusts expected return and volatility based on your macro assumptions.",
        )
        if st.button("Run Monte Carlo", key="run_mc_btn"):
            st.session_state.run_mc = True
        if st.session_state.get("run_mc", False):
            mc1, mc2 = st.columns(2)
            with mc1:
                mc_years = render_monte_carlo_projection_years_slider()
            with mc2:
                mc_sims = st.selectbox("Simulations", [200, 500, 1000], index=2)
                mc_target = st.number_input(
                    "Target ending value ($)",
                    min_value=1_000,
                    max_value=10_000_000,
                    value=int(settings["initial_value"] * 1.75),
                    step=5_000,
                )
            mc_fwd_ret = None
            mc_fwd_vol = None
            if mc_assumption_mode.startswith("Forward"):
                forward_mc = get_forward_projection(
                    start=settings["start"],
                    end=settings["end"],
                    metrics=metrics,
                    mean_returns=mean_rets.copy(),
                    cov=cov.values.copy(),
                    tickers=tickers,
                    weights=weights,
                    asset_types=asset_types,
                    initial_value=settings["initial_value"],
                    risk_free_rate=settings["risk_free"],
                    years=float(mc_years),
                )
                mc_fwd_ret = forward_mc.adjusted_return
                mc_fwd_vol = forward_mc.adjusted_volatility
                st.info(
                    f"Using macro-adjusted assumptions: return **{_pct(mc_fwd_ret)}**, "
                    f"volatility **{_pct(mc_fwd_vol)}** "
                    f"(recession stress and inflation/rate environment applied)."
                )
            with st.spinner("Running Monte Carlo…"):
                mc = compute_monte_carlo(
                    returns,
                    tuple(weights.tolist()),
                    settings["initial_value"],
                    mc_years,
                    mc_sims,
                    float(mc_target),
                    expected_annual_return=mc_fwd_ret,
                    expected_annual_volatility=mc_fwd_vol,
                    tickers_tuple=tuple(str(t).strip().upper() for t in tickers),
                )
            st.session_state.mc_cached_summary = mc.summary
            mode_label = "Forward macro-adjusted" if mc_fwd_ret is not None else "Historical"
            st.caption(
                f"Starting capital: **{_money(settings['initial_value'])}** · "
                f"{mc_sims:,} modeled paths · {mc_years} year(s) · "
                f"{mode_label} μ/σ · fixed seed for reproducibility. "
                "Aggregate portfolio simulation (not multi-asset correlated shocks). "
                "No contributions, withdrawals, or deposits on the path. "
                "Chart bands are **pointwise percentile envelopes**, not one simulated path. "
                f"{APP_DISCLAIMER}"
            )
            st.plotly_chart(
                charts.monte_carlo_paths(
                    mc.chart_df,
                    f"Modeled distribution · {mode_label} · {mc_sims:,} sims · {mc_years}Y",
                ),
                use_container_width=True,
            )
            h1, h2 = st.columns([1.2, 1])
            with h1:
                st.plotly_chart(
                    charts.monte_carlo_histogram(mc.ending_values, settings["initial_value"]),
                    use_container_width=True,
                )
            with h2:
                section_header("Outcome Statistics")
                s = mc.summary
                # Short st.metric labels avoid truncation on laptop widths; full meaning below.
                m1, m2, m3 = st.columns(3)
                m1.metric(
                    "P(< start)",
                    _pct(s["prob_loss"]),
                    help="Share of simulations with ending value below starting capital.",
                )
                m2.metric(
                    "P(target)",
                    _pct(s["prob_reach_target"]),
                    help=f"Share of simulations with ending value ≥ {_money(s['target_value'])}.",
                )
                m3.metric(
                    "P(2×)",
                    _pct(s["prob_double"]),
                    help="Share of simulations with ending value at least 2× starting capital.",
                )
                st.caption(
                    "**P(< start)** = ending below start · "
                    f"**P(target)** = ending ≥ {_money(s['target_value'])} · "
                    "**P(2×)** = ending ≥ 2× start."
                )
                m4, m5, m6 = st.columns(3)
                m4.metric("Mean", _money(s["mean"]), help="Average simulated ending value.")
                m5.metric(
                    "ES ≤5th",
                    _money(s["expected_shortfall"]),
                    help="Mean ending value among simulations at or below the 5th percentile.",
                )
                m6.metric("Target", _money(s["target_value"]))
                st.caption(
                    "**Mean** = average ending value · "
                    "**ES ≤5th** = expected shortfall (mean of endings at/below 5th percentile) · "
                    "**Target** = goal used for P(target)."
                )
                st.caption(
                    f"**5th–95th percentile ending values:** {_money(s['ci_low'])} – {_money(s['ci_high'])} "
                    "(empirical band across simulations — not a classical confidence interval)."
                )
                st.caption(
                    f"Downside dispersion of relative endings: {_pct(s['downside_std'])}."
                )
                pcols = st.columns(5)
                for col, (lbl, key) in zip(
                    pcols,
                    [("P5", "p5"), ("P25", "p25"), ("P50", "p50"), ("P75", "p75"), ("P95", "p95")],
                ):
                    col.metric(lbl, _money(s[key]))
                st.caption(
                    "Ending-value percentiles across simulations: "
                    "**P5 / P25 / P50 (median) / P75 / P95**."
                )
        else:
            st.caption("Monte Carlo runs on demand to keep first load fast.")

# ── Optimization ──────────────────────────────────────────────────────────────

if active_main_tab(_active_tab, "optimization", beginner=beginner_mode) and _require_analytics("Optimization"):
    if beginner_mode:
        st.info("Portfolio optimization is available in **Advanced Mode**.")
    else:
        if st.button("Run Portfolio Optimizer", key="run_optimizer_btn"):
            st.session_state.run_optimizer = True

    def opt_table(res: core.OptimizerResult) -> pd.DataFrame:
        rows = [
            {"Metric": "Strategy", "Value": res.label},
            {"Metric": "Return", "Value": _pct(res.annual_return)},
            {"Metric": "Volatility", "Value": _pct(res.volatility)},
            {"Metric": "Sharpe", "Value": f"{res.sharpe_ratio:.2f}"},
        ]
        pv = settings["initial_value"]
        for t, w in zip(tickers, res.weights):
            rows.append({"Metric": t, "Value": f"{_pct(w)} · {_money(pv * w)}"})
        return pd.DataFrame(rows)

    if not beginner_mode and st.session_state.get("run_optimizer", False):
        st.caption("Macro settings: " + macro_assumption_summary())
        opt_assumption_mode = st.radio(
            "Optimization basis",
            ["Historical returns", "Forward-looking (macro-adjusted)"],
            horizontal=True,
            key="opt_assumption_mode",
        )
        use_forward_opt = is_forward_optimizer_basis(opt_assumption_mode)
        section_header(
            "Optimizer Results",
            optimizer_results_methodology_lead(opt_assumption_mode),
        )
        try:
            render_optimizer_confidence()
        except Exception:
            pass
        st.caption(
            f"Dollar weights below use the sidebar analytical portfolio value "
            f"({_money(settings['initial_value'])}) — not ledger deposits as investment return."
        )
        opt_mean = mean_rets
        opt_cov = cov
        forward_opt = None
        if use_forward_opt:
            forward_opt = get_forward_projection(
                start=settings["start"],
                end=settings["end"],
                metrics=metrics,
                mean_returns=mean_rets.copy(),
                cov=cov.values.copy(),
                tickers=tickers,
                weights=weights,
                asset_types=asset_types,
                initial_value=settings["initial_value"],
                risk_free_rate=settings["risk_free"],
            )
            opt_mean = forward_opt.adjusted_mean_returns
            opt_cov = pd.DataFrame(
                forward_opt.adjusted_cov, index=cov.index, columns=cov.columns
            )
        with st.spinner("Optimizing portfolio…"):
            opt = compute_optimizer_pack(tuple(opt_mean.tolist()), opt_cov, settings["risk_free"])
        max_sharpe = opt["max_sharpe"]
        min_vol = opt["min_vol"]
        o1, o2 = st.columns(2)
        with o1:
            st.markdown("**Maximum Sharpe**")
            st.dataframe(opt_table(max_sharpe), use_container_width=True, hide_index=True)
        with o2:
            st.markdown("**Minimum Volatility**")
            st.dataframe(opt_table(min_vol), use_container_width=True, hide_index=True)
        # Compare row uses the same μ/Σ basis as the optimizer run.
        if use_forward_opt and forward_opt is not None:
            your_ret = float(forward_opt.adjusted_return)
            your_vol = float(forward_opt.adjusted_volatility)
            your_sharpe = float(forward_opt.adjusted_sharpe)
            your_label = "Your allocation (forward)"
            basis_note = "Return / Volatility / Sharpe below are forward (macro-adjusted)."
        else:
            your_ret = float(metrics.annual_return)
            your_vol = float(metrics.volatility)
            your_sharpe = float(metrics.sharpe_ratio)
            your_label = "Your allocation (historical)"
            basis_note = "Return / Volatility / Sharpe below are historical (selected date range)."
        compare = pd.DataFrame(
            {
                "Portfolio": [your_label, max_sharpe.label, min_vol.label],
                "Return": [_pct(your_ret), _pct(max_sharpe.annual_return), _pct(min_vol.annual_return)],
                "Volatility": [_pct(your_vol), _pct(max_sharpe.volatility), _pct(min_vol.volatility)],
                "Sharpe": [
                    f"{your_sharpe:.2f}",
                    f"{max_sharpe.sharpe_ratio:.2f}",
                    f"{min_vol.sharpe_ratio:.2f}",
                ],
            }
        )
        st.caption(basis_note)
        st.dataframe(compare, use_container_width=True, hide_index=True)
    elif not beginner_mode:
        st.caption("Optimizer runs on demand.")

# ── Efficient Frontier ────────────────────────────────────────────────────────

if active_main_tab(_active_tab, "frontier", beginner=beginner_mode):
    if beginner_mode:
        st.info("The efficient frontier chart is available in **Advanced Mode**.")
    else:
        if st.button("Build Efficient Frontier", key="run_frontier_btn"):
            st.session_state.run_frontier = True
            st.session_state.pop("_activity_frontier_logged", None)
    if not beginner_mode and st.session_state.get("run_frontier", False):
        st.caption("Macro settings: " + macro_assumption_summary())
        frontier_mode = st.radio(
            "Frontier basis",
            ["Historical Frontier", "Forward-Looking Frontier", "Compare both"],
            horizontal=True,
            key="frontier_assumption_mode",
        )
        section_header("Efficient Frontier", HELP["efficient_frontier"])
        forward_frontier = get_forward_projection(
            start=settings["start"],
            end=settings["end"],
            metrics=metrics,
            mean_returns=mean_rets.copy(),
            cov=cov.values.copy(),
            tickers=tickers,
            weights=weights,
            asset_types=asset_types,
            initial_value=settings["initial_value"],
            risk_free_rate=settings["risk_free"],
        )
        adj_cov = pd.DataFrame(
            forward_frontier.adjusted_cov, index=cov.index, columns=cov.columns
        )

        def _build_frontier_pack(mr, cv, label_prefix: str):
            with st.spinner(f"Building {label_prefix} frontier…"):
                fr = compute_frontier(
                    tuple(mr.tolist()) if hasattr(mr, "tolist") else tuple(mr),
                    cv,
                    settings["risk_free"],
                    settings["frontier_points"],
                )
                op = compute_optimizer_pack(
                    tuple(mr.tolist()) if hasattr(mr, "tolist") else tuple(mr),
                    cv,
                    settings["risk_free"],
                )
            return fr, op

        if frontier_mode == "Compare both":
            fc1, fc2 = st.columns(2)
            with fc1:
                st.markdown("**Historical Frontier**")
                hist_fr, hist_opt = _build_frontier_pack(mean_rets, cov, "historical")
                ms, mv = hist_opt["max_sharpe"], hist_opt["min_vol"]
                st.plotly_chart(
                    charts.efficient_frontier_chart(
                        hist_fr,
                        (metrics.volatility, metrics.annual_return, metrics.sharpe_ratio),
                        (ms.volatility, ms.annual_return, ms.sharpe_ratio, ms.label),
                        (mv.volatility, mv.annual_return, mv.sharpe_ratio, mv.label),
                    ),
                    use_container_width=True,
                )
            with fc2:
                st.markdown("**Forward-Looking Frontier**")
                fwd_fr, fwd_opt = _build_frontier_pack(forward_frontier.adjusted_mean_returns, adj_cov, "forward")
                ms, mv = fwd_opt["max_sharpe"], fwd_opt["min_vol"]
                st.plotly_chart(
                    charts.efficient_frontier_chart(
                        fwd_fr,
                        (forward_frontier.adjusted_volatility, forward_frontier.adjusted_return, forward_frontier.adjusted_sharpe),
                        (ms.volatility, ms.annual_return, ms.sharpe_ratio, ms.label),
                        (mv.volatility, mv.annual_return, mv.sharpe_ratio, mv.label),
                    ),
                    use_container_width=True,
                )
        else:
            use_forward = frontier_mode.startswith("Forward")
            mr = forward_frontier.adjusted_mean_returns if use_forward else mean_rets
            cv = adj_cov if use_forward else cov
            label = "forward-looking" if use_forward else "historical"
            frontier, opt = _build_frontier_pack(mr, cv, label)
            max_sharpe = opt["max_sharpe"]
            min_vol = opt["min_vol"]
            if use_forward:
                current_pt = (
                    forward_frontier.adjusted_volatility,
                    forward_frontier.adjusted_return,
                    forward_frontier.adjusted_sharpe,
                )
            else:
                current_pt = (metrics.volatility, metrics.annual_return, metrics.sharpe_ratio)
            st.plotly_chart(
                charts.efficient_frontier_chart(
                    frontier,
                    current_pt,
                    (max_sharpe.volatility, max_sharpe.annual_return, max_sharpe.sharpe_ratio, max_sharpe.label),
                    (min_vol.volatility, min_vol.annual_return, min_vol.sharpe_ratio, min_vol.label),
                ),
                use_container_width=True,
            )
        if not st.session_state.get("_activity_frontier_logged"):
            try:
                from investment_activity import log_frontier_viewed

                log_frontier_viewed(st)
                st.session_state["_activity_frontier_logged"] = True
            except Exception:
                pass
        st.caption("★ Your portfolio · ◆ Max Sharpe · ■ Min volatility — hover for return and volatility.")
    elif not beginner_mode:
        st.caption("Frontier construction is on demand.")

# ── My Portfolio (real ownership ledger) ──────────────────────────────────────

if is_real_portfolio_tab(_active_tab):
    try:
        from components.real_portfolio import render_real_portfolio_tab

        render_real_portfolio_tab(beginner=beginner_mode)
    except ImportError:
        st.warning("Real portfolio module is not available in this build.")

# ── ETF Holdings Explorer (Advanced only) ─────────────────────────────────────

if not beginner_mode and is_etf_holdings_tab(_active_tab):
    try:
        from components.etf_holdings_explorer import render_etf_holdings_explorer

        render_etf_holdings_explorer(st.session_state.holdings_df, settings=settings)
    except ImportError:
        st.warning("ETF Holdings Explorer module is not available in this build.")

# ── Header health badge (cached; no heavy health calc on load) ─────────────────

render_health_header_badge(health_badge_slot, tickers, weights)

try:
    if _PERSISTENCE_OK and not pp.skip_background_persistence(st):
        autosave_investment_state(st, end_of_run=True, trigger="end_of_run")
        finalize_persistence_debug(st)
except Exception:
    pass
try:
    from investment_persistence_trace import investment_trace_enabled, snapshot_full_trace

    if _PERSISTENCE_OK and investment_trace_enabled(st, persistence_ok=_PERSISTENCE_OK):
        snapshot_full_trace(st, persistence_ok=_PERSISTENCE_OK)
except Exception:
    pass
try:
    if _PERSISTENCE_OK:
        from suite_user_persistence import clear_workspace_autosave_block

        clear_workspace_autosave_block(st, "investment")
except Exception:
    pass

