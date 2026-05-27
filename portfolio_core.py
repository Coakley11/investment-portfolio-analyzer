"""
Core portfolio analytics — calculation logic only.
UI lives in streamlit_app.py; keep formulas stable when changing the dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.optimize import minimize

TRADING_DAYS = 252

# Curated presets for bonds, cash, REITs, and dividend ETFs
ASSET_PRESETS: dict[str, dict[str, str]] = {
    "US Total Bond": {"ticker": "BND", "category": "Bonds"},
    "Long Treasury": {"ticker": "TLT", "category": "Bonds"},
    "Aggregate Bond": {"ticker": "AGG", "category": "Bonds"},
    "T-Bills / Cash": {"ticker": "BIL", "category": "T-Bills"},
    "Short Treasury": {"ticker": "SHV", "category": "T-Bills"},
    "REIT Index": {"ticker": "VNQ", "category": "REIT"},
    "Dividend ETF": {"ticker": "SCHD", "category": "Dividend ETF"},
    "High Dividend": {"ticker": "VYM", "category": "Dividend ETF"},
}

DEFAULT_HOLDINGS = [
    {"Ticker": "VTI", "Weight (%)": 40.0, "Asset Type": "Equity"},
    {"Ticker": "VXUS", "Weight (%)": 20.0, "Asset Type": "Equity"},
    {"Ticker": "BND", "Weight (%)": 30.0, "Asset Type": "Bonds"},
    {"Ticker": "VNQ", "Weight (%)": 10.0, "Asset Type": "REIT"},
]

# Full portfolio allocation presets (sidebar)
PORTFOLIO_PRESETS: dict[str, list[dict]] = {
    "Conservative": [
        {"Ticker": "BND", "Weight (%)": 50.0, "Asset Type": "Bonds"},
        {"Ticker": "VTI", "Weight (%)": 25.0, "Asset Type": "Equity"},
        {"Ticker": "VXUS", "Weight (%)": 10.0, "Asset Type": "Equity"},
        {"Ticker": "BIL", "Weight (%)": 15.0, "Asset Type": "T-Bills"},
    ],
    "Balanced": [
        {"Ticker": "VTI", "Weight (%)": 40.0, "Asset Type": "Equity"},
        {"Ticker": "VXUS", "Weight (%)": 20.0, "Asset Type": "Equity"},
        {"Ticker": "BND", "Weight (%)": 30.0, "Asset Type": "Bonds"},
        {"Ticker": "VNQ", "Weight (%)": 10.0, "Asset Type": "REIT"},
    ],
    "Aggressive": [
        {"Ticker": "VTI", "Weight (%)": 50.0, "Asset Type": "Equity"},
        {"Ticker": "VXUS", "Weight (%)": 25.0, "Asset Type": "Equity"},
        {"Ticker": "QQQ", "Weight (%)": 20.0, "Asset Type": "Equity"},
        {"Ticker": "BND", "Weight (%)": 5.0, "Asset Type": "Bonds"},
    ],
    "Dividend Income": [
        {"Ticker": "SCHD", "Weight (%)": 35.0, "Asset Type": "Dividend ETF"},
        {"Ticker": "VYM", "Weight (%)": 25.0, "Asset Type": "Dividend ETF"},
        {"Ticker": "VNQ", "Weight (%)": 15.0, "Asset Type": "REIT"},
        {"Ticker": "BND", "Weight (%)": 25.0, "Asset Type": "Bonds"},
    ],
    "Tech Growth": [
        {"Ticker": "QQQ", "Weight (%)": 40.0, "Asset Type": "Equity"},
        {"Ticker": "VGT", "Weight (%)": 30.0, "Asset Type": "Equity"},
        {"Ticker": "VTI", "Weight (%)": 20.0, "Asset Type": "Equity"},
        {"Ticker": "BND", "Weight (%)": 10.0, "Asset Type": "Bonds"},
    ],
    "Retirement": [
        {"Ticker": "BND", "Weight (%)": 40.0, "Asset Type": "Bonds"},
        {"Ticker": "VTI", "Weight (%)": 30.0, "Asset Type": "Equity"},
        {"Ticker": "VXUS", "Weight (%)": 15.0, "Asset Type": "Equity"},
        {"Ticker": "SCHD", "Weight (%)": 10.0, "Asset Type": "Dividend ETF"},
        {"Ticker": "BIL", "Weight (%)": 5.0, "Asset Type": "T-Bills"},
    ],
    "All Weather": [
        {"Ticker": "SPY", "Weight (%)": 30.0, "Asset Type": "Equity"},
        {"Ticker": "TLT", "Weight (%)": 40.0, "Asset Type": "Bonds"},
        {"Ticker": "GLD", "Weight (%)": 15.0, "Asset Type": "Other"},
        {"Ticker": "DBC", "Weight (%)": 15.0, "Asset Type": "Other"},
    ],
}

BENCHMARK_TICKER = "SPY"
TECH_TICKERS = frozenset(
    {"QQQ", "VGT", "XLK", "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "NVDA", "META", "TSLA", "ARKK"}
)
ROLLING_WINDOW = 63
BENCHMARK_TICKERS = ("SPY", "QQQ", "AGG", "BIL")


@dataclass(frozen=True)
class PortfolioMetrics:
    annual_return: float
    volatility: float
    sharpe_ratio: float
    projected_value: float


@dataclass(frozen=True)
class ExtendedPortfolioMetrics:
    annual_return: float
    volatility: float
    sharpe_ratio: float
    projected_value: float
    max_drawdown: float
    sortino_ratio: float
    cagr: float
    beta_spy: float


@dataclass(frozen=True)
class MonteCarloResult:
    chart_df: pd.DataFrame
    ending_values: np.ndarray
    summary: dict[str, float]


@dataclass(frozen=True)
class RecommendationResult:
    allocation: dict[str, float]
    rationale: list[str]
    suggested_holdings: list[dict[str, float | str]]


@dataclass(frozen=True)
class OptimizerResult:
    weights: np.ndarray
    annual_return: float
    volatility: float
    sharpe_ratio: float
    label: str


def normalize_weights(weights: Iterable[float]) -> np.ndarray:
    w = np.asarray(list(weights), dtype=float)
    if w.sum() <= 0:
        raise ValueError("Portfolio weights must sum to a positive value.")
    return w / w.sum()


def fetch_price_history(
    tickers: list[str],
    start: str,
    end: str | None = None,
) -> pd.DataFrame:
    """Download adjusted close prices via yfinance."""
    clean = [t.strip().upper() for t in tickers if t and str(t).strip()]
    if not clean:
        raise ValueError("At least one ticker is required.")

    raw = yf.download(
        clean,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
        group_by="column",
    )
    if raw.empty:
        raise ValueError("No price data returned. Check tickers and date range.")

    if isinstance(raw.columns, pd.MultiIndex):
        if "Close" in raw.columns.get_level_values(0):
            prices = raw["Close"]
        elif "Adj Close" in raw.columns.get_level_values(0):
            prices = raw["Adj Close"]
        else:
            prices = raw.xs(raw.columns.levels[0][0], axis=1, level=0)
    else:
        col = "Close" if "Close" in raw.columns else raw.columns[0]
        prices = raw[[col]].rename(columns={col: clean[0]})

    prices = prices.dropna(how="all").ffill().dropna(how="any")
    if prices.empty:
        raise ValueError("Price history is empty after cleaning.")
    return prices


def daily_returns(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.pct_change().dropna()


def annualized_return(daily_rets: pd.Series | pd.DataFrame) -> float:
    return float(daily_rets.mean() * TRADING_DAYS)


def annualized_volatility(daily_rets: pd.Series | pd.DataFrame) -> float:
    return float(daily_rets.std() * np.sqrt(TRADING_DAYS))


def sharpe_ratio(
    ann_return: float,
    ann_vol: float,
    risk_free_rate: float,
) -> float:
    if ann_vol <= 0:
        return 0.0
    return (ann_return - risk_free_rate) / ann_vol


def portfolio_daily_returns(
    asset_returns: pd.DataFrame,
    weights: np.ndarray,
) -> pd.Series:
    w = normalize_weights(weights)
    aligned = asset_returns.iloc[:, : len(w)]
    return (aligned * w).sum(axis=1)


def compute_portfolio_metrics(
    asset_returns: pd.DataFrame,
    weights: np.ndarray,
    risk_free_rate: float,
    initial_value: float,
    years_forward: float = 1.0,
) -> PortfolioMetrics:
    ext = compute_extended_metrics(
        asset_returns, weights, risk_free_rate, initial_value, years_forward
    )
    return PortfolioMetrics(
        annual_return=ext.annual_return,
        volatility=ext.volatility,
        sharpe_ratio=ext.sharpe_ratio,
        projected_value=ext.projected_value,
    )


def maximum_drawdown(port_rets: pd.Series) -> float:
    cumulative = (1 + port_rets).cumprod()
    peak = cumulative.cummax()
    drawdown = (cumulative - peak) / peak
    return float(drawdown.min())


def sortino_ratio(
    port_rets: pd.Series,
    risk_free_rate: float,
) -> float:
    ann_ret = annualized_return(port_rets)
    daily_rf = risk_free_rate / TRADING_DAYS
    excess = port_rets - daily_rf
    downside = excess[excess < 0]
    if len(downside) == 0 or downside.std() == 0:
        return 0.0
    downside_vol = float(downside.std() * np.sqrt(TRADING_DAYS))
    return (ann_ret - risk_free_rate) / downside_vol


def cagr_from_growth(growth: pd.Series) -> float:
    if len(growth) < 2:
        return 0.0
    start_val = float(growth.iloc[0])
    end_val = float(growth.iloc[-1])
    if start_val <= 0:
        return 0.0
    idx = growth.index
    if hasattr(idx[0], "days"):
        years = max((idx[-1] - idx[0]).days / 365.25, 1 / 365.25)
    else:
        years = len(growth) / TRADING_DAYS
    return float((end_val / start_val) ** (1 / years) - 1)


def beta_vs_benchmark(
    port_rets: pd.Series,
    benchmark_rets: pd.Series,
) -> float:
    aligned = pd.concat([port_rets, benchmark_rets], axis=1, join="inner").dropna()
    if len(aligned) < 10:
        return 0.0
    cov = aligned.cov().iloc[0, 1]
    var_bench = aligned.iloc[:, 1].var()
    if var_bench <= 0:
        return 0.0
    return float(cov / var_bench)


def rolling_volatility(port_rets: pd.Series, window: int = ROLLING_WINDOW) -> pd.Series:
    return port_rets.rolling(window).std() * np.sqrt(TRADING_DAYS)


def rolling_returns(port_rets: pd.Series, window: int = ROLLING_WINDOW) -> pd.Series:
    return port_rets.rolling(window).mean() * TRADING_DAYS


def volatility_ranking(asset_returns: pd.DataFrame) -> pd.DataFrame:
    vols = asset_returns.std() * np.sqrt(TRADING_DAYS)
    df = pd.DataFrame(
        {
            "Ticker": vols.index,
            "Annual Volatility": vols.values,
        }
    )
    return df.sort_values("Annual Volatility", ascending=False).reset_index(drop=True)


def risk_contribution(
    asset_returns: pd.DataFrame,
    weights: np.ndarray,
) -> pd.DataFrame:
    w = normalize_weights(weights)
    cov = asset_returns.cov() * TRADING_DAYS
    port_vol = float(np.sqrt(np.dot(w.T, np.dot(cov.values, w))))
    if port_vol <= 0:
        marginal = np.zeros(len(w))
    else:
        marginal = w * (cov.values @ w) / port_vol
    contrib_pct = marginal / marginal.sum() if marginal.sum() > 0 else w
    return pd.DataFrame(
        {
            "Ticker": asset_returns.columns[: len(w)],
            "Weight": w,
            "Risk Contribution": contrib_pct,
            "Risk Contribution (%)": contrib_pct * 100,
        }
    ).sort_values("Risk Contribution (%)", ascending=False)


def compute_extended_metrics(
    asset_returns: pd.DataFrame,
    weights: np.ndarray,
    risk_free_rate: float,
    initial_value: float,
    years_forward: float = 1.0,
    benchmark_rets: pd.Series | None = None,
) -> ExtendedPortfolioMetrics:
    port_rets = portfolio_daily_returns(asset_returns, weights)
    growth = portfolio_growth_series(asset_returns, weights, initial_value)
    ann_ret = annualized_return(port_rets)
    ann_vol = annualized_volatility(port_rets)
    sharpe = sharpe_ratio(ann_ret, ann_vol, risk_free_rate)
    projected = initial_value * (1 + ann_ret) ** years_forward
    beta = 0.0
    if benchmark_rets is not None:
        beta = beta_vs_benchmark(port_rets, benchmark_rets)
    return ExtendedPortfolioMetrics(
        annual_return=ann_ret,
        volatility=ann_vol,
        sharpe_ratio=sharpe,
        projected_value=projected,
        max_drawdown=maximum_drawdown(port_rets),
        sortino_ratio=sortino_ratio(port_rets, risk_free_rate),
        cagr=cagr_from_growth(growth),
        beta_spy=beta,
    )


def correlation_matrix(asset_returns: pd.DataFrame) -> pd.DataFrame:
    return asset_returns.corr()


def portfolio_growth_series(
    asset_returns: pd.DataFrame,
    weights: np.ndarray,
    initial_value: float,
) -> pd.Series:
    port_rets = portfolio_daily_returns(asset_returns, weights)
    growth = (1 + port_rets).cumprod() * initial_value
    growth.name = "Portfolio Value"
    return growth


def holdings_breakdown(
    tickers: list[str],
    weights: np.ndarray,
    asset_types: list[str],
    initial_value: float,
    latest_prices: pd.Series | None = None,
) -> pd.DataFrame:
    w = normalize_weights(weights)
    rows = []
    for i, ticker in enumerate(tickers):
        allocation = float(w[i])
        value = initial_value * allocation
        row = {
            "Ticker": ticker,
            "Asset Type": asset_types[i] if i < len(asset_types) else "Equity",
            "Weight": allocation,
            "Weight (%)": allocation * 100,
            "Value ($)": value,
        }
        if latest_prices is not None and ticker in latest_prices.index:
            price = float(latest_prices[ticker])
            row["Last Price"] = price
            row["Est. Shares"] = value / price if price > 0 else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def _portfolio_stats(weights: np.ndarray, mean_returns: np.ndarray, cov: np.ndarray):
    w = normalize_weights(weights)
    port_return = float(np.dot(w, mean_returns))
    port_vol = float(np.sqrt(np.dot(w.T, np.dot(cov, w))))
    return port_return, port_vol


def optimize_max_sharpe(
    mean_returns: np.ndarray,
    cov: np.ndarray,
    risk_free_rate: float,
    n_assets: int,
) -> OptimizerResult:
    def neg_sharpe(w):
        r, v = _portfolio_stats(w, mean_returns, cov)
        return -sharpe_ratio(r, v, risk_free_rate)

    constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1}
    bounds = tuple((0.0, 1.0) for _ in range(n_assets))
    x0 = np.ones(n_assets) / n_assets
    result = minimize(neg_sharpe, x0, method="SLSQP", bounds=bounds, constraints=constraints)
    w = normalize_weights(result.x)
    r, v = _portfolio_stats(w, mean_returns, cov)
    return OptimizerResult(
        weights=w,
        annual_return=r,
        volatility=v,
        sharpe_ratio=sharpe_ratio(r, v, risk_free_rate),
        label="Maximum Sharpe",
    )


def optimize_min_volatility(
    mean_returns: np.ndarray,
    cov: np.ndarray,
    risk_free_rate: float,
    n_assets: int,
) -> OptimizerResult:
    def vol(w):
        _, v = _portfolio_stats(w, mean_returns, cov)
        return v

    constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1}
    bounds = tuple((0.0, 1.0) for _ in range(n_assets))
    x0 = np.ones(n_assets) / n_assets
    result = minimize(vol, x0, method="SLSQP", bounds=bounds, constraints=constraints)
    w = normalize_weights(result.x)
    r, v = _portfolio_stats(w, mean_returns, cov)
    return OptimizerResult(
        weights=w,
        annual_return=r,
        volatility=v,
        sharpe_ratio=sharpe_ratio(r, v, risk_free_rate),
        label="Minimum Volatility",
    )


def efficient_frontier(
    mean_returns: np.ndarray,
    cov: np.ndarray,
    risk_free_rate: float,
    n_points: int = 25,
) -> pd.DataFrame:
    n = len(mean_returns)
    targets = np.linspace(mean_returns.min(), mean_returns.max(), n_points)
    rows = []

    for target in targets:
        def vol(w):
            _, v = _portfolio_stats(w, mean_returns, cov)
            return v

        constraints = (
            {"type": "eq", "fun": lambda w: np.sum(w) - 1},
            {"type": "eq", "fun": lambda w: np.dot(w, mean_returns) - target},
        )
        bounds = tuple((0.0, 1.0) for _ in range(n))
        x0 = np.ones(n) / n
        res = minimize(vol, x0, method="SLSQP", bounds=bounds, constraints=constraints)
        if not res.success:
            continue
        w = normalize_weights(res.x)
        r, v = _portfolio_stats(w, mean_returns, cov)
        rows.append(
            {
                "Return": r,
                "Volatility": v,
                "Sharpe": sharpe_ratio(r, v, risk_free_rate),
            }
        )
    return pd.DataFrame(rows)


def monte_carlo_simulation(
    asset_returns: pd.DataFrame,
    weights: np.ndarray,
    initial_value: float,
    years: int,
    simulations: int,
    target_value: float | None = None,
    seed: int | None = 42,
) -> MonteCarloResult:
    """Geometric Brownian motion on portfolio daily returns."""
    rng = np.random.default_rng(seed)
    port_rets = portfolio_daily_returns(asset_returns, weights)
    mu = port_rets.mean()
    sigma = port_rets.std()
    days = years * TRADING_DAYS

    paths = np.zeros((simulations, days + 1))
    paths[:, 0] = initial_value
    shocks = rng.normal(mu, sigma, size=(simulations, days))
    for t in range(1, days + 1):
        paths[:, t] = paths[:, t - 1] * (1 + shocks[:, t - 1])

    ending = paths[:, -1]
    percentiles = [5, 25, 50, 75, 95]
    summary: dict[str, float] = {f"p{p}": float(np.percentile(ending, p)) for p in percentiles}
    summary["mean"] = float(ending.mean())
    summary["prob_loss"] = float((ending < initial_value).mean())
    summary["prob_below_start"] = summary["prob_loss"]
    summary["prob_double"] = float((ending >= initial_value * 2).mean())
    goal = target_value if target_value is not None and target_value > 0 else initial_value
    summary["target_value"] = float(goal)
    summary["prob_reach_target"] = float((ending >= goal).mean())
    summary["downside_std"] = float(np.std(np.minimum(0, ending / initial_value - 1)))
    bad_tail = ending[ending <= summary["p5"]]
    summary["expected_shortfall"] = float(bad_tail.mean()) if len(bad_tail) else float(summary["p5"])
    summary["ci_low"] = summary["p5"]
    summary["ci_high"] = summary["p95"]

    step = max(1, days // 250)
    idx = list(range(0, days + 1, step))
    chart_df = pd.DataFrame({"Day": idx})
    for p in percentiles:
        chart_df[f"{p}th Percentile"] = np.percentile(paths[:, idx], p, axis=0)
    chart_df["Median"] = np.median(paths[:, idx], axis=0)

    return MonteCarloResult(chart_df=chart_df, ending_values=ending, summary=summary)


def generate_portfolio_insights(
    tickers: list[str],
    weights: np.ndarray,
    asset_types: list[str],
    metrics: ExtendedPortfolioMetrics,
    corr: pd.DataFrame,
    risk_contrib: pd.DataFrame,
) -> list[str]:
    """Rule-based portfolio commentary (no external AI API)."""
    insights: list[str] = []
    w = normalize_weights(weights)
    equity_weight = float(
        sum(
            wi
            for wi, at in zip(w, asset_types)
            if at in ("Equity", "REIT", "Dividend ETF")
        )
    )
    bond_cash_weight = float(
        sum(wi for wi, at in zip(w, asset_types) if at in ("Bonds", "T-Bills"))
    )

    if metrics.volatility < 0.12:
        insights.append("This portfolio has relatively low volatility compared with broad equity portfolios.")
    elif metrics.volatility < 0.18:
        insights.append("This portfolio has moderate volatility compared with a broad equity portfolio.")
    else:
        insights.append("This portfolio has higher volatility than many balanced portfolios.")

    top_idx = int(np.argmax(w))
    top_ticker = tickers[top_idx]
    if w[top_idx] >= 0.35:
        insights.append(
            f"Portfolio is heavily concentrated in **{top_ticker}** "
            f"({w[top_idx]*100:.1f}% weight). Consider spreading risk across more holdings."
        )

    tech_weight = sum(
        wi for ti, wi in zip(tickers, w) if ti.upper() in TECH_TICKERS
    )
    if tech_weight >= 0.40:
        insights.append(
            f"Portfolio is heavily weighted toward **tech** (~{tech_weight*100:.0f}%). "
            "Tech rallies help returns but can amplify drawdowns."
        )

    bond_weight = sum(
        wi
        for ti, wi, at in zip(tickers, w, asset_types)
        if at in ("Bonds", "T-Bills") or ti.upper() in ("BND", "AGG", "TLT", "BIL", "SHV")
    )
    if bond_weight >= 0.20:
        insights.append(
            f"Bond/cash allocation (~{bond_weight*100:.0f}%) **reduces volatility** "
            f"versus an all-equity mix (current vol: {metrics.volatility*100:.1f}%)."
        )
    elif bond_weight < 0.05 and metrics.volatility > 0.18:
        insights.append(
            "Low fixed-income allocation — portfolio volatility is relatively high. "
            "Adding bonds may smooth the ride."
        )

    if metrics.sharpe_ratio >= 1.0:
        insights.append(
            f"Sharpe ratio of **{metrics.sharpe_ratio:.2f}** suggests solid risk-adjusted returns "
            "relative to the risk-free rate."
        )
    elif metrics.sharpe_ratio < 0.5:
        insights.append(
            f"A low Sharpe ratio (**{metrics.sharpe_ratio:.2f}**) means the portfolio may not be earning enough return for the risk taken."
        )

    if len(corr) >= 2:
        upper = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool))
        max_corr = upper.max().max()
        if max_corr > 0.85:
            insights.append(
                "Some holdings are **highly correlated** (>0.85). Diversification benefits may be limited."
            )
        elif max_corr < 0.50:
            insights.append(
                "Holdings show **moderate correlation** — diversification may be helping stabilize returns."
            )

    if metrics.max_drawdown < -0.25:
        insights.append(
            f"Maximum drawdown of **{metrics.max_drawdown*100:.1f}%** indicates significant "
            "historical peak-to-trough declines."
        )

    if metrics.beta_spy > 1.15:
        insights.append(
            f"Beta vs SPY of **{metrics.beta_spy:.2f}** — portfolio tends to move more than the broad market."
        )
    elif 0 < metrics.beta_spy < 0.85:
        insights.append(
            f"Beta below 1.0 (**{metrics.beta_spy:.2f}**) means the portfolio is less sensitive to the S&P 500."
        )

    if equity_weight >= 0.75:
        insights.append(f"High equity allocation (~{equity_weight*100:.0f}%) supports growth potential but can increase drawdowns.")
    elif equity_weight <= 0.45:
        insights.append(f"Lower equity allocation (~{equity_weight*100:.0f}%) may reduce upside but can improve stability.")

    if bond_cash_weight >= 0.30:
        insights.append(
            f"A large bond/T-bill allocation (~{bond_cash_weight*100:.0f}%) may be reducing drawdowns."
        )

    qqq_spy_weight = sum(wi for ti, wi in zip(tickers, w) if ti.upper() in {"QQQ", "SPY"})
    if qqq_spy_weight >= 0.35:
        insights.append(
            f"High QQQ/SPY exposure (~{qqq_spy_weight*100:.0f}%) increases growth potential but may increase drawdowns."
        )

    if metrics.sortino_ratio < metrics.sharpe_ratio and metrics.sortino_ratio < 0.7:
        insights.append(
            f"Sortino ratio (**{metrics.sortino_ratio:.2f}**) indicates downside volatility is a meaningful driver of risk."
        )

    top_risk = risk_contrib.iloc[0]
    insights.append(
        f"**{top_risk['Ticker']}** contributes the most to total risk "
        f"({top_risk['Risk Contribution (%)']:.1f}% of portfolio risk)."
    )

    if not insights:
        insights.append("Portfolio metrics are within typical ranges for a diversified allocation.")
    return insights


def build_summary_report(
    tickers: list[str],
    weights: np.ndarray,
    metrics: ExtendedPortfolioMetrics,
    mc_summary: dict[str, float] | None,
    insights: list[str],
    settings: dict,
) -> str:
    lines = [
        "INVESTMENT PORTFOLIO ANALYZER — SUMMARY REPORT",
        "=" * 52,
        f"Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "SETTINGS",
        f"  Period: {settings.get('start')} → {settings.get('end')}",
        f"  Portfolio value: ${settings.get('initial_value', 0):,.0f}",
        f"  Risk-free rate: {settings.get('risk_free', 0)*100:.2f}%",
        "",
        "HOLDINGS",
    ]
    for t, w in zip(tickers, normalize_weights(weights)):
        lines.append(f"  {t}: {w*100:.1f}%")
    lines.extend(
        [
            "",
            "KEY METRICS",
            f"  Annual return:     {metrics.annual_return*100:.2f}%",
            f"  Volatility:        {metrics.volatility*100:.2f}%",
            f"  Sharpe ratio:      {metrics.sharpe_ratio:.2f}",
            f"  Sortino ratio:     {metrics.sortino_ratio:.2f}",
            f"  CAGR:              {metrics.cagr*100:.2f}%",
            f"  Max drawdown:      {metrics.max_drawdown*100:.2f}%",
            f"  Beta vs SPY:       {metrics.beta_spy:.2f}",
            f"  Projected (1Y):    ${metrics.projected_value:,.0f}",
        ]
    )
    if mc_summary:
        lines.extend(
            [
                "",
                "MONTE CARLO (ending values)",
                f"  Median:            ${mc_summary.get('p50', 0):,.0f}",
                f"  90% CI:            ${mc_summary.get('p5', 0):,.0f} – ${mc_summary.get('p95', 0):,.0f}",
                f"  P(loss):           {mc_summary.get('prob_loss', 0)*100:.1f}%",
                f"  P(2× money):       {mc_summary.get('prob_double', 0)*100:.1f}%",
            ]
        )
    lines.extend(["", "INSIGHTS"])
    for item in insights:
        lines.append(f"  • {item.replace('**', '')}")
    lines.append("")
    lines.append("Disclaimer: Educational tool only. Not financial advice.")
    return "\n".join(lines)


def scenario_analysis(
    asset_returns: pd.DataFrame,
    weights: np.ndarray,
    initial_value: float,
    scenarios: dict[str, float] | None = None,
) -> pd.DataFrame:
    """
    Apply one-period return shocks to the portfolio.
    shocks are annualized decimal returns (e.g. -0.20 = -20%).
    """
    if scenarios is None:
        scenarios = {
            "Base Case (historical ann.)": annualized_return(
                portfolio_daily_returns(asset_returns, weights)
            ),
            "Mild Downturn (-10%)": -0.10,
            "Bear Market (-20%)": -0.20,
            "Strong Rally (+15%)": 0.15,
            "Stagflation (-5% / high vol)": -0.05,
        }

    rows = []
    for name, shock in scenarios.items():
        ending = initial_value * (1 + shock)
        rows.append(
            {
                "Scenario": name,
                "Assumed 1Y Return": shock,
                "Projected Value": ending,
                "Gain / Loss ($)": ending - initial_value,
            }
        )
    return pd.DataFrame(rows)


def benchmark_comparison(
    benchmark_returns: pd.DataFrame,
    initial_value: float,
    risk_free_rate: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    aligned = benchmark_returns.dropna().copy()
    if aligned.empty:
        raise ValueError("Benchmark returns are empty.")

    growth = (1 + aligned).cumprod() * initial_value
    growth.columns = [c.upper() for c in growth.columns]
    rows: list[dict[str, float | str]] = []

    for name in growth.columns:
        series = aligned[name]
        ann_ret = annualized_return(series)
        ann_vol = annualized_volatility(series)
        sharpe = sharpe_ratio(ann_ret, ann_vol, risk_free_rate)
        one_growth = pd.Series([initial_value, *growth[name].values])
        rows.append(
            {
                "Portfolio": name,
                "Annual Return": ann_ret,
                "Volatility": ann_vol,
                "Sharpe Ratio": sharpe,
                "Max Drawdown": maximum_drawdown(series),
                "CAGR": cagr_from_growth(one_growth),
                "Growth of $100,000": float(initial_value * (growth[name].iloc[-1] / initial_value)),
            }
        )

    return pd.DataFrame(rows), growth


def macro_regime_analysis(
    metrics: ExtendedPortfolioMetrics,
    initial_value: float,
    years: int,
    weights: np.ndarray,
    asset_types: list[str],
) -> pd.DataFrame:
    type_weights = {
        "equity": 0.0,
        "bonds": 0.0,
        "tbills": 0.0,
        "real_assets": 0.0,
    }
    for wi, at in zip(normalize_weights(weights), asset_types):
        key = "equity"
        if at == "Bonds":
            key = "bonds"
        elif at == "T-Bills":
            key = "tbills"
        elif at in ("REIT", "Other"):
            key = "real_assets"
        type_weights[key] += float(wi)

    regimes = {
        "Base Case": {"ret_shift": 0.0, "vol_mult": 1.0},
        "Recession": {"ret_shift": -0.08 * type_weights["equity"] + 0.01 * type_weights["tbills"], "vol_mult": 1.35},
        "High Inflation": {"ret_shift": -0.04 * type_weights["bonds"] + 0.02 * type_weights["real_assets"], "vol_mult": 1.20},
        "Falling Interest Rates": {"ret_shift": 0.03 * type_weights["bonds"] + 0.02 * type_weights["equity"], "vol_mult": 0.90},
        "Rising Interest Rates": {"ret_shift": -0.05 * type_weights["bonds"] - 0.02 * type_weights["equity"] + 0.02 * type_weights["tbills"], "vol_mult": 1.15},
        "AI / Tech Boom": {"ret_shift": 0.07 * type_weights["equity"], "vol_mult": 1.18},
        "Credit Crisis": {"ret_shift": -0.10 * type_weights["equity"] - 0.03 * type_weights["real_assets"], "vol_mult": 1.50},
        "Stagflation": {"ret_shift": -0.06 * type_weights["equity"] - 0.04 * type_weights["bonds"] + 0.01 * type_weights["tbills"], "vol_mult": 1.30},
    }

    rows: list[dict[str, float | str]] = []
    for regime, adj in regimes.items():
        adj_ret = metrics.annual_return + float(adj["ret_shift"])
        adj_vol = max(0.001, metrics.volatility * float(adj["vol_mult"]))
        adj_sharpe = sharpe_ratio(adj_ret, adj_vol, 0.0)
        proj = initial_value * (1 + adj_ret) ** years
        rows.append(
            {
                "Regime": regime,
                "Adjusted Return": adj_ret,
                "Adjusted Volatility": adj_vol,
                "Adjusted Sharpe": adj_sharpe,
                "Adjusted Projected Value": proj,
            }
        )
    return pd.DataFrame(rows)


def recommend_portfolio(
    age: int,
    horizon_years: int,
    risk_tolerance: str,
    liquidity_need: str,
    objective: str,
) -> RecommendationResult:
    risk_map = {"Low": 0.35, "Medium": 0.60, "High": 0.80}
    liq_penalty = {"Low": 0.00, "Medium": 0.08, "High": 0.18}
    objective_overrides = {
        "capital preservation": {"equity": 0.20, "bonds": 0.45, "tbills": 0.35},
        "balanced growth": {"equity": 0.60, "bonds": 0.30, "tbills": 0.10},
        "aggressive growth": {"equity": 0.85, "bonds": 0.10, "tbills": 0.05},
        "income": {"equity": 0.40, "bonds": 0.40, "tbills": 0.20},
        "retirement": {"equity": 0.45, "bonds": 0.40, "tbills": 0.15},
        "short-term cash management": {"equity": 0.10, "bonds": 0.20, "tbills": 0.70},
    }

    base_equity = risk_map.get(risk_tolerance, 0.60)
    age_adjust = max(0, age - 40) * 0.004
    horizon_boost = min(0.15, max(0, horizon_years - 8) * 0.01)
    equity = np.clip(base_equity - age_adjust + horizon_boost - liq_penalty.get(liquidity_need, 0.0), 0.10, 0.90)
    bonds = np.clip(0.70 - equity, 0.05, 0.65)
    tbills = float(max(0.05, 1 - equity - bonds))
    mix = {"equity": float(equity), "bonds": float(bonds), "tbills": float(tbills)}

    obj = objective.strip().lower()
    if obj in objective_overrides:
        mix = objective_overrides[obj]

    total = sum(mix.values())
    mix = {k: float(v / total) for k, v in mix.items()}

    rationale = [
        f"Age {age} and a {horizon_years}-year horizon suggest {'higher' if mix['equity'] >= 0.6 else 'moderate/lower'} equity exposure.",
        f"Risk tolerance '{risk_tolerance}' and liquidity need '{liquidity_need}' shape the bond and T-bill buffer.",
        f"Objective '{objective}' influences emphasis on growth, income, or capital stability.",
    ]

    suggested_holdings = [
        {"Ticker": "VTI", "Weight (%)": round(mix["equity"] * 0.55 * 100, 1), "Asset Type": "Equity"},
        {"Ticker": "QQQ", "Weight (%)": round(mix["equity"] * 0.25 * 100, 1), "Asset Type": "Equity"},
        {"Ticker": "VXUS", "Weight (%)": round(mix["equity"] * 0.20 * 100, 1), "Asset Type": "Equity"},
        {"Ticker": "BND", "Weight (%)": round(mix["bonds"] * 0.70 * 100, 1), "Asset Type": "Bonds"},
        {"Ticker": "TLT", "Weight (%)": round(mix["bonds"] * 0.30 * 100, 1), "Asset Type": "Bonds"},
        {"Ticker": "BIL", "Weight (%)": round(mix["tbills"] * 0.60 * 100, 1), "Asset Type": "T-Bills"},
        {"Ticker": "SGOV", "Weight (%)": round(mix["tbills"] * 0.25 * 100, 1), "Asset Type": "T-Bills"},
        {"Ticker": "SHY", "Weight (%)": round(mix["tbills"] * 0.15 * 100, 1), "Asset Type": "T-Bills"},
    ]
    if obj in ("income", "retirement"):
        suggested_holdings.append({"Ticker": "SCHD", "Weight (%)": 8.0, "Asset Type": "Dividend ETF"})
        suggested_holdings.append({"Ticker": "VNQ", "Weight (%)": 5.0, "Asset Type": "REIT"})

    df = pd.DataFrame(suggested_holdings)
    df["Weight (%)"] = df["Weight (%)"].astype(float)
    df = df[df["Weight (%)"] > 0].copy()
    df["Weight (%)"] = (df["Weight (%)"] / df["Weight (%)"].sum() * 100).round(1)

    alloc = {
        "Equity": float(df[df["Asset Type"] == "Equity"]["Weight (%)"].sum() / 100),
        "Bonds": float(df[df["Asset Type"] == "Bonds"]["Weight (%)"].sum() / 100),
        "T-Bills": float(df[df["Asset Type"] == "T-Bills"]["Weight (%)"].sum() / 100),
    }
    return RecommendationResult(
        allocation=alloc,
        rationale=rationale,
        suggested_holdings=df.to_dict(orient="records"),
    )
