"""
Investment Portfolio Analyzer — Streamlit dashboard UI.
Core calculations are in portfolio_core.py (do not duplicate formulas here).
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import portfolio_core as core

# ── Page config & global styling ──────────────────────────────────────────────

st.set_page_config(
    page_title="Investment Portfolio Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 1.25rem; padding-bottom: 2rem; max-width: 1200px; }
    [data-testid="stMetric"] {
        background: linear-gradient(145deg, #1a2332 0%, #121820 100%);
        border: 1px solid #2d3a4f;
        border-radius: 10px;
        padding: 0.85rem 1rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    }
    [data-testid="stMetric"] label { font-size: 0.8rem; color: #9eb0c8; }
    [data-testid="stMetric"] [data-testid="stMetricValue"] {
        font-size: 1.45rem; font-weight: 600; color: #f0f4f8;
    }
    .section-lead { color: #8fa3bc; font-size: 0.92rem; margin-bottom: 0.75rem; }
    .dashboard-title { font-size: 1.75rem; font-weight: 700; margin-bottom: 0.15rem; }
    .dashboard-sub { color: #7d92ab; font-size: 0.95rem; margin-bottom: 1.25rem; }
    div[data-testid="stSidebar"] .block-container { padding-top: 1rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

HELP = {
    "sharpe": (
        "**Sharpe ratio** measures return per unit of risk. "
        "Higher is better. Above ~1.0 is solid; below 0 means returns did not beat the risk-free rate."
    ),
    "volatility": (
        "**Volatility** is how much returns swing up and down (annualized standard deviation). "
        "Higher volatility means a bumpier ride, not necessarily worse returns."
    ),
    "correlation": (
        "**Correlation** shows how assets move together (-1 to +1). "
        "Lower correlations between holdings can improve diversification."
    ),
    "monte_carlo": (
        "**Monte Carlo simulation** runs many random future paths using historical return and volatility. "
        "It illustrates a range of outcomes, not a forecast."
    ),
    "efficient_frontier": (
        "The **efficient frontier** plots optimal portfolios for each level of risk (volatility). "
        "Points on the curve offer the highest expected return for that risk level."
    ),
}


def _pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def _money(x: float) -> str:
    return f"${x:,.0f}"


@st.cache_data(show_spinner="Fetching market data…")
def load_market_data(tickers: tuple[str, ...], start: str, end: str | None):
    return core.fetch_price_history(list(tickers), start, end)


def metric_row(metrics: core.PortfolioMetrics, initial_value: float):
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(
            "Annual Return",
            _pct(metrics.annual_return),
            help="Average daily return × 252 trading days.",
        )
    with c2:
        st.metric(
            "Volatility",
            _pct(metrics.volatility),
            help=HELP["volatility"],
        )
    with c3:
        st.metric(
            "Sharpe Ratio",
            f"{metrics.sharpe_ratio:.2f}",
            help=HELP["sharpe"],
        )
    with c4:
        st.metric(
            "Projected Value (1Y)",
            _money(metrics.projected_value),
            delta=_money(metrics.projected_value - initial_value),
            help="Simple projection using historical annual return.",
        )


def render_sidebar() -> dict:
    st.sidebar.markdown("### ⚙️ Analysis Settings")
    st.sidebar.caption("Configure dates, capital, and risk assumptions.")

    end_default = dt.date.today()
    start_default = end_default - dt.timedelta(days=365 * 5)
    col_a, col_b = st.sidebar.columns(2)
    with col_a:
        start_date = st.date_input("Start date", value=start_default)
    with col_b:
        end_date = st.date_input("End date", value=end_default)

    initial_value = st.sidebar.number_input(
        "Portfolio value ($)",
        min_value=1_000,
        value=100_000,
        step=5_000,
        help="Total capital used for value projections and Monte Carlo.",
    )
    risk_free = (
        st.sidebar.slider(
            "Risk-free rate (annual %)",
            0.0,
            10.0,
            4.0,
            0.25,
            help="Used for Sharpe ratio and efficient frontier.",
        )
        / 100.0
    )

    st.sidebar.divider()
    st.sidebar.markdown("### 📎 Quick-add assets")
    st.sidebar.caption("Bonds, T-bills, REITs, and dividend ETFs.")
    preset_choice = st.sidebar.selectbox(
        "Preset",
        ["— select —"] + list(core.ASSET_PRESETS.keys()),
        label_visibility="collapsed",
    )

    st.sidebar.divider()
    st.sidebar.markdown("### ℹ️ About")
    st.sidebar.info(
        "Uses **yfinance** for real ticker data. "
        "Past performance does not guarantee future results."
    )

    return {
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "initial_value": float(initial_value),
        "risk_free": float(risk_free),
        "preset_choice": preset_choice,
    }


def init_holdings_state():
    if "holdings_df" not in st.session_state:
        st.session_state.holdings_df = pd.DataFrame(core.DEFAULT_HOLDINGS)


def apply_preset(preset_name: str):
    if preset_name == "— select —":
        return
    info = core.ASSET_PRESETS[preset_name]
    df = st.session_state.holdings_df.copy()
    new_row = {
        "Ticker": info["ticker"],
        "Weight (%)": 0.0,
        "Asset Type": info["category"],
    }
    if info["ticker"] not in df["Ticker"].astype(str).str.upper().values:
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    st.session_state.holdings_df = df


def parse_holdings(df: pd.DataFrame) -> tuple[list[str], np.ndarray, list[str]]:
    clean = df.dropna(subset=["Ticker"]).copy()
    clean["Ticker"] = clean["Ticker"].astype(str).str.strip().str.upper()
    clean = clean[clean["Ticker"] != ""]
    if clean.empty:
        raise ValueError("Add at least one ticker to the portfolio.")

    weights_pct = clean["Weight (%)"].fillna(0).astype(float).values
    if weights_pct.sum() <= 0:
        weights = np.ones(len(clean)) / len(clean)
    else:
        weights = core.normalize_weights(weights_pct / 100.0)

    tickers = clean["Ticker"].tolist()
    types = clean.get("Asset Type", pd.Series(["Equity"] * len(clean))).fillna("Equity").tolist()
    return tickers, weights, types


# ── Header ────────────────────────────────────────────────────────────────────

st.markdown('<p class="dashboard-title">📊 Investment Portfolio Analyzer</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="dashboard-sub">Analyze risk, run simulations, and explore optimization — '
    "beginner-friendly, portfolio-ready.</p>",
    unsafe_allow_html=True,
)

settings = render_sidebar()
init_holdings_state()
if settings["preset_choice"] != "— select —":
    apply_preset(settings["preset_choice"])

tab_overview, tab_inputs, tab_risk, tab_mc, tab_opt, tab_frontier = st.tabs(
    [
        "Overview",
        "Portfolio Inputs",
        "Risk Analysis",
        "Monte Carlo",
        "Optimization",
        "Efficient Frontier",
    ]
)

# ── Portfolio Inputs tab (also drives data) ───────────────────────────────────

with tab_inputs:
    st.markdown("#### Portfolio Inputs")
    st.markdown(
        '<p class="section-lead">Enter tickers and target weights. Weights are normalized to 100% '
        "if they do not sum exactly. Use **Asset Type** for clarity (equity, bonds, REIT, etc.).</p>",
        unsafe_allow_html=True,
    )
    edited = st.data_editor(
        st.session_state.holdings_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Ticker": st.column_config.TextColumn("Ticker", help="Yahoo Finance symbol, e.g. AAPL, BND, VNQ"),
            "Weight (%)": st.column_config.NumberColumn(
                "Weight (%)",
                min_value=0.0,
                max_value=100.0,
                format="%.1f",
            ),
            "Asset Type": st.column_config.SelectboxColumn(
                "Asset Type",
                options=["Equity", "Bonds", "T-Bills", "REIT", "Dividend ETF", "Other"],
            ),
        },
        key="holdings_editor",
    )
    st.session_state.holdings_df = edited

    w_sum = edited["Weight (%)"].fillna(0).sum()
    if abs(w_sum - 100) > 0.5:
        st.warning(f"Weights sum to **{w_sum:.1f}%** — they will be normalized automatically.")

# Parse holdings for all tabs
try:
    tickers, weights, asset_types = parse_holdings(st.session_state.holdings_df)
except ValueError as e:
    st.error(str(e))
    st.stop()

# Load data once
try:
    prices = load_market_data(tuple(tickers), settings["start"], settings["end"])
    returns = core.daily_returns(prices)
    mean_rets = returns.mean().values * core.TRADING_DAYS
    cov = returns.cov().values * core.TRADING_DAYS
    metrics = core.compute_portfolio_metrics(
        returns,
        weights,
        settings["risk_free"],
        settings["initial_value"],
    )
except Exception as ex:
    st.error(f"Could not load market data: {ex}")
    st.stop()

latest_prices = prices.iloc[-1] if len(tickers) == 1 else prices.iloc[-1]
holdings_df = core.holdings_breakdown(
    tickers, weights, asset_types, settings["initial_value"], latest_prices
)
growth = core.portfolio_growth_series(returns, weights, settings["initial_value"])
corr = core.correlation_matrix(returns)
scenarios = core.scenario_analysis(returns, weights, settings["initial_value"])
max_sharpe = core.optimize_max_sharpe(mean_rets, cov, settings["risk_free"], len(tickers))
min_vol = core.optimize_min_volatility(mean_rets, cov, settings["risk_free"], len(tickers))
frontier = core.efficient_frontier(mean_rets, cov, settings["risk_free"])

# ── Overview ──────────────────────────────────────────────────────────────────

with tab_overview:
    st.markdown("#### Portfolio Summary")
    st.markdown(
        '<p class="section-lead">Key risk/return metrics based on historical daily returns.</p>',
        unsafe_allow_html=True,
    )
    metric_row(metrics, settings["initial_value"])

    with st.expander("What is the Sharpe ratio?", expanded=False):
        st.markdown(HELP["sharpe"])

    st.markdown("#### Holdings Table")
    display_holdings = holdings_df.copy()
    display_holdings["Weight (%)"] = display_holdings["Weight (%)"].map(lambda x: f"{x:.1f}%")
    display_holdings["Value ($)"] = display_holdings["Value ($)"].map(_money)
    st.dataframe(display_holdings, use_container_width=True, hide_index=True)

    st.markdown("#### Growth Over Time")
    growth_df = growth.reset_index()
    growth_df.columns = ["Date", "Portfolio Value"]
    fig_growth = px.line(
        growth_df,
        x="Date",
        y="Portfolio Value",
        color_discrete_sequence=["#4da3ff"],
    )
    fig_growth.update_layout(
        height=380,
        margin=dict(l=0, r=0, t=30, b=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#c8d4e0"),
    )
    st.plotly_chart(fig_growth, use_container_width=True)

    st.markdown("#### Allocation Chart")
    fig_alloc = px.pie(
        holdings_df,
        names="Ticker",
        values="Weight",
        hole=0.45,
        color_discrete_sequence=px.colors.sequential.Blues_r,
    )
    fig_alloc.update_layout(height=360, margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(fig_alloc, use_container_width=True)

# ── Risk Analysis ─────────────────────────────────────────────────────────────

with tab_risk:
    st.markdown("#### Correlation Matrix")
    st.caption(HELP["correlation"].replace("**", ""))
    fig_corr = px.imshow(
        corr,
        text_auto=".2f",
        aspect="auto",
        color_continuous_scale="RdBu_r",
        zmin=-1,
        zmax=1,
    )
    fig_corr.update_layout(height=420, margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(fig_corr, use_container_width=True)

    st.markdown("#### Scenario Analysis")
    st.markdown(
        '<p class="section-lead">Hypothetical one-year portfolio outcomes under simple return shocks.</p>',
        unsafe_allow_html=True,
    )
    scen_display = scenarios.copy()
    scen_display["Assumed 1Y Return"] = scen_display["Assumed 1Y Return"].map(_pct)
    scen_display["Projected Value"] = scen_display["Projected Value"].map(_money)
    scen_display["Gain / Loss ($)"] = scen_display["Gain / Loss ($)"].map(
        lambda x: f"+{_money(x)}" if x >= 0 else f"-{_money(abs(x))}"
    )
    st.dataframe(scen_display, use_container_width=True, hide_index=True)

    with st.expander("Understanding volatility"):
        st.markdown(HELP["volatility"])

# ── Monte Carlo ───────────────────────────────────────────────────────────────

with tab_mc:
    st.markdown("#### Monte Carlo Simulation")
    st.caption(HELP["monte_carlo"].replace("**", ""))
    c1, c2 = st.columns(2)
    with c1:
        mc_years = st.slider("Projection years", 1, 15, 5)
    with c2:
        mc_sims = st.selectbox("Simulations", [200, 500, 1000], index=1)

    mc_chart, mc_summary = core.monte_carlo_simulation(
        returns, weights, settings["initial_value"], mc_years, mc_sims
    )

    fig_mc = go.Figure()
    fig_mc.add_trace(go.Scatter(x=mc_chart["Day"], y=mc_chart["5th Percentile"], name="5th %ile", line=dict(color="#e74c3c", dash="dot")))
    fig_mc.add_trace(go.Scatter(x=mc_chart["Day"], y=mc_chart["Median"], name="Median", line=dict(color="#4da3ff", width=2)))
    fig_mc.add_trace(go.Scatter(x=mc_chart["Day"], y=mc_chart["95th Percentile"], name="95th %ile", line=dict(color="#2ecc71", dash="dot")))
    fig_mc.update_layout(
        title=f"{mc_sims} simulated paths ({mc_years} years)",
        xaxis_title="Trading days",
        yaxis_title="Portfolio value ($)",
        height=400,
        margin=dict(l=0, r=0, t=40, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig_mc, use_container_width=True)

    m1, m2, m3, m4, m5 = st.columns(5)
    for col, (label, key) in zip(
        [m1, m2, m3, m4, m5],
        [("5th %ile", "p5"), ("25th %ile", "p25"), ("Median", "p50"), ("75th %ile", "p75"), ("95th %ile", "p95")],
    ):
        with col:
            st.metric(f"Ending {label}", _money(mc_summary[key]))

# ── Optimization ──────────────────────────────────────────────────────────────

with tab_opt:
    st.markdown("#### Optimizer Results")
    st.markdown(
        '<p class="section-lead">Mean-variance optimization on historical returns (long-only, weights sum to 100%).</p>',
        unsafe_allow_html=True,
    )

    def _optimizer_table(result: core.OptimizerResult) -> pd.DataFrame:
        rows = [
            {"Metric": "Strategy", "Value": result.label},
            {"Metric": "Annual Return", "Value": _pct(result.annual_return)},
            {"Metric": "Volatility", "Value": _pct(result.volatility)},
            {"Metric": "Sharpe Ratio", "Value": f"{result.sharpe_ratio:.2f}"},
        ]
        for t, w in zip(tickers, result.weights):
            rows.append({"Metric": f"Weight — {t}", "Value": _pct(w)})
        return pd.DataFrame(rows)

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("**Maximum Sharpe**")
        st.dataframe(_optimizer_table(max_sharpe), use_container_width=True, hide_index=True)
    with col_r:
        st.markdown("**Minimum Volatility**")
        st.dataframe(_optimizer_table(min_vol), use_container_width=True, hide_index=True)

    st.markdown("#### Current vs optimized (Sharpe)")
    compare = pd.DataFrame(
        {
            "Portfolio": ["Your allocation", max_sharpe.label, min_vol.label],
            "Return": [_pct(metrics.annual_return), _pct(max_sharpe.annual_return), _pct(min_vol.annual_return)],
            "Volatility": [_pct(metrics.volatility), _pct(max_sharpe.volatility), _pct(min_vol.volatility)],
            "Sharpe": [
                f"{metrics.sharpe_ratio:.2f}",
                f"{max_sharpe.sharpe_ratio:.2f}",
                f"{min_vol.sharpe_ratio:.2f}",
            ],
        }
    )
    st.dataframe(compare, use_container_width=True, hide_index=True)

# ── Efficient Frontier ────────────────────────────────────────────────────────

with tab_frontier:
    st.markdown("#### Efficient Frontier")
    st.caption(HELP["efficient_frontier"].replace("**", ""))

    fig_ef = go.Figure()
    fig_ef.add_trace(
        go.Scatter(
            x=frontier["Volatility"],
            y=frontier["Return"],
            mode="lines+markers",
            name="Efficient frontier",
            line=dict(color="#4da3ff", width=2),
        )
    )
    fig_ef.add_trace(
        go.Scatter(
            x=[metrics.volatility],
            y=[metrics.annual_return],
            mode="markers",
            name="Your portfolio",
            marker=dict(size=14, color="#f39c12", symbol="star"),
        )
    )
    fig_ef.add_trace(
        go.Scatter(
            x=[max_sharpe.volatility],
            y=[max_sharpe.annual_return],
            mode="markers",
            name="Max Sharpe",
            marker=dict(size=12, color="#2ecc71"),
        )
    )
    fig_ef.add_trace(
        go.Scatter(
            x=[min_vol.volatility],
            y=[min_vol.annual_return],
            mode="markers",
            name="Min volatility",
            marker=dict(size=12, color="#e74c3c"),
        )
    )
    fig_ef.update_layout(
        xaxis_title="Volatility (annual)",
        yaxis_title="Return (annual)",
        yaxis_tickformat=".0%",
        xaxis_tickformat=".0%",
        height=450,
        margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig_ef, use_container_width=True)
