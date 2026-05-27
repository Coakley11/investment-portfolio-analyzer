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


@st.cache_data(show_spinner=False)
def load_comparison_prices(start: str, end: str | None):
    return core.fetch_price_history(list(core.BENCHMARK_TICKERS), start, end)


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
    [
        "Overview",
        "Portfolio Inputs",
        "Risk Analysis",
        "Explain This Portfolio",
        "Forward-Looking Macro Analysis",
        "Monte Carlo",
        "Optimization",
        "Efficient Frontier",
    ]
)
tab_overview, tab_inputs, tab_risk, tab_explain, tab_forward, tab_mc, tab_opt, tab_frontier = tabs

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
        comp_prices = load_comparison_prices(settings["start"], settings["end"])
        comp_returns_raw = core.daily_returns(comp_prices)
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
            returns,
            weights,
            settings["initial_value"],
            years=5,
            simulations=500,
            target_value=settings["initial_value"] * 1.5,
        )
        synth_6040 = comp_returns_raw["SPY"] * 0.60 + comp_returns_raw["AGG"] * 0.40
        benchmark_returns = pd.DataFrame(
            {
                "Current Portfolio": port_rets,
                "SPY": comp_returns_raw["SPY"],
                "QQQ": comp_returns_raw["QQQ"],
                "60/40": synth_6040,
                "T-Bills": comp_returns_raw["BIL"],
            }
        ).dropna()
        benchmark_table, benchmark_growth = core.benchmark_comparison(
            benchmark_returns,
            settings["initial_value"],
            settings["risk_free"],
        )
        macro_df = core.macro_regime_analysis(
            metrics, settings["initial_value"], years=1, weights=weights, asset_types=asset_types
        )
        explanation = core.generate_portfolio_explanation(
            tickers, weights, asset_types, metrics, corr, risk_contrib, benchmark_rets=bench_rets
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
    section_header(
        "Benchmark Comparison",
        "Compare your portfolio against SPY, QQQ, a 60/40 blend, and a T-bill portfolio.",
    )
    btab = benchmark_table.copy()
    for col in ["Annual Return", "Volatility", "Sharpe Ratio", "Max Drawdown", "CAGR"]:
        if col != "Sharpe Ratio":
            btab[col] = btab[col].map(_pct)
        else:
            btab[col] = btab[col].map(lambda x: f"{x:.2f}")
    btab["Growth of $100,000"] = btab["Growth of $100,000"].map(_money)
    st.dataframe(btab, use_container_width=True, hide_index=True)

    gcmp = benchmark_growth.reset_index().rename(columns={"index": "Date"})
    if "Date" not in gcmp.columns:
        gcmp["Date"] = benchmark_growth.index
    st.plotly_chart(charts.benchmark_growth_chart(gcmp), use_container_width=True)

    st.markdown("---")
    section_header(
        "Portfolio Recommendation Engine",
        "Generate a suggested allocation from age, horizon, risk, liquidity, and objective.",
    )
    r1, r2, r3 = st.columns(3)
    with r1:
        rec_age = st.number_input("Age", min_value=18, max_value=100, value=35)
        rec_horizon = st.slider("Investment horizon (years)", 1, 40, 15)
    with r2:
        rec_risk = st.selectbox("Risk tolerance", ["Low", "Medium", "High"], index=1)
        rec_liq = st.selectbox("Need for liquidity", ["Low", "Medium", "High"], index=1)
    with r3:
        rec_obj = st.selectbox(
            "Objective",
            [
                "capital preservation",
                "balanced growth",
                "aggressive growth",
                "income",
                "retirement",
                "short-term cash management",
            ],
            index=1,
        )
    rec = core.recommend_portfolio(rec_age, rec_horizon, rec_risk, rec_liq, rec_obj)
    alloc_text = " · ".join([f"{k}: {v*100:.1f}%" for k, v in rec.allocation.items()])
    st.caption(f"Suggested mix: {alloc_text}")
    for reason in rec.rationale:
        st.markdown(f"- {reason}")
    rec_df = pd.DataFrame(rec.suggested_holdings)
    st.dataframe(rec_df, use_container_width=True, hide_index=True)
    if st.button("Apply Recommendation", use_container_width=False):
        st.session_state.holdings_df = rec_df
        st.success("Recommended allocation applied to Portfolio Inputs.")
        st.rerun()

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

# ── Explain This Portfolio ─────────────────────────────────────────────────────

with tab_explain:
    section_header(
        "Explain This Portfolio",
        "AI-style memo synthesized from allocation, risk metrics, and macro sensitivity.",
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

    section_header(
        "Macro Regime Engine",
        "Adjusted return, volatility, Sharpe, and projection under major macro scenarios.",
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

# ── Forward-Looking Macro Analysis ─────────────────────────────────────────────

with tab_forward:
    section_header(
        "Forward-Looking Macro Analysis",
        "Set future macro assumptions and propagate them into projections, Monte Carlo, and optimization inputs.",
    )
    f1, f2, f3 = st.columns(3)
    with f1:
        rate_env = st.selectbox(
            "Interest Rate Environment",
            ["Falling Rates", "Stable Rates", "Rising Rates", "High Rate Environment"],
            index=1,
        )
        recession_prob_pct = st.slider("Recession Probability (%)", 0, 100, 25, 5)
    with f2:
        inflation_env = st.selectbox(
            "Inflation Assumption",
            ["Low Inflation", "Moderate Inflation", "High Inflation", "Deflation"],
            index=1,
        )
        valuation_env = st.selectbox(
            "Valuation Environment",
            ["Cheap", "Fair Value", "Expensive", "Bubble-like"],
            index=1,
        )
    with f3:
        econ_regime = st.selectbox(
            "Economic Regime",
            ["Expansion", "Slow Growth", "Recession", "Recovery", "Stagflation", "AI / Tech Boom", "Credit Crisis"],
            index=0,
        )

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

    assumptions = core.ForwardMacroAssumptions(
        rate_environment=rate_env,
        inflation=inflation_env,
        recession_probability=recession_prob_pct / 100.0,
        valuation=valuation_env,
        economic_regime=econ_regime,
        override_equity_return=eq_ret if use_eq else None,
        override_bond_return=bond_ret if use_bond else None,
        override_inflation=exp_infl if use_infl else None,
        override_volatility=exp_vol if use_vol else None,
    )
    fwd_years = st.slider("Forward projection horizon (years)", 1, 15, 5)
    forward = core.compute_forward_projection_with_profile(
        metrics=metrics,
        mean_returns=mean_rets.copy(),
        cov=cov.copy(),
        tickers=tickers,
        weights=weights,
        asset_types=asset_types,
        assumptions=assumptions,
        initial_value=settings["initial_value"],
        years=float(fwd_years),
        risk_free_rate=settings["risk_free"],
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Forward Return", _pct(forward.adjusted_return))
    m2.metric("Forward Volatility", _pct(forward.adjusted_volatility))
    m3.metric("Forward Sharpe", f"{forward.adjusted_sharpe:.2f}")
    m4.metric("Forward Projected Value", _money(forward.projected_value))
    m5, m6 = st.columns(2)
    m5.metric("Forward Max Drawdown", _pct(forward.adjusted_max_drawdown))
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

    section_header("Forward Optimizer Snapshot", "Optimizer outputs under your forward assumptions.")
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

    fmc_years = st.slider("Forward Monte Carlo years", 1, 15, 5, key="fmc_years")
    fmc_sims = st.selectbox("Forward Monte Carlo simulations", [200, 500, 1000], index=1, key="fmc_sims")
    fmc_target = st.number_input(
        "Forward Monte Carlo target value ($)",
        min_value=1_000,
        max_value=25_000_000,
        value=int(settings["initial_value"] * 1.8),
        step=5_000,
        key="fmc_target",
    )
    with st.spinner("Running forward-looking Monte Carlo…"):
        mc_forward = core.monte_carlo_simulation(
            returns,
            weights,
            settings["initial_value"],
            years=fmc_years,
            simulations=fmc_sims,
            target_value=float(fmc_target),
            expected_annual_return=forward.adjusted_return,
            expected_annual_volatility=forward.adjusted_volatility,
        )
    c1, c2 = st.columns([1.15, 1.0])
    with c1:
        st.plotly_chart(
            charts.monte_carlo_paths(
                mc_forward.chart_df,
                f"Forward Paths · {fmc_sims:,} sims · {fmc_years}Y · {econ_regime}",
            ),
            use_container_width=True,
        )
    with c2:
        sf = mc_forward.summary
        st.metric("P(Loss)", _pct(sf["prob_loss"]))
        st.metric("P(Reach Target)", _pct(sf["prob_reach_target"]))
        st.metric("Expected Shortfall", _money(sf["expected_shortfall"]))
        st.caption(f"Median ending value: {_money(sf['p50'])}")

# ── Monte Carlo ───────────────────────────────────────────────────────────────

with tab_mc:
    section_header("Monte Carlo Simulation", HELP["monte_carlo"])
    mc1, mc2 = st.columns(2)
    with mc1:
        mc_years = st.slider("Projection years", 1, 15, 5)
    with mc2:
        mc_sims = st.selectbox("Simulations", [200, 500, 1000], index=1)
        mc_target = st.number_input(
            "Target ending value ($)",
            min_value=1_000,
            max_value=10_000_000,
            value=int(settings["initial_value"] * 1.75),
            step=5_000,
        )

    with st.spinner("Running simulations…"):
        mc = core.monte_carlo_simulation(
            returns, weights, settings["initial_value"], mc_years, mc_sims, target_value=float(mc_target)
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
        m2.metric("P(Below Start)", _pct(s["prob_below_start"]))
        m3.metric("P(Reach Target)", _pct(s["prob_reach_target"]))
        m4, m5, m6 = st.columns(3)
        m4.metric("P(2× Money)", _pct(s["prob_double"]))
        m5.metric("Mean Outcome", _money(s["mean"]))
        m6.metric("Expected Shortfall", _money(s["expected_shortfall"]))
        st.caption(f"**90% confidence interval:** {_money(s['ci_low'])} – {_money(s['ci_high'])}")
        st.caption(f"Target value: {_money(s['target_value'])} · Downside risk estimate: {_pct(s['downside_std'])}")
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
