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
BENCHMARK_TICKERS = {
    "SPY": "S&P 500",
    "QQQ": "Nasdaq 100",
    "AGG": "Aggregate Bonds",
    "BIL": "Treasury Bills",
}


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


@dataclass(frozen=True)
class PortfolioExplanation:
    portfolio_overview: list[str]
    risk_analysis: list[str]
    macro_sensitivity: list[str]
    investor_suitability: list[str]
    strengths: list[str]
    weaknesses: list[str]
    suggested_improvements: list[str]
    full_memo: str


@dataclass(frozen=True)
class ForwardMacroAssumptions:
    rate_environment: str
    inflation: str
    recession_probability: float
    valuation: str
    economic_regime: str
    override_equity_return: float | None = None
    override_bond_return: float | None = None
    override_inflation: float | None = None
    override_volatility: float | None = None


@dataclass(frozen=True)
class ForwardProjectionResult:
    adjusted_return: float
    adjusted_volatility: float
    adjusted_sharpe: float
    adjusted_max_drawdown: float
    projected_value: float
    forward_insights: list[str]
    rate_commentary: list[str]
    inflation_commentary: list[str]
    adjusted_mean_returns: np.ndarray
    adjusted_cov: np.ndarray


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
    asset_returns: pd.DataFrame | None = None,
    weights: np.ndarray | None = None,
    initial_value: float | None = None,
    years: int = 10,
    simulations: int = 1000,
    target_value: float | None = None,
    seed: int | None = 42,
    *,
    starting_value: float | None = None,
    annual_return: float | None = None,
    annual_volatility: float | None = None,
    expected_annual_return: float | None = None,
    expected_annual_volatility: float | None = None,
    returns: pd.DataFrame | None = None,
) -> MonteCarloResult:
    """
    Geometric Brownian motion on portfolio returns.

    If `returns` (or `asset_returns`) and `weights` are provided, historical
    daily returns estimate mu/sigma unless overridden by annual_return/volatility.
    Otherwise supply annual_return and annual_volatility directly.
    """
    if returns is not None:
        asset_returns = returns
    start_val = starting_value if starting_value is not None else initial_value
    if start_val is None:
        raise ValueError("starting_value or initial_value is required.")

    ann_ret = annual_return if annual_return is not None else expected_annual_return
    ann_vol = annual_volatility if annual_volatility is not None else expected_annual_volatility

    rng = np.random.default_rng(seed)
    if asset_returns is not None and weights is not None:
        port_rets = portfolio_daily_returns(asset_returns, weights)
        hist_ann_ret = float(port_rets.mean() * TRADING_DAYS)
        hist_ann_vol = float(port_rets.std() * np.sqrt(TRADING_DAYS))
        use_ann_ret = ann_ret if ann_ret is not None else hist_ann_ret
        use_ann_vol = ann_vol if ann_vol is not None else hist_ann_vol
    elif ann_ret is not None and ann_vol is not None:
        use_ann_ret = ann_ret
        use_ann_vol = ann_vol
    else:
        raise ValueError(
            "Provide returns+weights for historical estimation, or annual_return and annual_volatility."
        )

    mu = (1 + use_ann_ret) ** (1 / TRADING_DAYS) - 1
    sigma = use_ann_vol / np.sqrt(TRADING_DAYS)
    days = years * TRADING_DAYS

    paths = np.zeros((simulations, days + 1))
    paths[:, 0] = start_val
    shocks = rng.normal(mu, sigma, size=(simulations, days))
    for t in range(1, days + 1):
        paths[:, t] = paths[:, t - 1] * (1 + shocks[:, t - 1])

    ending = paths[:, -1]
    percentiles = [5, 25, 50, 75, 95]
    summary: dict[str, float] = {f"p{p}": float(np.percentile(ending, p)) for p in percentiles}
    summary["mean"] = float(ending.mean())
    summary["prob_loss"] = float((ending < start_val).mean())
    summary["prob_below_start"] = summary["prob_loss"]
    summary["prob_double"] = float((ending >= start_val * 2).mean())
    goal = target_value if target_value is not None and target_value > 0 else start_val
    summary["target_value"] = float(goal)
    summary["prob_reach_target"] = float((ending >= goal).mean())
    summary["downside_std"] = float(np.std(np.minimum(0, ending / start_val - 1)))
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


