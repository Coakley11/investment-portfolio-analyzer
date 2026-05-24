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


@dataclass(frozen=True)
class PortfolioMetrics:
    annual_return: float
    volatility: float
    sharpe_ratio: float
    projected_value: float


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
    port_rets = portfolio_daily_returns(asset_returns, weights)
    ann_ret = annualized_return(port_rets)
    ann_vol = annualized_volatility(port_rets)
    sharpe = sharpe_ratio(ann_ret, ann_vol, risk_free_rate)
    projected = initial_value * (1 + ann_ret) ** years_forward
    return PortfolioMetrics(
        annual_return=ann_ret,
        volatility=ann_vol,
        sharpe_ratio=sharpe,
        projected_value=projected,
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
    seed: int | None = 42,
) -> tuple[pd.DataFrame, dict[str, float]]:
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

    percentiles = [5, 25, 50, 75, 95]
    summary = {f"p{p}": float(np.percentile(paths[:, -1], p)) for p in percentiles}
    summary["mean"] = float(paths[:, -1].mean())

    # Downsample for chart performance
    step = max(1, days // 250)
    idx = list(range(0, days + 1, step))
    median_path = np.median(paths[:, idx], axis=0)
    p5_path = np.percentile(paths[:, idx], 5, axis=0)
    p95_path = np.percentile(paths[:, idx], 95, axis=0)

    chart_df = pd.DataFrame(
        {
            "Day": idx,
            "Median": median_path,
            "5th Percentile": p5_path,
            "95th Percentile": p95_path,
        }
    )
    return chart_df, summary


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
