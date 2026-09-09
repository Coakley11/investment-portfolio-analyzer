"""Minimal Streamlit app: true AMI cold-start without Forward/analytics page seed.

Does NOT call store_forward_engine_inputs or visit Forward / MC / Optimizer.
Engine inputs are materialized from holdings + session settings via the
canonical resolver (fetch_price_history mocked for offline CI).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import streamlit as st

import portfolio_core as core
from applied_math_context import build_investment_applied_math_context, ensure_ami_forward_scenario_metrics
from components.macro_engine import (
    FORWARD_ENGINE_INPUTS_KEY,
    FORWARD_PROJECTION_KEY,
    ensure_shared_macro_session_defaults,
)
from json_safe import json_safe_context
from investment_ami.integration.instant_solver_facade import solve_instant_insight

ensure_shared_macro_session_defaults()

st.session_state.setdefault("health_rate_env", "Rising Rates")
st.session_state.setdefault("health_inflation", "High Inflation")
st.session_state.setdefault("health_recession", 60)
st.session_state.setdefault("health_valuation", "Expensive")
st.session_state.setdefault("health_regime", "Recession")
st.session_state.setdefault("fwd_years", 10)
st.session_state.setdefault("risk_free_pct", 4.0)
st.session_state.setdefault("analysis_start_date", "2018-01-01")
st.session_state.setdefault("analysis_end_date", "2024-12-31")
st.session_state.setdefault("sidebar_portfolio_value", 10_000.0)

tickers = ["VTI", "VXUS", "BND", "VNQ"]
weights = np.array([0.40, 0.20, 0.30, 0.10], dtype=float)
st.session_state["holdings_df"] = pd.DataFrame(
    [
        {"Ticker": "VTI", "Weight (%)": 40.0, "Asset Type": "Equity"},
        {"Ticker": "VXUS", "Weight (%)": 20.0, "Asset Type": "Equity"},
        {"Ticker": "BND", "Weight (%)": 30.0, "Asset Type": "Bonds"},
        {"Ticker": "VNQ", "Weight (%)": 10.0, "Asset Type": "REIT"},
    ]
)

# True cold-start: no Forward UI cache and no special engine-input bundle.
st.session_state.pop(FORWARD_PROJECTION_KEY, None)
st.session_state.pop("forward_projection_fp", None)
st.session_state.pop(FORWARD_ENGINE_INPUTS_KEY, None)
assert FORWARD_ENGINE_INPUTS_KEY not in st.session_state


def _fake_prices(symbols, start, end=None):
    """Offline stand-in for market data (same path live AMI uses)."""
    rng = np.random.default_rng(7)
    idx = pd.date_range(str(start)[:10], periods=600, freq="B")
    cols = [str(t).strip().upper() for t in symbols]
    data = {t: 100.0 * np.cumprod(1.0 + rng.normal(0.0003, 0.01, len(idx))) for t in cols}
    return pd.DataFrame(data, index=idx)


q = (
    "How does my current macro environment affect my portfolio, "
    "and should I change my allocation because of it?"
)
ctx = build_investment_applied_math_context("Portfolio Health", st.session_state)
assert "_ami_session_ref" not in ctx
safe = json_safe_context(ctx)
import json

json.dumps(safe)

with mock.patch("portfolio_core.fetch_price_history", side_effect=_fake_prices):
    ensure_ami_forward_scenario_metrics(ctx)
pair = solve_instant_insight(q, ctx)
assert pair is not None
_, result = pair
answer = (result.short_answer or "") + " " + str(getattr(result, "analyst_sections", "") or "")
st.markdown("ok=1")
st.markdown("has_forward=" + str(ctx.get("forward_modeled_return") is not None))
st.markdown("ret=" + str(ctx.get("forward_modeled_return_display")))
st.markdown("vol=" + str(ctx.get("forward_modeled_volatility_display")))
st.markdown("sharpe=" + str(ctx.get("forward_modeled_sharpe_display")))
st.markdown(
    "answer_has_forward="
    + str(
        "forward modeled" in answer.lower()
        or "modeled return" in answer.lower()
    )
)
st.markdown("engine_inputs_materialized=" + str(isinstance(st.session_state.get(FORWARD_ENGINE_INPUTS_KEY), dict)))