def allocation_profile(
    tickers: list[str],
    weights: np.ndarray,
    asset_types: list[str],
) -> dict[str, float | int | str]:
    w = normalize_weights(weights)
    equity = sum(wi for wi, at in zip(w, asset_types) if at in ("Equity", "REIT", "Dividend ETF"))
    bonds = sum(wi for wi, at in zip(w, asset_types) if at == "Bonds")
    tbills = sum(wi for wi, at in zip(w, asset_types) if at == "T-Bills")
    reit = sum(wi for wi, at in zip(w, asset_types) if at == "REIT")
    dividend = sum(wi for wi, at in zip(w, asset_types) if at == "Dividend ETF")
    real_assets = sum(wi for wi, at in zip(w, asset_types) if at in ("REIT", "Other"))
    long_duration_bonds = sum(
        wi for ti, wi in zip(tickers, w) if ti.upper() in {"TLT", "EDV", "VGLT", "ZROZ", "BLV"}
    )
    short_duration_cash = sum(
        wi for ti, wi, at in zip(tickers, w, asset_types) if ti.upper() in {"BIL", "SGOV", "SHY", "SHV"} or at == "T-Bills"
    )
    tech = sum(wi for ti, wi in zip(tickers, w) if ti.upper() in TECH_TICKERS)
    qqq_spy = sum(wi for ti, wi in zip(tickers, w) if ti.upper() in {"QQQ", "SPY"})
    intl = sum(wi for ti, wi in zip(tickers, w) if ti.upper() in {"VXUS", "VEA", "IEFA", "EFA", "IXUS"})
    top_idx = int(np.argmax(w))
    return {
        "equity": float(equity),
        "bonds": float(bonds),
        "tbills": float(tbills),
        "reit": float(reit),
        "dividend": float(dividend),
        "real_assets": float(real_assets),
        "long_duration_bonds": float(long_duration_bonds),
        "short_duration_cash": float(short_duration_cash),
        "tech": float(tech),
        "qqq_spy": float(qqq_spy),
        "intl": float(intl),
        "bond_cash": float(bonds + tbills),
        "concentration": float(w[top_idx]),
        "top_ticker": tickers[top_idx],
        "n_holdings": len(tickers),
    }


def _memo_section(title: str, bullets: list[str]) -> str:
    lines = [title, "-" * len(title)]
    lines.extend(f"• {b}" for b in bullets)
    return "\n".join(lines)


