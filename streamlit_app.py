"""
Investment Portfolio Analyzer — professional finance dashboard UI.
Core calculations: portfolio_core.py | Charts: dashboard_charts.py
"""

from __future__ import annotations

import datetime as dt
import io

import numpy as np
import pandas as pd
import streamlit as st

import dashboard_charts as charts
import portfolio_core as core

# ── Page config & styling ─────────────────────────────────────────────────────

st.set_page_config(
    page_title="Portfolio Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 1rem; padding-bottom: 2.5rem; max-width: 1280px; }
    [data-testid="stMetric"] {
        background: linear-gradient(160deg, #1e2a3a 0%, #141c28 100%);
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 0.75rem 0.9rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.2);
    }
    [data-testid="stMetric"] label {
        font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em;
        color: #94a3b8 !important;
    }
    [data-testid="stMetric"] [data-testid="stMetricValue"] {
        font-size: 1.35rem; font-weight: 600; color: #f1f5f9;
    }
    .dashboard-title {
        font-size: 1.65rem; font-weight: 700; color: #f8fafc;
        margin: 0 0 0.1rem 0; letter-spacing: -0.02em;
    }
    .dashboard-sub { color: #64748b; font-size: 0.9rem; margin-bottom: 1rem; }
    .section-lead { color: #94a3b8; font-size: 0.88rem; margin-bottom: 0.65rem; line-height: 1.45; }
    .insight-card {
        background: #1a2332; border-left: 3px solid #4da3ff;
        padding: 0.65rem 0.9rem; margin-bottom: 0.5rem;
        border-radius: 0 6px 6px 0; font-size: 0.9rem; color: #cbd5e1;
    }
    .finance-divider { border-top: 1px solid #334155; margin: 1.25rem 0; }
    @media (max-width: 768px) {
        .block-container { padding-left: 1rem; padding-right: 1rem; }
        [data-testid="stMetric"] [data-testid="stMetricValue"] { font-size: 1.1rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

HELP = {
    "sharpe": "Return per unit of total risk. Above ~1.0 is strong.",
    "sortino": "Like Sharpe, but penalizes only downside volatility.",
    "volatility": "Annualized standard deviation of daily returns.",
    "correlation": "How assets move together (-1 to +1). Lower can mean better diversification.",
    "monte_carlo": "Random future paths from historical return/vol — a range of outcomes, not a forecast.",
    "efficient_frontier": "Optimal risk/return combinations from mean-variance optimization.",
    "drawdown": "Largest peak-to-trough decline over the analysis period.",
    "beta": "Sensitivity vs SPY: 1.0 moves with the market; >1 is more aggressive.",
}


def _pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def _money(x: float) -> str:
    return f"${x:,.0f}"


def section_header(title: str, lead: str = ""):
    st.markdown(f"#### {title}")
    if lead:
        st.markdown(f'<p class="section-lead">{lead}</p>', unsafe_allow_html=True)
    st.markdown('<div class="finance-divider"></div>', unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def load_market_data(tickers: tuple[str, ...], start: str, end: str | None):
    return core.fetch_price_history(list(tickers), start, end)


@st.cache_data(show_spinner=False)
def load_benchmark_returns(start: str, end: str | None):
    prices = core.fetch_price_history([core.BENCHMARK_TICKER], start, end)
    return core.daily_returns(prices).iloc[:, 0]


def render_insights(insights: list[str]):
    for text in insights:
        plain = text.replace("**", "")
        st.markdown(f'<div class="insight-card">💡 {plain}</div>', unsafe_allow_html=True)


def metrics_row_primary(m: core.ExtendedPortfolioMetrics, initial: float):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Annual Return", _pct(m.annual_return))
    c2.metric("Volatility", _pct(m.volatility), help=HELP["volatility"])
    c3.metric("Sharpe Ratio", f"{m.sharpe_ratio:.2f}", help=HELP["sharpe"])
    c4.metric(
        "Projected Value (1Y)",
        _money(m.projected_value),
        delta=_money(m.projected_value - initial),
    )


def metrics_row_extended(m: core.ExtendedPortfolioMetrics):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Max Drawdown", _pct(m.max_drawdown), help=HELP["drawdown"])
    c2.metric("Sortino Ratio", f"{m.sortino_ratio:.2f}", help=HELP["sortino"])
    c3.metric("CAGR", _pct(m.cagr))
    c4.metric("Beta vs SPY", f"{m.beta_spy:.2f}", help=HELP["beta"])


def render_sidebar() -> dict:
    st.sidebar.markdown("### Portfolio Presets")
    st.sidebar.caption("Load a model allocation into the holdings table.")
    preset_names = ["— custom —", *core.PORTFOLIO_PRESETS.keys()]
    portfolio_preset = st.sidebar.selectbox("Strategy", preset_names, label_visibility="collapsed")
    if st.sidebar.button("Apply preset", use_container_width=True, type="primary"):
        if portfolio_preset in core.PORTFOLIO_PRESETS:
            st.session_state.holdings_df = pd.DataFrame(core.PORTFOLIO_PRESETS[portfolio_preset])
            st.session_state.preset_applied = portfolio_preset
            st.rerun()

    st.sidebar.divider()
    st.sidebar.markdown("### Analysis Settings")
    end_default = dt.date.today()
    start_default = end_default - dt.timedelta(days=365 * 5)
    ca, cb = st.sidebar.columns(2)
    with ca:
        start_date = st.date_input("Start", value=start_default)
    with cb:
        end_date = st.date_input("End", value=end_default)

    initial_value = st.sidebar.number_input("Portfolio value ($)", 1_000, 100_000, 100_000, 5_000)
    risk_free = st.sidebar.slider("Risk-free rate (%)", 0.0, 10.0, 4.0, 0.25) / 100.0

    st.sidebar.divider()
    st.sidebar.markdown("### Quick-add asset")
    asset_preset = st.sidebar.selectbox("ETF preset", ["—"] + list(core.ASSET_PRESETS.keys()))

    st.sidebar.divider()
    st.sidebar.markdown("### Export")
    st.sidebar.caption("Downloads appear after analysis loads.")

    st.sidebar.divider()
    st.sidebar.caption("Data: yfinance · Not financial advice")

    return {
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "initial_value": float(initial_value),
        "risk_free": float(risk_free),
        "portfolio_preset": portfolio_preset,
        "asset_preset": asset_preset,
    }


def init_holdings():
    if "holdings_df" not in st.session_state:
        st.session_state.holdings_df = pd.DataFrame(core.DEFAULT_HOLDINGS)


def apply_asset_preset(name: str):
    if name == "—":
        return
    info = core.ASSET_PRESETS[name]
    df = st.session_state.holdings_df.copy()
    if info["ticker"] not in df["Ticker"].astype(str).str.upper().values:
        df = pd.concat(
            [df, pd.DataFrame([{"Ticker": info["ticker"], "Weight (%)": 0.0, "Asset Type": info["category"]}])],
            ignore_index=True,
        )
        st.session_state.holdings_df = df


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

st.markdown('<p class="dashboard-title">Investment Portfolio Analyzer</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="dashboard-sub">Professional portfolio analytics · Real market data · Risk & optimization</p>',
    unsafe_allow_html=True,
)

settings = render_sidebar()
init_holdings()
apply_asset_preset(settings["asset_preset"])

tabs = st.tabs(
    ["Overview", "Portfolio Inputs", "Risk Analysis", "Monte Carlo", "Optimization", "Efficient Frontier"]
)
tab_overview, tab_inputs, tab_risk, tab_mc, tab_opt, tab_frontier = tabs

with tab_inputs:
    section_header("Portfolio Inputs", "Tickers and target weights. Normalized to 100% if needed.")
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
    ws = edited["Weight (%)"].fillna(0).sum()
    if abs(ws - 100) > 0.5:
        st.warning(f"Weights sum to **{ws:.1f}%** — auto-normalized in calculations.")

try:
    tickers, weights, asset_types = parse_holdings(st.session_state.holdings_df)
except ValueError as e:
    st.error(str(e))
    st.stop()

with st.spinner("Loading market data and running analytics…"):
    try:
        prices = load_market_data(tuple(tickers), settings["start"], settings["end"])
        bench_rets = load_benchmark_returns(settings["start"], settings["end"])
        returns = core.daily_returns(prices)
        mean_rets = returns.mean().values * core.TRADING_DAYS
        cov = returns.cov().values * core.TRADING_DAYS
        metrics = core.compute_extended_metrics(
            returns, weights, settings["risk_free"], settings["initial_value"], benchmark_rets=bench_rets
        )
        port_rets = core.portfolio_daily_returns(returns, weights)
        growth = core.portfolio_growth_series(returns, weights, settings["initial_value"])
        corr = core.correlation_matrix(returns)
        scenarios = core.scenario_analysis(returns, weights, settings["initial_value"])
        vol_rank = core.volatility_ranking(returns)
        risk_contrib = core.risk_contribution(returns, weights)
        roll_vol = core.rolling_volatility(port_rets)
        roll_ret = core.rolling_returns(port_rets)
        max_sharpe = core.optimize_max_sharpe(mean_rets, cov, settings["risk_free"], len(tickers))
        min_vol = core.optimize_min_volatility(mean_rets, cov, settings["risk_free"], len(tickers))
        frontier = core.efficient_frontier(mean_rets, cov, settings["risk_free"])
        insights = core.generate_portfolio_insights(
            tickers, weights, asset_types, metrics, corr, risk_contrib
        )
        mc_default = core.monte_carlo_simulation(
            returns, weights, settings["initial_value"], years=5, simulations=500
        )
    except Exception as ex:
        st.error(f"Analysis failed: {ex}")
        st.stop()

latest = prices.iloc[-1]
holdings_df = core.holdings_breakdown(tickers, weights, asset_types, settings["initial_value"], latest)
report_text = core.build_summary_report(
    tickers, weights, metrics, mc_default.summary, insights, settings
)
export_buttons(holdings_df, metrics, scenarios, vol_rank, risk_contrib, report_text)

# ── Overview ──────────────────────────────────────────────────────────────────

with tab_overview:
    section_header("Portfolio Summary", "Historical risk/return based on daily returns.")
    metrics_row_primary(metrics, settings["initial_value"])
    metrics_row_extended(metrics)

    st.markdown("---")
    section_header("Portfolio Insights", "Automated commentary from your allocation and risk metrics.")
    render_insights(insights)

    st.markdown("---")
    section_header("Holdings")
    disp = holdings_df.copy()
    disp["Weight (%)"] = disp["Weight (%)"].map(lambda x: f"{x:.1f}%")
    disp["Value ($)"] = disp["Value ($)"].map(_money)
    st.dataframe(disp, use_container_width=True, hide_index=True)

    c1, c2 = st.columns([1.2, 1])
    with c1:
        section_header("Growth Over Time")
        gdf = growth.reset_index()
        gdf.columns = ["Date", "Portfolio Value"]
        st.plotly_chart(charts.growth_chart(gdf), use_container_width=True)
    with c2:
        section_header("Allocation")
        st.plotly_chart(charts.allocation_chart(holdings_df), use_container_width=True)

    section_header("Rolling Analytics", f"{core.ROLLING_WINDOW}-trading-day window (~3 months).")
    r1, r2 = st.columns(2)
    with r1:
        st.plotly_chart(
            charts.rolling_chart(roll_ret.to_frame("Rolling Return"), "Rolling Annualized Return", "Return"),
            use_container_width=True,
        )
    with r2:
        st.plotly_chart(
            charts.rolling_chart(roll_vol.to_frame("Rolling Volatility"), "Rolling Volatility", "Volatility"),
            use_container_width=True,
        )

# ── Risk Analysis ─────────────────────────────────────────────────────────────

with tab_risk:
    section_header("Correlation Matrix", HELP["correlation"])
    st.plotly_chart(charts.correlation_heatmap(corr), use_container_width=True)

    section_header("Volatility Ranking", "Annualized volatility by holding (highest first).")
    vr = vol_rank.copy()
    vr["Annual Volatility"] = vr["Annual Volatility"].map(_pct)
    st.dataframe(vr, use_container_width=True, hide_index=True)

    section_header("Risk Contribution", "Share of total portfolio risk from each asset.")
    rc = risk_contrib.copy()
    rc["Weight"] = rc["Weight"].map(_pct)
    rc["Risk Contribution (%)"] = rc["Risk Contribution (%)"].map(lambda x: f"{x:.1f}%")
    st.dataframe(rc.drop(columns=["Risk Contribution"]), use_container_width=True, hide_index=True)

    section_header("Scenario Analysis", "Hypothetical 1-year outcomes under return shocks.")
    sd = scenarios.copy()
    sd["Assumed 1Y Return"] = sd["Assumed 1Y Return"].map(_pct)
    sd["Projected Value"] = sd["Projected Value"].map(_money)
    sd["Gain / Loss ($)"] = sd["Gain / Loss ($)"].map(
        lambda x: f"+{_money(x)}" if x >= 0 else f"-{_money(abs(x))}"
    )
    st.dataframe(sd, use_container_width=True, hide_index=True)

# ── Monte Carlo ───────────────────────────────────────────────────────────────

with tab_mc:
    section_header("Monte Carlo Simulation", HELP["monte_carlo"])
    mc1, mc2 = st.columns(2)
    with mc1:
        mc_years = st.slider("Projection years", 1, 15, 5)
    with mc2:
        mc_sims = st.selectbox("Simulations", [200, 500, 1000], index=1)

    with st.spinner("Running simulations…"):
        mc = core.monte_carlo_simulation(
            returns, weights, settings["initial_value"], mc_years, mc_sims
        )

    st.plotly_chart(
        charts.monte_carlo_paths(mc.chart_df, f"Projection paths · {mc_sims:,} simulations · {mc_years}Y"),
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
        m1, m2, m3 = st.columns(3)
        m1.metric("P(Loss)", _pct(s["prob_loss"]), help="Ending below starting value")
        m2.metric("P(2× Money)", _pct(s["prob_double"]))
        m3.metric("Mean Outcome", _money(s["mean"]))
        st.caption(f"**90% confidence interval:** {_money(s['ci_low'])} – {_money(s['ci_high'])}")
        pcols = st.columns(5)
        for col, (lbl, key) in zip(
            pcols,
            [("5th", "p5"), ("25th", "p25"), ("Median", "p50"), ("75th", "p75"), ("95th", "p95")],
        ):
            col.metric(lbl, _money(s[key]))

# ── Optimization ──────────────────────────────────────────────────────────────

with tab_opt:

    def opt_table(res: core.OptimizerResult) -> pd.DataFrame:
        rows = [
            {"Metric": "Strategy", "Value": res.label},
            {"Metric": "Return", "Value": _pct(res.annual_return)},
            {"Metric": "Volatility", "Value": _pct(res.volatility)},
            {"Metric": "Sharpe", "Value": f"{res.sharpe_ratio:.2f}"},
        ]
        for t, w in zip(tickers, res.weights):
            rows.append({"Metric": t, "Value": _pct(w)})
        return pd.DataFrame(rows)

    section_header("Optimizer Results", "Long-only mean-variance optimization on historical data.")
    o1, o2 = st.columns(2)
    with o1:
        st.markdown("**Maximum Sharpe**")
        st.dataframe(opt_table(max_sharpe), use_container_width=True, hide_index=True)
    with o2:
        st.markdown("**Minimum Volatility**")
        st.dataframe(opt_table(min_vol), use_container_width=True, hide_index=True)

    compare = pd.DataFrame(
        {
            "Portfolio": ["Your allocation", max_sharpe.label, min_vol.label],
            "Return": [_pct(metrics.annual_return), _pct(max_sharpe.annual_return), _pct(min_vol.annual_return)],
            "Volatility": [_pct(metrics.volatility), _pct(max_sharpe.volatility), _pct(min_vol.volatility)],
            "Sharpe": [f"{metrics.sharpe_ratio:.2f}", f"{max_sharpe.sharpe_ratio:.2f}", f"{min_vol.sharpe_ratio:.2f}"],
        }
    )
    st.dataframe(compare, use_container_width=True, hide_index=True)

# ── Efficient Frontier ────────────────────────────────────────────────────────

with tab_frontier:
    section_header("Efficient Frontier", HELP["efficient_frontier"])
    st.plotly_chart(
        charts.efficient_frontier_chart(
            frontier,
            (metrics.volatility, metrics.annual_return, metrics.sharpe_ratio),
            (max_sharpe.volatility, max_sharpe.annual_return, max_sharpe.sharpe_ratio, max_sharpe.label),
            (min_vol.volatility, min_vol.annual_return, min_vol.sharpe_ratio, min_vol.label),
        ),
        use_container_width=True,
    )
    st.caption(
        "★ Your portfolio · ◆ Max Sharpe · ■ Min volatility — hover for return and volatility."
    )
