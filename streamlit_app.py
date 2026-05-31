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
from components.getting_started_guide import render_getting_started_guide
from components.problem_solving import render_problem_solving_lab

APP_DISCLAIMER = "Educational model-based analysis, not financial advice."

# ── Page config & styling ─────────────────────────────────────────────────────

st.set_page_config(
    page_title="Daniel Cohen Investment Portfolio Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

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
        gap: 0.35rem;
        border-bottom: 1px solid var(--dc-border);
        margin-bottom: 0.35rem;
    }
    button[data-baseweb="tab"] {
        background-color: transparent;
        border-radius: 8px 8px 0 0;
        color: #94a3b8;
        font-weight: 500;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        background: linear-gradient(180deg, #1a2840 0%, #152238 100%);
        color: #f8fafc;
        border: 1px solid var(--dc-border);
        border-bottom-color: transparent;
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


def render_branded_header():
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
def load_comparison_prices(start: str, end: str | None):
    return core.fetch_price_history(list(core.BENCHMARK_TICKERS), start, end)


@st.cache_data(show_spinner=False)
def compute_daily_returns(prices: pd.DataFrame):
    return core.daily_returns(prices)


@st.cache_data(show_spinner=False)
def compute_risk_pack(returns: pd.DataFrame, weights_tuple: tuple[float, ...], initial_value: float):
    weights = np.asarray(weights_tuple, dtype=float)
    port_rets = core.portfolio_daily_returns(returns, weights)
    return {
        "corr": core.correlation_matrix(returns),
        "scenarios": core.scenario_analysis(returns, weights, initial_value),
        "vol_rank": core.volatility_ranking(returns),
        "risk_contrib": core.risk_contribution(returns, weights),
        "roll_vol": core.rolling_volatility(port_rets),
        "roll_ret": core.rolling_returns(port_rets),
        "port_rets": port_rets,
    }


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
):
    weights = np.asarray(weights_tuple, dtype=float)
    return core.monte_carlo_simulation(
        returns=returns,
        weights=weights,
        initial_value=initial_value,
        years=years,
        simulations=simulations,
        target_value=target_value,
        expected_annual_return=expected_annual_return,
        expected_annual_volatility=expected_annual_volatility,
    )


def render_insights(insights: list[str]):
    for text in insights:
        plain = text.replace("**", "")
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


def cache_health_summary(health: core.PortfolioHealthResult, tickers: list[str], weights: np.ndarray) -> None:
    st.session_state.health_summary = {
        "score": float(health.score),
        "score_label": health.score_label,
        "score_color": health.score_color,
        "fingerprint": _portfolio_fingerprint(tickers, weights),
    }


def get_health_badge_state(tickers: list[str], weights: np.ndarray) -> tuple[str, dict | None]:
    summary = st.session_state.get("health_summary")
    if not summary:
        return "missing", None
    if summary.get("fingerprint") != _portfolio_fingerprint(tickers, weights):
        return "stale", None
    return "ok", summary


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
    else:
        html = f"""
        <div class="health-header-badge health-header-badge-neutral">
            <span>🩺 <strong>Portfolio Health</strong></span>
            <span class="health-header-prompt">Run Portfolio Health analysis for updated score.</span>
            <span class="health-header-note">{disclaimer}</span>
        </div>
        """
    slot.markdown(html, unsafe_allow_html=True)


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
    st.sidebar.caption(APP_DISCLAIMER)
    st.sidebar.divider()
    st.sidebar.markdown("### Performance")
    mode = st.sidebar.radio("Analysis mode", ["Fast mode", "Full analysis mode"], index=0)
    frontier_points = st.sidebar.select_slider(
        "Frontier granularity",
        options=[200, 500, 1000, 2000],
        value=2000,
        help="Lower values run faster. 2,000 is default institutional setting.",
    )

    return {
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "initial_value": float(initial_value),
        "risk_free": float(risk_free),
        "portfolio_preset": portfolio_preset,
        "asset_preset": asset_preset,
        "mode": mode,
        "frontier_points": int(frontier_points),
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

render_branded_header()
health_badge_slot = st.empty()

settings = render_sidebar()
init_holdings()
apply_asset_preset(settings["asset_preset"])

tabs = st.tabs(
    [
        "Getting Started Guide",
        "Overview",
        "Portfolio Inputs",
        "Risk Analysis",
        "Portfolio Health",
        "Explain This Portfolio",
        "Forward-Looking Macro Analysis",
        "Monte Carlo",
        "Optimization",
        "Efficient Frontier",
        "Math Problem Solving Lab",
    ]
)
(
    tab_guide,
    tab_overview,
    tab_inputs,
    tab_risk,
    tab_health,
    tab_explain,
    tab_forward,
    tab_mc,
    tab_opt,
    tab_frontier,
    tab_problem_lab,
) = tabs

with tab_guide:
    section_header(
        "Getting Started Guide",
        f"Step-by-step tutorial for building, analyzing, and monitoring your portfolio. {APP_DISCLAIMER}",
    )
    render_getting_started_guide()

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
        returns = compute_daily_returns(prices)
        mean_rets = returns.mean().values * core.TRADING_DAYS
        cov = returns.cov() * core.TRADING_DAYS
        metrics = core.compute_extended_metrics(
            returns, weights, settings["risk_free"], settings["initial_value"], benchmark_rets=bench_rets
        )
        growth = core.portfolio_growth_series(returns, weights, settings["initial_value"])
    except Exception as ex:
        st.error(f"Analysis failed: {ex}")
        st.stop()

mc_summary = st.session_state.get("mc_cached_summary")

latest = prices.iloc[-1]
holdings_df = core.holdings_breakdown(tickers, weights, asset_types, settings["initial_value"], latest)
base_risk_pack = compute_risk_pack(returns, tuple(weights.tolist()), settings["initial_value"])
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

# ── Overview ──────────────────────────────────────────────────────────────────

with tab_overview:
    section_header("Portfolio Summary", f"Historical risk/return based on daily returns. {APP_DISCLAIMER}")
    metrics_row_primary(metrics, settings["initial_value"])
    metrics_row_extended(metrics)
    fast_mode = settings["mode"] == "Fast mode"
    if fast_mode:
        st.info("Fast mode is active: advanced analytics are deferred until you switch to Full analysis mode.")

    st.markdown("---")
    if not fast_mode:
        section_header("Portfolio Insights", "Automated commentary from your allocation and risk metrics.")
        render_insights(insights)

    if not fast_mode:
        st.markdown("---")
        section_header(
            "Benchmark Comparison",
            "Compare your portfolio against SPY, QQQ, a 60/40 blend, and a T-bill portfolio.",
        )
        if st.button("Run Benchmark Comparison", key="run_benchmark_btn"):
            st.session_state.run_benchmark = True
        if st.session_state.get("run_benchmark", False):
            with st.spinner("Loading benchmark comparison…"):
                comp_prices = load_comparison_prices(settings["start"], settings["end"])
                comp_returns_raw = compute_daily_returns(comp_prices)
                port_rets = core.portfolio_daily_returns(returns, weights)
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
        else:
            st.caption("Benchmark analytics are on-demand to speed initial app load.")

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

    if not fast_mode:
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

# ── Explain This Portfolio ─────────────────────────────────────────────────────

with tab_explain:
    section_header(
        "Explain This Portfolio",
        f"AI-style memo synthesized from allocation, risk metrics, and macro sensitivity. {APP_DISCLAIMER}",
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
    fast_mode = settings["mode"] == "Fast mode"
    if fast_mode:
        st.info("Risk Analysis is disabled in Fast mode. Switch to Full analysis mode to run advanced risk sections.")
    else:
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

# ── Portfolio Health ──────────────────────────────────────────────────────────

with tab_health:
    section_header(
        "Portfolio Health Monitor",
        f"Model-based evaluation of performance, risk, drift, and macro fit. {APP_DISCLAIMER}",
    )
    if st.button("Refresh Portfolio Health", key="refresh_health_btn", type="primary"):
        st.session_state.health_refresh = st.session_state.get("health_refresh", 0) + 1
        st.session_state.run_health = True

    h1, h2, h3 = st.columns(3)
    with h1:
        health_rate = st.selectbox(
            "Interest Rate Environment",
            ["Falling Rates", "Stable Rates", "Rising Rates", "High Rate Environment"],
            index=1,
            key="health_rate_env",
        )
        health_recession = st.slider("Recession Probability (%)", 0, 100, 25, 5, key="health_recession")
    with h2:
        health_inflation = st.selectbox(
            "Inflation Assumption",
            ["Low Inflation", "Moderate Inflation", "High Inflation", "Deflation"],
            index=1,
            key="health_inflation",
        )
        health_valuation = st.selectbox(
            "Valuation Environment",
            ["Cheap", "Fair Value", "Expensive", "Bubble-like"],
            index=1,
            key="health_valuation",
        )
    with h3:
        health_regime = st.selectbox(
            "Economic Regime",
            ["Expansion", "Slow Growth", "Recession", "Recovery", "Stagflation", "AI / Tech Boom", "Credit Crisis"],
            index=0,
            key="health_regime",
        )
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
            value=not (settings["mode"] == "Fast mode"),
            key="health_run_optimizer",
        )

    if not st.session_state.get("run_health", False):
        st.info("Click **Refresh Portfolio Health** to run the health analysis with your current settings.")
    else:
        health_assumptions = core.ForwardMacroAssumptions(
            rate_environment=health_rate,
            inflation=health_inflation,
            recession_probability=health_recession / 100.0,
            valuation=health_valuation,
            economic_regime=health_regime,
        )
        opt_weights = None
        if health_run_optimizer:
            with st.spinner("Running optimizer for drift comparison…"):
                opt_pack = compute_optimizer_pack(tuple(mean_rets.tolist()), cov, settings["risk_free"])
                opt_weights = opt_pack["max_sharpe"].weights

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
            )
        cache_health_summary(health, tickers, weights)

        st.markdown(
            f'<div class="insight-card">📋 <b>Status:</b> {health.status_message}</div>',
            unsafe_allow_html=True,
        )

        section_header("Portfolio Health Score", "Composite score from return, risk, diversification, objective, and macro fit.")
        sc1, sc2 = st.columns([1, 2])
        with sc1:
            render_health_score_card(health)
        with sc2:
            breakdown_df = pd.DataFrame(
                {"Component": list(health.score_breakdown.keys()), "Points": list(health.score_breakdown.values())}
            )
            st.dataframe(breakdown_df, use_container_width=True, hide_index=True)

        section_header("What's Working / What's Not", "Model-identified positives and areas to monitor.")
        wn1, wn2 = st.columns(2)
        with wn1:
            st.markdown("**What's Working**")
            for item in health.whats_working:
                st.markdown(f'<div class="health-working">✓ {item}</div>', unsafe_allow_html=True)
        with wn2:
            st.markdown("**What's Not Working**")
            for item in health.whats_not_working:
                st.markdown(f'<div class="health-not">⚠ {item}</div>', unsafe_allow_html=True)

        section_header("Allocation Drift / Rebalancing Suggestions", "Compare current weights to objective, optimizer, and recommended mixes.")
        st.dataframe(health.rebalance_df, use_container_width=True, hide_index=True)
        drift_notes = health.rebalance_df[health.rebalance_df["Model Note"] != "Within tolerance"]["Model Note"].tolist()
        if drift_notes:
            for note in drift_notes[:6]:
                st.markdown(f"- *{note}* (for educational purposes)")
        else:
            st.caption("No material drift detected vs objective/optimizer in the model.")

        section_header("Macro Environment Fit", "Commentary based on your macro assumptions and portfolio mix.")
        for note in health.macro_fit:
            st.markdown(f"- {note}")
        st.markdown("**Model-based considerations**")
        for note in health.recommendations:
            st.markdown(f"- {note}")

        section_header("Visual Portfolio Diagnostics", "Return/risk contributions, allocation comparison, macro sensitivity, and benchmark view.")
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
                mini = pd.DataFrame({"Date": port_rets.index})
                mini["Portfolio"] = settings["initial_value"] * (1 + port_rets).cumprod()
                for bc in cmp_rets.columns:
                    if bc.upper() in ("SPY", "QQQ"):
                        mini[bc.upper()] = settings["initial_value"] * (1 + cmp_rets[bc]).cumprod()
                st.plotly_chart(charts.benchmark_mini_chart(mini), use_container_width=True)
            except Exception:
                mini = pd.DataFrame({"Date": growth.index, "Portfolio": growth.values})
                st.plotly_chart(charts.benchmark_mini_chart(mini, title="Portfolio Growth"), use_container_width=True)

        st.caption(
            f"Portfolio Health outputs are rule-based and model-driven. {APP_DISCLAIMER} "
            "Refresh after changing tickers, weights, or macro settings."
        )

# ── Forward-Looking Macro Analysis ─────────────────────────────────────────────

with tab_forward:
    fast_mode = settings["mode"] == "Fast mode"
    if fast_mode:
        st.info("Forward-Looking Macro Analysis is disabled in Fast mode.")
    else:
        if st.button("Run Forward-Looking Macro Analysis", key="run_forward_macro_btn"):
            st.session_state.run_forward_macro = True
    if not fast_mode and st.session_state.get("run_forward_macro", False):
        section_header(
            "Forward-Looking Macro Analysis",
            f"Set future macro assumptions and propagate them into projections, Monte Carlo, and optimization inputs. {APP_DISCLAIMER}",
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
    elif not fast_mode:
        st.caption("Forward macro analysis is on-demand for faster initial load.")

# ── Monte Carlo ───────────────────────────────────────────────────────────────

with tab_mc:
    section_header("Monte Carlo Simulation", f"{HELP['monte_carlo']} {APP_DISCLAIMER}")
    fast_mode = settings["mode"] == "Fast mode"
    if fast_mode:
        st.info("Monte Carlo is disabled in Fast mode.")
    else:
        if st.button("Run Monte Carlo", key="run_mc_btn"):
            st.session_state.run_mc = True
        if st.session_state.get("run_mc", False):
            mc1, mc2 = st.columns(2)
            with mc1:
                mc_years = st.slider("Projection years", 1, 15, 5)
            with mc2:
                mc_sims = st.selectbox("Simulations", [200, 500, 1000], index=2)
                mc_target = st.number_input(
                    "Target ending value ($)",
                    min_value=1_000,
                    max_value=10_000_000,
                    value=int(settings["initial_value"] * 1.75),
                    step=5_000,
                )
            with st.spinner("Running Monte Carlo…"):
                mc = compute_monte_carlo(
                    returns,
                    tuple(weights.tolist()),
                    settings["initial_value"],
                    mc_years,
                    mc_sims,
                    float(mc_target),
                )
            st.session_state.mc_cached_summary = mc.summary
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
        else:
            st.caption("Monte Carlo runs on demand to keep first load fast.")

# ── Optimization ──────────────────────────────────────────────────────────────

with tab_opt:
    fast_mode = settings["mode"] == "Fast mode"
    if fast_mode:
        st.info("Optimization is disabled in Fast mode.")
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
        for t, w in zip(tickers, res.weights):
            rows.append({"Metric": t, "Value": _pct(w)})
        return pd.DataFrame(rows)

    if not fast_mode and st.session_state.get("run_optimizer", False):
        section_header("Optimizer Results", "Long-only mean-variance optimization on historical data.")
        with st.spinner("Optimizing portfolio…"):
            opt = compute_optimizer_pack(tuple(mean_rets.tolist()), cov, settings["risk_free"])
        max_sharpe = opt["max_sharpe"]
        min_vol = opt["min_vol"]
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
    elif not fast_mode:
        st.caption("Optimizer runs on demand.")

# ── Efficient Frontier ────────────────────────────────────────────────────────

with tab_frontier:
    fast_mode = settings["mode"] == "Fast mode"
    if fast_mode:
        st.info("Efficient frontier is disabled in Fast mode.")
    else:
        if st.button("Build Efficient Frontier", key="run_frontier_btn"):
            st.session_state.run_frontier = True
    if not fast_mode and st.session_state.get("run_frontier", False):
        section_header("Efficient Frontier", HELP["efficient_frontier"])
        with st.spinner("Building efficient frontier…"):
            frontier = compute_frontier(
                tuple(mean_rets.tolist()),
                cov,
                settings["risk_free"],
                settings["frontier_points"],
            )
            opt = compute_optimizer_pack(tuple(mean_rets.tolist()), cov, settings["risk_free"])
            max_sharpe = opt["max_sharpe"]
            min_vol = opt["min_vol"]
        st.plotly_chart(
            charts.efficient_frontier_chart(
                frontier,
                (metrics.volatility, metrics.annual_return, metrics.sharpe_ratio),
                (max_sharpe.volatility, max_sharpe.annual_return, max_sharpe.sharpe_ratio, max_sharpe.label),
                (min_vol.volatility, min_vol.annual_return, min_vol.sharpe_ratio, min_vol.label),
            ),
            use_container_width=True,
        )
        st.caption("★ Your portfolio · ◆ Max Sharpe · ■ Min volatility — hover for return and volatility.")
    elif not fast_mode:
        st.caption("Frontier construction is on demand.")

# ── Math Problem Solving Lab ──────────────────────────────────────────────────

with tab_problem_lab:
    section_header(
        "Mathematical Problem Solving Lab",
        f"Practice portfolio math with guided exercises and formula reference. {APP_DISCLAIMER}",
    )
    render_problem_solving_lab()

# ── Header health badge (cached; no heavy health calc on load) ─────────────────

render_health_header_badge(health_badge_slot, tickers, weights)