def generate_portfolio_explanation(
    tickers: list[str],
    weights: np.ndarray,
    asset_types: list[str],
    metrics: ExtendedPortfolioMetrics,
    corr: pd.DataFrame,
    risk_contrib: pd.DataFrame,
    benchmark_rets: pd.Series | None = None,
) -> PortfolioExplanation:
    """Generate a structured investment memo from portfolio metrics and allocation."""
    profile = allocation_profile(tickers, weights, asset_types)
    overview: list[str] = []
    risk: list[str] = []
    macro: list[str] = []
    suitability: list[str] = []
    strengths: list[str] = []
    weaknesses: list[str] = []
    improvements: list[str] = []

    eq, bc = profile["equity"], profile["bond_cash"]
    if eq < 0.50 and bc >= 0.40:
        overview.append(
            "This portfolio is moderately conservative with balanced equity and fixed-income exposure."
        )
    elif profile["qqq_spy"] >= 0.35 or profile["tech"] >= 0.40:
        overview.append(
            "The portfolio is growth-oriented due to elevated SPY/QQQ or technology allocations."
        )
    elif profile["tbills"] >= 0.25:
        overview.append("The portfolio emphasizes stability through T-bill and cash-like exposure.")
    elif eq >= 0.75:
        overview.append("This portfolio is equity-heavy and oriented toward long-term capital appreciation.")
    else:
        overview.append("This portfolio blends growth assets with defensive fixed income in a balanced structure.")

    overview.append(
        f"Allocation snapshot: ~{eq*100:.0f}% growth-oriented assets, "
        f"~{profile['bonds']*100:.0f}% bonds, ~{profile['tbills']*100:.0f}% T-bills/cash."
    )

    spy_vol = None
    if benchmark_rets is not None and len(benchmark_rets) > 20:
        spy_vol = annualized_volatility(benchmark_rets)
        if metrics.volatility < spy_vol * 0.90:
            risk.append("Volatility is below the S&P 500, likely due to bond and diversification benefits.")
        elif metrics.volatility > spy_vol * 1.15:
            risk.append("Volatility exceeds the S&P 500, indicating above-market risk-taking.")
        else:
            risk.append("Volatility is broadly in line with the S&P 500.")

    if metrics.volatility < 0.12:
        risk.append(f"Annualized volatility ({metrics.volatility*100:.1f}%) is relatively low for a multi-asset portfolio.")
    elif metrics.volatility > 0.20:
        risk.append(f"Elevated volatility ({metrics.volatility*100:.1f}%) suggests meaningful drawdown potential.")

    if metrics.sharpe_ratio >= 1.0:
        risk.append(f"Sharpe ratio ({metrics.sharpe_ratio:.2f}) indicates strong risk-adjusted returns versus the risk-free rate.")
    elif metrics.sharpe_ratio < 0.5:
        risk.append(
            "A low Sharpe ratio means the portfolio may not be earning enough return for the risk taken."
        )
    else:
        risk.append(f"Sharpe ratio ({metrics.sharpe_ratio:.2f}) is moderate on a historical basis.")

    if metrics.sortino_ratio >= metrics.sharpe_ratio and metrics.sortino_ratio >= 0.8:
        risk.append(f"Sortino ratio ({metrics.sortino_ratio:.2f}) suggests downside risk is relatively contained.")
    elif metrics.sortino_ratio < 0.5:
        risk.append(f"Sortino ratio ({metrics.sortino_ratio:.2f}) highlights meaningful downside volatility.")

    if metrics.beta_spy > 1.1:
        risk.append(f"Beta vs SPY ({metrics.beta_spy:.2f}) implies above-market sensitivity in risk-on environments.")
    elif 0 < metrics.beta_spy < 0.85:
        risk.append(f"Beta below 1.0 ({metrics.beta_spy:.2f}) means the portfolio is less sensitive to the S&P 500.")

    if metrics.max_drawdown < -0.25:
        risk.append(
            f"Maximum drawdown ({metrics.max_drawdown*100:.1f}%) indicates the portfolio has experienced severe peak-to-trough declines."
        )
    if profile["tech"] >= 0.30:
        risk.append("The portfolio may experience elevated drawdowns during technology selloffs.")
    if profile["tbills"] >= 0.20:
        risk.append("A large T-bill allocation reduces market sensitivity and can cushion equity drawdowns.")

    if profile["concentration"] >= 0.35:
        risk.append(
            f"Concentration risk: {profile['top_ticker']} represents {profile['concentration']*100:.1f}% of the portfolio."
        )
    top_risk = risk_contrib.iloc[0]
    risk.append(
        f"{top_risk['Ticker']} contributes {top_risk['Risk Contribution (%)']:.1f}% of total portfolio risk."
    )

    if profile["bonds"] >= 0.25:
        macro.append(
            "High inflation could pressure long-duration bond holdings; shorter-duration and T-bill exposure may be more resilient."
        )
    if profile["qqq_spy"] >= 0.25 or profile["tech"] >= 0.30:
        macro.append(
            "The portfolio may benefit from falling rates because growth exposure is elevated."
        )
        macro.append("Rising rates could weigh on growth stocks and long-duration bonds simultaneously.")
    if profile["tbills"] >= 0.15:
        macro.append("Elevated cash/T-bill exposure may outperform during credit stress and flight-to-quality episodes.")
    if profile["reit"] + profile["real_assets"] >= 0.10:
        macro.append("Real assets and REIT exposure may provide partial inflation hedging over long horizons.")
    if eq >= 0.60:
        macro.append("Recession risk would likely pressure equities; defensive sleeves may partially offset losses.")
    else:
        macro.append("The portfolio appears relatively resilient during recessions because of defensive asset exposure.")
    if profile["tech"] >= 0.25:
        macro.append("An AI/tech-driven expansion could amplify returns but also increase volatility and drawdown risk.")
    if profile["bond_cash"] >= 0.35:
        macro.append("Falling interest rates may support bond prices and reduce portfolio volatility.")
    if not macro:
        macro.append("Macro sensitivity appears balanced across growth, income, and defensive sleeves.")

    if metrics.volatility < 0.14 and bc >= 0.45:
        suitability.append("May be suitable for retirement or capital-preservation-oriented investors.")
    if eq >= 0.65 and metrics.volatility < 0.22:
        suitability.append("Suitable for long-term growth investors with a multi-year horizon.")
    if metrics.volatility > 0.20:
        suitability.append("May be too volatile for short-term cash needs or near-term spending goals.")
    if 0.12 <= metrics.volatility <= 0.18:
        suitability.append("Suitable for moderate-risk investors seeking balanced growth and stability.")
    if profile["tbills"] >= 0.40:
        suitability.append("Appropriate for short-term cash management with limited market exposure.")
    if not suitability:
        suitability.append("Investor fit depends on horizon and liquidity needs; review risk metrics before allocating.")

    if len(corr) >= 2:
        upper = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool))
        max_corr = float(upper.max().max())
        if max_corr < 0.65:
            strengths.append("Diversification benefits appear meaningful across holdings.")
        if max_corr > 0.85:
            weaknesses.append("High pairwise correlation may limit diversification benefits.")

    if profile["n_holdings"] >= 4 and profile["concentration"] < 0.35:
        strengths.append("Holdings are spread across multiple positions, reducing single-name risk.")
    if profile["bond_cash"] >= 0.25 and metrics.volatility < 0.16:
        strengths.append("Defensive positioning helps stabilize volatility relative to pure equity portfolios.")
    if metrics.sharpe_ratio >= 0.8:
        strengths.append("Historical risk-adjusted returns are competitive versus typical balanced portfolios.")
    if profile["intl"] >= 0.10:
        strengths.append("International diversification may improve risk-adjusted return over time.")

    if profile["concentration"] >= 0.40:
        weaknesses.append(f"Concentration in {profile['top_ticker']} increases idiosyncratic risk.")
    if profile["bond_cash"] < 0.10 and metrics.volatility > 0.18:
        weaknesses.append("Insufficient fixed-income exposure for investors seeking drawdown protection.")
    if metrics.annual_return < 0.05 and metrics.volatility > 0.12:
        weaknesses.append("Low expected return relative to volatility may limit long-term wealth accumulation.")
    if metrics.volatility > 0.22:
        weaknesses.append("Excessive volatility may challenge investors with low risk tolerance.")
    if profile["reit"] + profile["real_assets"] < 0.05 and profile["bonds"] > 0.30:
        weaknesses.append("Inflation vulnerability: bond-heavy portfolios can struggle in sustained high-inflation regimes.")
    if metrics.max_drawdown < -0.30:
        weaknesses.append("Historical drawdowns have been severe; recovery periods may be lengthy.")

    if profile["bond_cash"] < 0.20 and metrics.volatility > 0.16:
        improvements.append("Increasing bond exposure could reduce volatility and improve stability.")
    if profile["qqq_spy"] >= 0.40:
        improvements.append("Reducing concentration in QQQ/SPY may lower drawdown risk during growth selloffs.")
    if profile["intl"] < 0.08 and eq > 0.50:
        improvements.append("Adding international diversification may improve risk-adjusted return.")
    if profile["concentration"] >= 0.35:
        improvements.append(f"Consider trimming {profile['top_ticker']} to reduce concentration risk.")
    if metrics.sharpe_ratio < 0.6:
        improvements.append("Rebalancing toward higher Sharpe sleeves (bonds, diversifiers) may improve efficiency.")
    if profile["tbills"] < 0.05 and metrics.beta_spy > 1.1:
        improvements.append("A modest T-bill sleeve could reduce beta and provide liquidity in stress scenarios.")
    if not improvements:
        improvements.append("Current positioning is reasonable; periodic rebalancing remains prudent.")

    sections = [
        _memo_section("Portfolio Overview", overview),
        _memo_section("Risk Analysis", risk),
        _memo_section("Macro Sensitivity", macro),
        _memo_section("Investor Suitability", suitability),
        _memo_section("Strengths", strengths),
        _memo_section("Weaknesses", weaknesses),
        _memo_section("Suggested Improvements", improvements),
    ]
    header = "PORTFOLIO INVESTMENT MEMO\n" + "=" * 52 + "\n"
    full_memo = header + "\n\n".join(sections) + "\n\nDisclaimer: Educational analysis only. Not financial advice."

    return PortfolioExplanation(
        portfolio_overview=overview,
        risk_analysis=risk,
        macro_sensitivity=macro,
        investor_suitability=suitability,
        strengths=strengths,
        weaknesses=weaknesses,
        suggested_improvements=improvements,
        full_memo=full_memo,
    )


