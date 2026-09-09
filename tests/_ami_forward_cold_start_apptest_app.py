"""Minimal Streamlit app: AMI cold-start Forward metrics without visiting Forward UI."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import streamlit as st

import portfolio_core as core
from applied_math_context import build_investment_applied_math_context, ensure_ami_forward_scenario_metrics
from components.macro_engine import (
    FORWARD_PROJECTION_KEY,
    ensure_shared_macro_session_defaults,
    store_forward_engine_inputs,
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

tickers = ["VTI", "VXUS", "BND", "VNQ"]
weights = np.array([0.40, 0.20, 0.30, 0.10], dtype=float)
asset_types = ["Equity", "Equity", "Bonds", "REIT"]
st.session_state["holdings_df"] = pd.DataFrame(
    [
        {"Ticker": "VTI", "Weight (%)": 40.0, "Asset Type": "Equity"},
        {"Ticker": "VXUS", "Weight (%)": 20.0, "Asset Type": "Equity"},
        {"Ticker": "BND", "Weight (%)": 30.0, "Asset Type": "Bond"},
        {"Ticker": "VNQ", "Weight (%)": 10.0, "Asset Type": "REIT"},
    ]
)

# Simulate analytics-ready engine inputs WITHOUT visiting Forward Macro.
if "_forward_engine_inputs" not in st.session_state:
    rng = np.random.default_rng(7)
    idx = pd.date_range("2018-01-01", periods=600, freq="B")
    rets = pd.DataFrame(
        {
            "VTI": rng.normal(0.0005, 0.01, len(idx)),
            "VXUS": rng.normal(0.0003, 0.012, len(idx)),
            "BND": rng.normal(0.00008, 0.003, len(idx)),
            "VNQ": rng.normal(0.0004, 0.014, len(idx)),
        },
        index=idx,
    )
    mean_rets, cov, aligned = core.annualized_mean_and_cov(rets, tickers=tickers, weights=weights)
    metrics = core.compute_extended_metrics(aligned, weights, 0.04, 10_000.0, tickers=tickers)
    store_forward_engine_inputs(
        st.session_state,
        metrics=metrics,
        mean_returns=mean_rets,
        cov=cov,
        tickers=tickers,
        weights=weights,
        asset_types=asset_types,
        start="2018-01-01",
        end="2024-12-31",
        initial_value=10_000.0,
        risk_free_rate=0.04,
    )

# Cold-start: clear any Forward UI cache.
st.session_state.pop(FORWARD_PROJECTION_KEY, None)
st.session_state.pop("forward_projection_fp", None)

q = (
    "How does my current macro environment affect my portfolio, "
    "and should I change my allocation because of it?"
)
ctx = build_investment_applied_math_context("Portfolio Health", st.session_state)
assert "_ami_session_ref" not in ctx
safe = json_safe_context(ctx)  # must not raise SessionStateProxy TypeError
import json

json.dumps(safe)
ensure_ami_forward_scenario_metrics(ctx)
pair = solve_instant_insight(q, ctx)
assert pair is not None
_, result = pair
st.markdown("ok=1")
st.markdown("has_forward=" + str(ctx.get("forward_modeled_return") is not None))
st.markdown("ret=" + str(ctx.get("forward_modeled_return_display")))
st.markdown("vol=" + str(ctx.get("forward_modeled_volatility_display")))
st.markdown("sharpe=" + str(ctx.get("forward_modeled_sharpe_display")))
st.markdown("answer_has_forward=" + str("forward modeled" in (result.short_answer or "").lower()))