def _rate_environment_effects(env: str, profile: dict) -> tuple[float, float, list[str]]:
    ret_shift, vol_mult = 0.0, 1.0
    notes: list[str] = []
    eq, bonds, tbills, reit = profile["equity"], profile["bonds"], profile["tbills"], profile["reit"]
    long_bonds = profile["long_duration_bonds"]
    if env == "Falling Rates":
        ret_shift += 0.025 * eq + 0.045 * bonds + 0.020 * reit - 0.005 * tbills + 0.020 * long_bonds
        vol_mult *= 0.90
        notes.append("Falling rates typically support growth stocks and bonds, with stronger upside for long-duration bonds.")
    elif env == "Rising Rates":
        ret_shift += -0.020 * eq - 0.060 * bonds + 0.020 * tbills - 0.030 * reit - 0.040 * long_bonds
        vol_mult *= 1.20
        notes.append("Rising rates pressure duration-sensitive assets; T-bills become relatively more attractive.")
    elif env == "High Rate Environment":
        ret_shift += -0.030 * eq - 0.070 * bonds + 0.025 * tbills - 0.035 * reit - 0.050 * long_bonds
        vol_mult *= 1.30
        notes.append("Persistently high rates compress equity valuations and can materially hurt long-duration bonds.")
    else:
        notes.append("Stable rates imply modest macro drift; historical relationships may persist.")
    return ret_shift, vol_mult, notes


def _inflation_effects(inflation: str, profile: dict) -> tuple[float, float, list[str]]:
    ret_shift, vol_mult = 0.0, 1.0
    notes: list[str] = []
    long_bonds = profile["long_duration_bonds"]
    cash_like = profile["short_duration_cash"]
    if inflation == "High Inflation":
        ret_shift += (
            -0.080 * profile["bonds"]
            - 0.025 * profile["equity"]
            + 0.030 * profile["real_assets"]
            + 0.020 * profile["tbills"]
            - 0.060 * long_bonds
            + 0.010 * cash_like
        )
        vol_mult *= 1.28
        notes.append("High inflation is punitive for duration: long bonds face larger downside, while T-bills/cash are more defensive.")
    elif inflation == "Deflation":
        ret_shift += 0.030 * profile["bonds"] - 0.030 * profile["equity"] - 0.020 * profile["reit"] + 0.010 * long_bonds
        vol_mult *= 1.22
        notes.append("Deflation can support high-quality bonds but pressure earnings and risk assets.")
    elif inflation == "Low Inflation":
        ret_shift += 0.010 * profile["equity"] + 0.005 * profile["bonds"]
        notes.append("Low inflation is generally supportive for duration and growth assets.")
    else:
        notes.append("Moderate inflation is typically manageable for diversified portfolios.")
    return ret_shift, vol_mult, notes


def _valuation_effects(valuation: str, profile: dict) -> tuple[float, float, list[str]]:
    notes: list[str] = []
    shifts = {"Cheap": 0.02, "Fair Value": 0.0, "Expensive": -0.015, "Bubble-like": -0.03}
    vol_mults = {"Cheap": 0.95, "Fair Value": 1.0, "Expensive": 1.08, "Bubble-like": 1.15}
    shift = shifts.get(valuation, 0.0) * profile["equity"]
    vol_mult = vol_mults.get(valuation, 1.0)
    if valuation in ("Expensive", "Bubble-like"):
        notes.append("The current valuation environment may limit future equity upside and raise drawdown risk.")
    elif valuation == "Cheap":
        notes.append("A cheap valuation backdrop may support above-average forward equity returns.")
    else:
        notes.append("Fair valuations suggest returns may track earnings growth and macro conditions.")
    return shift, vol_mult, notes


def _economic_regime_effects(regime: str, profile: dict) -> tuple[float, float, list[str]]:
    notes: list[str] = []
    long_bonds = profile["long_duration_bonds"]
    mapping = {
        "Expansion": (
            0.020 * profile["equity"] - 0.005 * profile["tbills"],
            0.95,
            "Expansion supports earnings and risk assets, while defensive cash drags upside.",
        ),
        "Slow Growth": (
            -0.020 * profile["equity"] + 0.010 * profile["tbills"] + 0.005 * profile["bonds"],
            1.10,
            "Slow growth pressures cyclicals and favors defensive fixed income.",
        ),
        "Recession": (
            -0.180 * profile["equity"] - 0.030 * profile["reit"] + 0.020 * profile["tbills"] + 0.015 * profile["bonds"],
            1.65,
            "Recession stress materially lowers equity returns and raises volatility/correlation.",
        ),
        "Recovery": (
            0.050 * profile["equity"] - 0.010 * profile["tbills"],
            1.15,
            "Recovery phases typically reward risk assets but volatility often stays elevated.",
        ),
        "Stagflation": (
            -0.100 * profile["equity"] - 0.080 * profile["bonds"] - 0.050 * long_bonds + 0.015 * profile["tbills"],
            1.45,
            "Stagflation is challenging for both equities and bonds; shorter-duration cash is relatively defensive.",
        ),
        "AI / Tech Boom": (
            0.120 * profile["tech"] + 0.030 * profile["equity"] - 0.005 * profile["tbills"],
            1.30,
            "Tech-led expansions can improve returns but often come with higher regime volatility.",
        ),
        "Credit Crisis": (
            -0.220 * profile["equity"] - 0.060 * profile["reit"] + 0.035 * profile["tbills"] - 0.010 * profile["bonds"],
            1.95,
            "Credit crises drive sharp drawdowns, spread widening, and significantly higher realized volatility.",
        ),
    }
    ret_shift, vol_mult, note = mapping.get(regime, (0.0, 1.0, "Regime effects applied to forward assumptions."))
    notes.append(note)
    return ret_shift, vol_mult, notes


def compute_forward_projection_with_profile(
    metrics: ExtendedPortfolioMetrics,
    mean_returns: np.ndarray,
    cov: np.ndarray,
    tickers: list[str],
    weights: np.ndarray,
    asset_types: list[str],
    assumptions: ForwardMacroAssumptions,
    initial_value: float,
    years: float,
    risk_free_rate: float,
) -> ForwardProjectionResult:
    """Forward projection using actual portfolio allocation profile."""
    profile = allocation_profile(tickers, weights, asset_types)
    ret_shift = 0.0
    vol_mult = 1.0

    r1, v1, rate_notes = _rate_environment_effects(assumptions.rate_environment, profile)
    r2, v2, infl_notes = _inflation_effects(assumptions.inflation, profile)
    r3, v3, _ = _valuation_effects(assumptions.valuation, profile)
    r4, v4, regime_notes = _economic_regime_effects(assumptions.economic_regime, profile)
    ret_shift += r1 + r2 + r3 + r4
    vol_mult *= v1 * v2 * v3 * v4

    recession_prob = float(np.clip(assumptions.recession_probability, 0.0, 1.0))
    ret_shift += (
        -0.180 * recession_prob * profile["equity"]
        -0.040 * recession_prob * profile["reit"]
        +0.030 * recession_prob * profile["tbills"]
        +0.010 * recession_prob * profile["bonds"]
    )
    vol_mult *= 1.0 + recession_prob * 0.75
    drawdown_mult = 1.0 + recession_prob * 0.90

    adj_return = metrics.annual_return + ret_shift
    adj_vol = max(0.001, metrics.volatility * vol_mult)

    if assumptions.override_equity_return is not None:
        blended = (
            assumptions.override_equity_return * profile["equity"]
            + (assumptions.override_bond_return or metrics.annual_return) * profile["bonds"]
            + metrics.annual_return * profile["tbills"]
            + metrics.annual_return * profile["dividend"]
        )
        adj_return = blended / max(
            profile["equity"] + profile["bonds"] + profile["tbills"] + profile["dividend"], 0.01
        )
    elif assumptions.override_bond_return is not None:
        adj_return += (assumptions.override_bond_return - metrics.annual_return) * profile["bonds"]
    if assumptions.override_volatility is not None:
        adj_vol = assumptions.override_volatility
    if assumptions.override_inflation is not None and assumptions.override_inflation > 0.04:
        inflation_excess = min(0.08, assumptions.override_inflation - 0.04)
        adj_return -= inflation_excess * (1.20 * profile["bonds"] + 1.50 * profile["long_duration_bonds"])
        adj_vol *= 1.0 + 1.5 * inflation_excess

    adj_sharpe = sharpe_ratio(adj_return, adj_vol, risk_free_rate)
    adj_dd = metrics.max_drawdown * drawdown_mult
    projected = initial_value * (1 + adj_return) ** years

    type_shifts = {"Equity": 0.0, "Bonds": 0.0, "T-Bills": 0.0, "REIT": 0.0, "Dividend ETF": 0.0, "Other": 0.0}
    if assumptions.rate_environment == "Rising Rates":
        type_shifts.update({"Bonds": -0.05, "T-Bills": 0.02, "Equity": -0.02, "REIT": -0.02})
    elif assumptions.rate_environment == "Falling Rates":
        type_shifts.update({"Bonds": 0.03, "T-Bills": -0.005, "Equity": 0.02, "REIT": 0.02})
    if assumptions.inflation == "High Inflation":
        type_shifts.update({"Bonds": -0.06, "T-Bills": 0.015, "REIT": 0.015, "Dividend ETF": -0.005})
    if assumptions.economic_regime == "Recession":
        type_shifts.update({"Equity": type_shifts["Equity"] - 0.10, "REIT": type_shifts["REIT"] - 0.04, "T-Bills": type_shifts["T-Bills"] + 0.02})
    if assumptions.economic_regime == "Credit Crisis":
        type_shifts.update({"Equity": type_shifts["Equity"] - 0.14, "REIT": type_shifts["REIT"] - 0.06, "Bonds": type_shifts["Bonds"] - 0.02, "T-Bills": type_shifts["T-Bills"] + 0.03})
    if assumptions.economic_regime == "AI / Tech Boom":
        type_shifts["Equity"] += 0.06

    adjusted_mean = mean_returns.copy()
    for i, at in enumerate(asset_types):
        adjusted_mean[i] += type_shifts.get(at, 0.0)
    if assumptions.override_equity_return is not None:
        for i, at in enumerate(asset_types):
            if at in ("Equity", "REIT", "Dividend ETF"):
                adjusted_mean[i] = assumptions.override_equity_return
    if assumptions.override_bond_return is not None:
        for i, at in enumerate(asset_types):
            if at in ("Bonds", "T-Bills"):
                adjusted_mean[i] = assumptions.override_bond_return

    vol_scale = adj_vol / max(metrics.volatility, 1e-6)
    corr_stress = 1.0 + recession_prob * 0.30
    adjusted_cov = cov * (vol_scale**2) * corr_stress

    insights: list[str] = list(rate_notes) + list(infl_notes) + list(regime_notes)
    if recession_prob >= 0.5:
        insights.append("High recession probability reduces expected equity returns and raises stress-test volatility.")
        insights.append("Under institutional stress assumptions, recession drawdowns are materially larger for growth-heavy portfolios.")
    if assumptions.inflation == "High Inflation":
        insights.append("Sustained high inflation is modeled as significantly damaging for long-duration bond exposure.")
    if assumptions.rate_environment == "Falling Rates" and profile["equity"] >= 0.50:
        insights.append("Falling-rate environments may improve growth-stock performance.")
    if assumptions.valuation in ("Expensive", "Bubble-like"):
        insights.append("The current valuation environment may limit future upside.")

    return ForwardProjectionResult(
        adjusted_return=adj_return,
        adjusted_volatility=adj_vol,
        adjusted_sharpe=adj_sharpe,
        adjusted_max_drawdown=adj_dd,
        projected_value=projected,
        forward_insights=insights,
        rate_commentary=rate_notes,
        inflation_commentary=infl_notes,
        adjusted_mean_returns=adjusted_mean,
        adjusted_cov=adjusted_cov,
    )
