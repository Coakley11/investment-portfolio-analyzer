"""
Core portfolio analytics — calculation logic only.
UI lives in streamlit_app.py; keep formulas stable when changing the dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd
from scipy.optimize import minimize

TRADING_DAYS = 252

# Curated presets for bonds, cash, REITs, and dividend ETFs
ASSET_PRESETS: dict[str, dict[str, str]] = {
    "Total US Stock": {"ticker": "VTI", "category": "Equity"},
    "International Stock": {"ticker": "VXUS", "category": "Equity"},
    "US Total Bond": {"ticker": "BND", "category": "Bonds"},
    "Long Treasury": {"ticker": "TLT", "category": "Bonds"},
    "Aggregate Bond": {"ticker": "AGG", "category": "Bonds"},
    "T-Bills / Cash": {"ticker": "BIL", "category": "T-Bills"},
    "Short Treasury": {"ticker": "SHV", "category": "T-Bills"},
    "REIT Index": {"ticker": "VNQ", "category": "REIT"},
    "Dividend ETF": {"ticker": "SCHD", "category": "Dividend ETF"},
    "High Dividend": {"ticker": "VYM", "category": "Dividend ETF"},
}

# Beginner quick-add row on the Portfolio tab (ticker order: VTI, BND, VYM, SCHD, VXUS, VNQ)
COMMON_ETF_QUICK_ADD: tuple[str, ...] = (
    "Total US Stock",
    "US Total Bond",
    "High Dividend",
    "Dividend ETF",
    "International Stock",
    "REIT Index",
)

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

# One-click loaders on the Portfolio tab (label → PORTFOLIO_PRESETS key).
PORTFOLIO_QUICK_LOADERS: dict[str, str] = {
    "Balanced": "Balanced",
    "Growth": "Aggressive",
    "Tech": "Tech Growth",
    "Dividend": "Dividend Income",
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


@dataclass(frozen=True)
class RecommendationDetail:
    text: str
    issue: str
    why_it_matters: str
    triggered_by: str
    possible_benefit: str
    evidence: dict[str, str]
    # Option C: core = actionable allocation/plan; diagnostic = context only;
    # macro = Environment / Macro coaching (not Core Health allocation).
    rec_class: str = "core"


REC_CLASS_CORE = "core"
REC_CLASS_DIAGNOSTIC = "diagnostic"
REC_CLASS_MACRO = "macro"


@dataclass(frozen=True)
class PortfolioActionPlan:
    headline: str
    today: list[str]
    this_month: list[str]
    this_year: list[str]


@dataclass(frozen=True)
class PortfolioHealthResult:
    score: float
    score_label: str
    score_color: str
    status_message: str
    whats_working: list[str]
    whats_not_working: list[str]
    recommendations: list[str]
    recommendation_details: list[RecommendationDetail]
    action_plan: PortfolioActionPlan
    macro_fit: list[str]
    rebalance_df: pd.DataFrame
    return_contrib_df: pd.DataFrame
    risk_contrib_df: pd.DataFrame
    drawdown_contrib_df: pd.DataFrame
    allocation_compare_df: pd.DataFrame
    macro_heatmap_df: pd.DataFrame
    score_breakdown: dict[str, float]
    avg_drift: float
    objective: str
    policy_benchmark_label: str = ""
    policy_benchmark_detail: str = ""
    max_pairwise_abs_corr: float = 0.0
    # Option C transparency / diagnostics (not part of Core Health points)
    pillar_explanations: dict[str, str] = field(default_factory=dict)
    construction_subscores: dict[str, float] = field(default_factory=dict)
    health_diagnostics: dict[str, float] = field(default_factory=dict)
    macro_check_score: float = 0.0
    macro_check_max: float = 10.0


OBJECTIVE_ALLOCATIONS: dict[str, dict[str, float]] = {
    "capital preservation": {"equity": 0.20, "bonds": 0.45, "tbills": 0.35},
    "balanced growth": {"equity": 0.60, "bonds": 0.30, "tbills": 0.10},
    "aggressive growth": {"equity": 0.85, "bonds": 0.10, "tbills": 0.05},
    "income": {"equity": 0.40, "bonds": 0.40, "tbills": 0.20},
    "retirement": {"equity": 0.45, "bonds": 0.40, "tbills": 0.15},
    "short-term cash management": {"equity": 0.10, "bonds": 0.20, "tbills": 0.70},
}

# Proxies for objective-aware Health Return vs Policy Benchmark (must exist in market data).
POLICY_BENCHMARK_PROXIES: dict[str, str] = {
    "equity": "SPY",
    "bonds": "AGG",
    "tbills": "BIL",
}

_INTL_EQUITY_TICKERS = frozenset({"VXUS", "VEA", "IEFA", "EFA", "IXUS", "VWO", "IEMG", "ACWX"})


def policy_benchmark_proxy_tickers() -> tuple[str, ...]:
    return tuple(POLICY_BENCHMARK_PROXIES.values())


def build_policy_benchmark_returns(
    proxy_returns: pd.DataFrame,
    objective: str,
) -> tuple[pd.Series | None, dict[str, Any]]:
    """
    Build a date-aligned policy benchmark return series from objective category weights.

    Uses SPY (equity), AGG (bonds), BIL (T-Bills). Returns (None, meta) when any
    required proxy column is missing or the aligned series is too short — callers
    must not silently fall back to 100% SPY for Health scoring.
    """
    targets = _objective_type_targets(objective)
    meta: dict[str, Any] = {
        "objective": objective.strip().lower(),
        "weights": {
            "equity": float(targets["equity"]),
            "bonds": float(targets["bonds"]),
            "tbills": float(targets["tbills"]),
        },
        "proxies": dict(POLICY_BENCHMARK_PROXIES),
        "ok": False,
        "n_obs": 0,
    }
    if proxy_returns is None or getattr(proxy_returns, "empty", True):
        meta["error"] = "empty_proxy_returns"
        return None, meta

    col_map = {str(c).strip().upper(): c for c in proxy_returns.columns}
    pieces: list[pd.Series] = []
    for sleeve, proxy in POLICY_BENCHMARK_PROXIES.items():
        raw = col_map.get(proxy.upper())
        if raw is None:
            meta["error"] = f"missing_proxy:{proxy}"
            return None, meta
        pieces.append(proxy_returns[raw].rename(proxy.upper()))

    aligned = pd.concat(pieces, axis=1, join="inner").dropna(how="any")
    if len(aligned) < 6:
        meta["error"] = "insufficient_aligned_observations"
        meta["n_obs"] = int(len(aligned))
        return None, meta

    w_eq = float(targets["equity"])
    w_bond = float(targets["bonds"])
    w_tb = float(targets["tbills"])
    series = (
        w_eq * aligned["SPY"]
        + w_bond * aligned["AGG"]
        + w_tb * aligned["BIL"]
    )
    series.name = "policy_benchmark"
    meta["ok"] = True
    meta["n_obs"] = int(len(series))
    meta["label"] = (
        f"Policy ({meta['objective']}: "
        f"{w_eq * 100:.0f}% SPY / {w_bond * 100:.0f}% AGG / {w_tb * 100:.0f}% BIL)"
    )
    meta["detail"] = (
        f"Objective-aware policy benchmark = "
        f"{w_eq * 100:.0f}% equity (SPY) + {w_bond * 100:.0f}% bonds (AGG) + "
        f"{w_tb * 100:.0f}% T-Bills (BIL), date-aligned."
    )
    return series, meta


def score_return_vs_policy_benchmark(
    portfolio_returns: pd.Series,
    policy_returns: pd.Series | None,
) -> tuple[float, float, float, int]:
    """
    Policy-relative performance pillar (0–20).

    Uses the same gap thresholds as the legacy 15-point ladder, rescaled to a
    20-point maximum so the Option C core Health total remains 100.

    Returns (s_return, port_ann, policy_ann, n_aligned) on an explicit date
    intersection — never falls back to 100% SPY.
    """
    if policy_returns is None or portfolio_returns is None:
        return 0.0, 0.0, 0.0, 0
    port = portfolio_returns.copy()
    pol = policy_returns.copy()
    if not isinstance(port.index, pd.DatetimeIndex):
        port.index = pd.to_datetime(port.index)
    if not isinstance(pol.index, pd.DatetimeIndex):
        pol.index = pd.to_datetime(pol.index)
    aligned = pd.concat([port.rename("port"), pol.rename("policy")], axis=1, join="inner").dropna()
    n = int(len(aligned))
    if n < 6:
        return 0.0, 0.0, 0.0, n
    port_ann = annualized_return(aligned["port"])
    policy_ann = annualized_return(aligned["policy"])
    ret_gap = port_ann - policy_ann
    # Legacy 15-pt ladder × (20/15), expressed as explicit 20-pt thresholds.
    if ret_gap >= 0.02:
        s_return = 20.0
    elif ret_gap >= 0:
        s_return = 16.0
    elif ret_gap >= -0.02:
        s_return = float(8.0 * 20.0 / 15.0)  # ≈ 10.667
    elif ret_gap >= -0.05:
        s_return = float(4.0 * 20.0 / 15.0)  # ≈ 5.333
    else:
        s_return = 0.0
    return float(s_return), float(port_ann), float(policy_ann), n


# Alias used by Option C naming in Health UI / tests.
score_policy_relative_performance = score_return_vs_policy_benchmark


HEALTH_CORE_PILLAR_MAX: dict[str, float] = {
    "Policy / Objective Fit": 30.0,
    "Portfolio Construction": 30.0,
    "Risk Appropriateness": 20.0,
    "Policy-Relative Performance": 20.0,
}
HEALTH_CONSTRUCTION_DIV_MAX = 15.0
HEALTH_CONSTRUCTION_CONC_MAX = 15.0
# Bump when Health diagnostic key schema changes (forces session cache refresh).
HEALTH_DIAGNOSTICS_SCHEMA_VERSION = 3
# Visible on Health diagnostics so live vs local provenance is unambiguous.
HEALTH_RUNTIME_BUILD_ID = "2026-09-06-health-provenance-v1"


def health_runtime_provenance() -> str:
    """Short branch@sha (best-effort) plus HEALTH_RUNTIME_BUILD_ID."""
    sha = "unknown"
    branch = "unknown"
    try:
        import subprocess

        sha = (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            or "unknown"
        )
        branch = (
            subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            or "unknown"
        )
    except Exception:
        pass
    return f"{branch}@{sha} · {HEALTH_RUNTIME_BUILD_ID}"


def normalize_health_diagnostics_schema_version(value: Any) -> int | None:
    """
    Coerce a stored/current Health diagnostics schema version for comparison.

    Accepts int/float/numeric strings. Missing, blank, bool, NaN, or malformed
    values return None (treat as outdated / invalidate).
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if value != value:  # NaN
            return None
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(float(text))
        except ValueError:
            return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def health_diagnostics_schema_is_current(diagnostics: Any) -> bool:
    """True when diagnostics carry the current HEALTH_DIAGNOSTICS_SCHEMA_VERSION."""
    if not isinstance(diagnostics, dict):
        return False
    stored = normalize_health_diagnostics_schema_version(
        diagnostics.get("_schema_version")
    )
    current = normalize_health_diagnostics_schema_version(
        HEALTH_DIAGNOSTICS_SCHEMA_VERSION
    )
    if stored is None or current is None:
        return False
    return stored == current


# Diversification / concentration engines still score 0–12 internally.
_HEALTH_DIV_ENGINE_MAX = 12.0
_HEALTH_CONC_ENGINE_MAX = 12.0


def score_policy_objective_fit(
    profile: dict[str, float],
    objective: str,
) -> tuple[float, dict[str, Any]]:
    """
    Policy / Objective Fit pillar (0–30).

    Category drift vs OBJECTIVE_ALLOCATIONS (equity / bonds / tbills). Same
    avg_drift definition as the legacy 0–12 Objective Alignment score, rescaled
    to 30: ``clip(30 − avg_drift × 75, 0, 30)`` (zero at avg_drift = 0.40).
    """
    obj_targets = _objective_type_targets(objective)
    eq_drift = abs(float(profile["equity"]) - obj_targets["equity"])
    bond_drift = abs(float(profile["bonds"]) - obj_targets["bonds"])
    tbill_drift = abs(float(profile["tbills"]) - obj_targets["tbills"])
    avg_drift = (eq_drift + bond_drift + tbill_drift) / 3.0
    points = float(np.clip(30.0 - avg_drift * 75.0, 0.0, 30.0))
    return points, {
        "avg_drift": float(avg_drift),
        "equity_drift": float(eq_drift),
        "bond_drift": float(bond_drift),
        "tbill_drift": float(tbill_drift),
        "targets": dict(obj_targets),
        "current": {
            "equity": float(profile["equity"]),
            "bonds": float(profile["bonds"]),
            "tbills": float(profile["tbills"]),
        },
        "points": points,
        "max_points": HEALTH_CORE_PILLAR_MAX["Policy / Objective Fit"],
    }


def score_portfolio_construction(
    tickers: Sequence[str],
    weights: np.ndarray,
    asset_types: Sequence[str],
    corr: pd.DataFrame,
) -> tuple[float, dict[str, Any]]:
    """
    Portfolio Construction pillar (0–30) = Diversification (0–15) + Concentration (0–15).

    Scales the existing 0–12 diversification and kind-aware concentration engines
    by 15/12. Max pairwise correlation remains diagnostic only (inside div_diag).
    """
    s_div_engine, div_diag = score_portfolio_diversification(
        tickers, weights, asset_types, corr
    )
    s_conc_engine, conc_diag = score_concentration_risk_kind_aware(
        tickers, weights, asset_types
    )
    s_div = float(s_div_engine) * (HEALTH_CONSTRUCTION_DIV_MAX / _HEALTH_DIV_ENGINE_MAX)
    s_conc = float(s_conc_engine) * (HEALTH_CONSTRUCTION_CONC_MAX / _HEALTH_CONC_ENGINE_MAX)
    total = float(np.clip(s_div + s_conc, 0.0, 30.0))
    return total, {
        "diversification_pts": s_div,
        "diversification_max": HEALTH_CONSTRUCTION_DIV_MAX,
        "concentration_pts": s_conc,
        "concentration_max": HEALTH_CONSTRUCTION_CONC_MAX,
        "div_engine_pts": float(s_div_engine),
        "conc_engine_pts": float(s_conc_engine),
        "div_diag": div_diag,
        "conc_diag": conc_diag,
        "points": total,
        "max_points": HEALTH_CORE_PILLAR_MAX["Portfolio Construction"],
    }


def score_risk_appropriateness(
    portfolio_returns: pd.Series,
    policy_returns: pd.Series | None,
    *,
    vol_max_pts: float = 16.0,
    dd_max_pts: float = 4.0,
) -> tuple[float, dict[str, Any]]:
    """
    Risk Appropriateness pillar (0–20) — policy-relative, objective-aware.

    Compares portfolio risk to the **same objective policy benchmark** (SPY/AGG/BIL
    mix) over identical date-aligned observations. Absolute volatility ladders are
    intentionally not used: Capital Preservation and Aggressive Growth are judged
    against their own policy risk, not a shared vol threshold.

    Formula
    -------
    Align ``portfolio_returns`` and ``policy_returns`` (inner join, dropna).
    Require ≥ 6 observations; otherwise score 0.

    **Volatility subscore (0–16)** — ``r = port_vol / policy_vol``
    (annualized stdev × √252 on the aligned window):

    - |r − 1| ≤ 0.15 → 16
    - |r − 1| ≤ 0.30 → 12
    - |r − 1| ≤ 0.50 → 8
    - |r − 1| ≤ 0.75 → 4
    - else → 0

    If ``policy_vol`` ≤ 0: award 0 unless ``port_vol`` is also ≈ 0 (then full 16).

    **Drawdown subscore (0–4)** — policy-relative only (not absolute DD grades):
    ``excess = |port_dd| / |policy_dd|`` on the aligned window:

    - excess ≤ 1.15 → 4
    - excess ≤ 1.35 → 2
    - else → 0

    If ``|policy_dd|`` ≈ 0: award 4 when ``|port_dd|`` ≈ 0, else 0.

    **Total** = vol_pts + dd_pts, clipped to 20.

    Historical max drawdown remains a visible diagnostic outside this grade.
    """
    max_total = float(vol_max_pts + dd_max_pts)
    empty = {
        "ok": False,
        "n_aligned": 0,
        "port_vol": 0.0,
        "policy_vol": 0.0,
        "vol_ratio": float("nan"),
        "vol_pts": 0.0,
        "port_dd": 0.0,
        "policy_dd": 0.0,
        "dd_excess": float("nan"),
        "dd_pts": 0.0,
        "points": 0.0,
        "max_points": max_total,
        "vol_max_pts": float(vol_max_pts),
        "dd_max_pts": float(dd_max_pts),
    }
    if policy_returns is None or portfolio_returns is None:
        return 0.0, empty
    port = portfolio_returns.copy()
    pol = policy_returns.copy()
    if not isinstance(port.index, pd.DatetimeIndex):
        port.index = pd.to_datetime(port.index)
    if not isinstance(pol.index, pd.DatetimeIndex):
        pol.index = pd.to_datetime(pol.index)
    aligned = pd.concat([port.rename("port"), pol.rename("policy")], axis=1, join="inner").dropna()
    n = int(len(aligned))
    if n < 6:
        empty["n_aligned"] = n
        return 0.0, empty

    port_vol = annualized_volatility(aligned["port"])
    policy_vol = annualized_volatility(aligned["policy"])
    port_dd = maximum_drawdown(aligned["port"])
    policy_dd = maximum_drawdown(aligned["policy"])

    if policy_vol <= 1e-12:
        vol_ratio = 1.0 if port_vol <= 1e-12 else float("inf")
        vol_pts = float(vol_max_pts) if port_vol <= 1e-12 else 0.0
    else:
        vol_ratio = float(port_vol / policy_vol)
        abs_dev = abs(vol_ratio - 1.0)
        if abs_dev <= 0.15:
            vol_pts = float(vol_max_pts)
        elif abs_dev <= 0.30:
            vol_pts = float(vol_max_pts) * 0.75
        elif abs_dev <= 0.50:
            vol_pts = float(vol_max_pts) * 0.50
        elif abs_dev <= 0.75:
            vol_pts = float(vol_max_pts) * 0.25
        else:
            vol_pts = 0.0

    pol_dd_mag = abs(float(policy_dd))
    port_dd_mag = abs(float(port_dd))
    if pol_dd_mag <= 1e-12:
        dd_excess = 1.0 if port_dd_mag <= 1e-12 else float("inf")
        dd_pts = float(dd_max_pts) if port_dd_mag <= 1e-12 else 0.0
    else:
        dd_excess = float(port_dd_mag / pol_dd_mag)
        if dd_excess <= 1.15:
            dd_pts = float(dd_max_pts)
        elif dd_excess <= 1.35:
            dd_pts = float(dd_max_pts) * 0.5
        else:
            dd_pts = 0.0

    total = float(np.clip(vol_pts + dd_pts, 0.0, max_total))
    return total, {
        "ok": True,
        "n_aligned": n,
        "port_vol": float(port_vol),
        "policy_vol": float(policy_vol),
        "vol_ratio": float(vol_ratio) if np.isfinite(vol_ratio) else float("nan"),
        "vol_pts": float(vol_pts),
        "port_dd": float(port_dd),
        "policy_dd": float(policy_dd),
        "dd_excess": float(dd_excess) if np.isfinite(dd_excess) else float("nan"),
        "dd_pts": float(dd_pts),
        "points": total,
        "max_points": max_total,
        "vol_max_pts": float(vol_max_pts),
        "dd_max_pts": float(dd_max_pts),
    }


def compute_macro_environment_check(
    profile: dict[str, float],
    assumptions: ForwardMacroAssumptions,
) -> tuple[float, list[str]]:
    """
    Environment / Macro Check (0–10) — diagnostic only; never added to Core Health.

    Same rule logic as the former Macro Regime Fit Health component.
    """
    s_macro = 5.0
    recession_prob = assumptions.recession_probability
    notes: list[str] = []
    if assumptions.rate_environment == "Falling Rates" and float(profile["equity"]) >= 0.45:
        s_macro += 1.5
    if assumptions.rate_environment in ("Rising Rates", "High Rate Environment") and float(profile["tbills"]) >= 0.10:
        s_macro += 1.5
    if assumptions.inflation == "High Inflation" and float(profile["long_duration_bonds"]) <= 0.15:
        s_macro += 1.0
    elif assumptions.inflation == "High Inflation" and float(profile["long_duration_bonds"]) > 0.25:
        s_macro -= 1.5
    if recession_prob >= 0.5 and float(profile["equity"]) <= 0.55:
        s_macro += 1.0
    elif recession_prob >= 0.5 and float(profile["equity"]) > 0.70:
        s_macro -= 2.0
    if assumptions.economic_regime == "AI / Tech Boom" and float(profile["tech"]) >= 0.15:
        s_macro += 1.0
    if assumptions.economic_regime == "Credit Crisis" and float(profile["tbills"]) >= 0.15:
        s_macro += 1.0
    s_macro = float(np.clip(s_macro, 0, 10))

    if assumptions.rate_environment == "Falling Rates":
        notes.append(
            "Falling-rate assumptions can support longer-duration bonds and rate-sensitive equities in this model."
        )
    if assumptions.rate_environment in ("Rising Rates", "High Rate Environment"):
        notes.append(
            "Rising/high-rate assumptions may favor shorter duration and cash-like buffers in stress scenarios."
        )
    if assumptions.inflation == "High Inflation":
        notes.append("High inflation may pressure bond holdings, especially long-duration positions.")
    if recession_prob >= 0.45:
        notes.append("High recession probability suggests reviewing equity concentration and defensive buffers.")
    if float(profile["tbills"]) >= 0.10:
        notes.append("T-bill exposure may help during high-rate or uncertain environments in stress scenarios.")
    if float(profile.get("tech", 0.0)) >= 0.15:
        if assumptions.economic_regime == "AI / Tech Boom":
            notes.append("A tech-heavy portfolio may benefit in an AI/Tech Boom regime in this framework.")
        if assumptions.economic_regime == "Credit Crisis":
            notes.append("A tech-heavy portfolio may suffer more in credit stress under modeled assumptions.")
    if assumptions.valuation == "Expensive":
        notes.append("An expensive valuation environment may limit forward upside in the model.")
    if not notes:
        notes.append(
            "Environment check is informational only — it does not change the Core Portfolio Health Score."
        )
    notes.insert(
        0,
        f"Environment / Macro Check: {s_macro:.1f}/10 (not part of Core Health).",
    )
    return s_macro, notes


def _economic_sleeve_weights(
    tickers: Sequence[str],
    weights: np.ndarray,
    asset_types: Sequence[str],
) -> dict[str, float]:
    """Map holdings into economic sleeves for diversification breadth."""
    w = normalize_weights(weights)
    sleeves = {
        "us_equity": 0.0,
        "intl_equity": 0.0,
        "bonds": 0.0,
        "tbills": 0.0,
        "reit": 0.0,
        "dividend": 0.0,
        "other": 0.0,
    }
    for ti, wi, at in zip(tickers, w, asset_types):
        sym = str(ti).strip().upper()
        if at == "Bonds":
            sleeves["bonds"] += float(wi)
        elif at == "T-Bills":
            sleeves["tbills"] += float(wi)
        elif at == "REIT":
            sleeves["reit"] += float(wi)
        elif at == "Dividend ETF":
            sleeves["dividend"] += float(wi)
        elif at == "Equity":
            if sym in _INTL_EQUITY_TICKERS:
                sleeves["intl_equity"] += float(wi)
            else:
                sleeves["us_equity"] += float(wi)
        else:
            sleeves["other"] += float(wi)
    return sleeves


def score_portfolio_diversification(
    tickers: Sequence[str],
    weights: np.ndarray,
    asset_types: Sequence[str],
    corr: pd.DataFrame,
    *,
    sleeve_min_weight: float = 0.05,
) -> tuple[float, dict[str, Any]]:
    """
    Portfolio-level diversification score (0–12).

    Combines:
    - economic sleeve breadth (0–4)
    - weight dispersion via effective N = 1/HHI (0–4)
    - average |pairwise correlation| (0–4)

    Worst pairwise correlation is reported as a diagnostic only.
    """
    w = normalize_weights(weights)
    sleeves = _economic_sleeve_weights(tickers, w, asset_types)
    n_sleeves = sum(1 for v in sleeves.values() if v >= sleeve_min_weight)
    if n_sleeves >= 4:
        s_breadth = 4.0
    elif n_sleeves == 3:
        s_breadth = 3.0
    elif n_sleeves == 2:
        s_breadth = 2.0
    elif n_sleeves == 1:
        s_breadth = 0.0
    else:
        s_breadth = 0.0

    hhi = float(np.sum(np.square(w)))
    n_eff = (1.0 / hhi) if hhi > 0 else 1.0
    if n_eff >= 3.5:
        s_disp = 4.0
    elif n_eff >= 2.5:
        s_disp = 3.0
    elif n_eff >= 1.75:
        s_disp = 2.0
    elif n_eff >= 1.25:
        s_disp = 1.0
    else:
        s_disp = 0.0

    max_corr = 0.0
    avg_corr = 1.0
    if corr is not None and not corr.empty and len(corr) >= 2:
        off = corr.values.copy().astype(float)
        np.fill_diagonal(off, np.nan)
        abs_off = np.abs(off)
        if np.isfinite(abs_off).any():
            max_corr = float(np.nanmax(abs_off))
            avg_corr = float(np.nanmean(abs_off))
    if len(w) < 2:
        s_corr = 0.0
    elif avg_corr < 0.40:
        s_corr = 4.0
    elif avg_corr < 0.55:
        s_corr = 3.0
    elif avg_corr < 0.70:
        s_corr = 2.0
    elif avg_corr < 0.85:
        s_corr = 1.0
    else:
        s_corr = 0.0

    total = float(np.clip(s_breadth + s_disp + s_corr, 0, 12))
    diag = {
        "sleeve_weights": sleeves,
        "n_sleeves_ge_min": n_sleeves,
        "breadth_pts": s_breadth,
        "hhi": hhi,
        "n_eff": n_eff,
        "dispersion_pts": s_disp,
        "avg_abs_corr": avg_corr,
        "max_abs_corr": max_corr,
        "corr_pts": s_corr,
        "total": total,
    }
    return total, diag


def _classify_health_holding(ticker: str, asset_type: str) -> str:
    try:
        from investment_ami.decision_support.real_portfolio_security_types import (
            classify_ticker_security,
        )

        at = str(asset_type or "")
        engine = ""
        if at == "Bonds":
            engine = "Bonds"
        elif at == "T-Bills":
            engine = "Cash"
        clf = classify_ticker_security(ticker, asset_type_label=at, engine_asset_class=engine)
        return str(clf.kind)
    except Exception:
        at = str(asset_type or "")
        if at == "Bonds":
            return "bond_etf_or_bond_fund"
        if at == "T-Bills":
            return "cash"
        if at == "REIT":
            return "narrow_or_thematic_etf"
        return "unknown"


def score_concentration_risk_kind_aware(
    tickers: Sequence[str],
    weights: np.ndarray,
    asset_types: Sequence[str],
) -> tuple[float, dict[str, Any]]:
    """
    Concentration score (0–12) using AMI security-kind bands on the largest holding.

    Broad-market ETFs and bond funds use softer weight bands than individual equities;
    narrow/thematic ETFs remain relatively strict.
    """
    w = normalize_weights(weights)
    top_idx = int(np.argmax(w))
    top_w = float(w[top_idx])
    top_t = str(tickers[top_idx])
    top_at = str(asset_types[top_idx]) if top_idx < len(asset_types) else ""
    kind = _classify_health_holding(top_t, top_at)

    # (max_weight_inclusive, points) ladders by kind — first match wins.
    bands: dict[str, list[tuple[float, float]]] = {
        "individual_equity": [(0.20, 12.0), (0.30, 8.0), (0.40, 4.0), (1.01, 0.0)],
        "unknown": [(0.20, 12.0), (0.30, 8.0), (0.40, 4.0), (1.01, 0.0)],
        "other": [(0.25, 12.0), (0.35, 8.0), (0.45, 4.0), (1.01, 0.0)],
        "narrow_or_thematic_etf": [(0.25, 12.0), (0.35, 8.0), (0.45, 4.0), (1.01, 0.0)],
        "diversified_sector_or_factor_etf": [(0.30, 12.0), (0.40, 8.0), (0.50, 4.0), (1.01, 0.0)],
        "broad_market_etf": [(0.45, 12.0), (0.60, 8.0), (0.75, 4.0), (1.01, 0.0)],
        "bond_etf_or_bond_fund": [(0.50, 12.0), (0.70, 8.0), (0.85, 4.0), (1.01, 0.0)],
        "cash": [(0.70, 12.0), (0.85, 8.0), (0.95, 4.0), (1.01, 0.0)],
    }
    ladder = bands.get(kind, bands["other"])
    s_conc = 0.0
    for limit, pts in ladder:
        if top_w <= limit:
            s_conc = pts
            break

    return float(s_conc), {
        "top_ticker": top_t,
        "top_weight": top_w,
        "kind": kind,
        "points": float(s_conc),
    }


def normalize_weights(weights: Iterable[float]) -> np.ndarray:
    w = np.asarray(list(weights), dtype=float)
    if w.sum() <= 0:
        raise ValueError("Portfolio weights must sum to a positive value.")
    return w / w.sum()


# Health/Guided: Equity sleeve includes REIT / Dividend ETF (same as allocation_profile).
_EQUITY_BUCKET_TYPES: tuple[str, ...] = ("Equity", "REIT", "Dividend ETF")
_ORPHAN_SLEEVE_LABELS: dict[str, str] = {
    "equity": "Equity (unrepresented)",
    "bonds": "Bonds (unrepresented)",
    "tbills": "Cash / T-Bills (unrepresented)",
}
_WEIGHT_DUST_EPS = 1e-8


def threshold_weight_dust(
    weights: Iterable[float],
    *,
    eps: float = _WEIGHT_DUST_EPS,
    renormalize: bool = True,
) -> np.ndarray:
    """Zero numerical dust (e.g. SLSQP ~1e-12) so displays do not show fake precision."""
    w = np.asarray(list(weights), dtype=float)
    w = np.where(np.abs(w) < eps, 0.0, w)
    if renormalize and float(w.sum()) > 0:
        return normalize_weights(w)
    return w


def format_weight_pct(weight: float, *, decimals: int = 2, eps: float = _WEIGHT_DUST_EPS) -> str:
    """Format a portfolio weight as a percentage, treating dust as 0%."""
    w = 0.0 if abs(float(weight)) < eps else float(weight)
    return f"{w * 100:.{decimals}f}%"


def build_category_preserving_ticker_targets(
    tickers: Sequence[str],
    asset_types: Sequence[str],
    category_targets: dict[str, float],
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """
    Split category objective weights across eligible holdings without renormalizing
    missing sleeves into represented securities.

    Returns
    -------
    ticker_weights
        Absolute target weight per holding (may sum to less than 1.0).
    orphan_sleeves
        Explicit unrepresented category targets (e.g. T-Bills when no T-Bill holding).
        Each dict: ticker label, weight, asset_type, category key, orphan=True.
    """
    n = len(tickers)
    if n != len(asset_types):
        raise ValueError("tickers and asset_types must have the same length.")
    w = np.zeros(n, dtype=float)
    orphans: list[dict[str, Any]] = []

    eq_idx = [i for i, at in enumerate(asset_types) if at in _EQUITY_BUCKET_TYPES]
    bond_idx = [i for i, at in enumerate(asset_types) if at == "Bonds"]
    tb_idx = [i for i, at in enumerate(asset_types) if at == "T-Bills"]

    eq_t = float(category_targets.get("equity", 0.0) or 0.0)
    bond_t = float(category_targets.get("bonds", 0.0) or 0.0)
    tb_t = float(category_targets.get("tbills", 0.0) or 0.0)

    def _assign(indices: list[int], target: float, category: str, asset_type: str) -> None:
        if target <= 0:
            return
        if indices:
            share = target / len(indices)
            for i in indices:
                w[i] = share
            return
        orphans.append(
            {
                "Ticker": _ORPHAN_SLEEVE_LABELS[category],
                "weight": float(target),
                "Asset Type": asset_type,
                "category": category,
                "orphan": True,
            }
        )

    _assign(eq_idx, eq_t, "equity", "Equity")
    _assign(bond_idx, bond_t, "bonds", "Bonds")
    _assign(tb_idx, tb_t, "tbills", "T-Bills")
    return w, orphans


def is_orphan_rebalance_row(row: Any) -> bool:
    """True for explicit unrepresented category sleeves in the rebalance table."""
    try:
        if bool(row.get("Orphan Sleeve")) if hasattr(row, "get") else bool(row["Orphan Sleeve"]):
            return True
    except Exception:
        pass
    try:
        ticker = str(row.get("Ticker", "") if hasattr(row, "get") else row["Ticker"])
    except Exception:
        return False
    return "(unrepresented)" in ticker


def aggregate_guided_category_exposure(
    tickers: Sequence[str],
    asset_types: Sequence[str],
    ticker_weights: Iterable[float],
    orphan_sleeves: Sequence[dict[str, Any]] | None = None,
) -> dict[str, float]:
    """Roll ticker + orphan sleeve weights into Equity / Bonds / T-Bills (Health rules)."""
    w = np.asarray(list(ticker_weights), dtype=float)
    equity = float(
        sum(w[i] for i, at in enumerate(asset_types) if i < len(w) and at in _EQUITY_BUCKET_TYPES)
    )
    bonds = float(sum(w[i] for i, at in enumerate(asset_types) if i < len(w) and at == "Bonds"))
    tbills = float(sum(w[i] for i, at in enumerate(asset_types) if i < len(w) and at == "T-Bills"))
    for sleeve in orphan_sleeves or ():
        wt = float(sleeve.get("weight", 0.0) or 0.0)
        cat = str(sleeve.get("category") or "").strip().lower()
        at = str(sleeve.get("Asset Type") or "")
        if cat == "equity" or at in _EQUITY_BUCKET_TYPES:
            equity += wt
        elif cat == "bonds" or at == "Bonds":
            bonds += wt
        elif cat == "tbills" or at == "T-Bills":
            tbills += wt
    return {"equity": equity, "bonds": bonds, "tbills": tbills}


def align_returns_and_weights(
    asset_returns: pd.DataFrame,
    weights: Iterable[float],
    tickers: Sequence[str] | None = None,
) -> tuple[pd.DataFrame, np.ndarray, list[str]]:
    """Align return columns to ticker/weight order (holdings row order).

    Prevents positional bugs when market-data columns are alphabetical (or any
    other order) while ``weights`` follow the holdings/ticker list.
    """
    w = normalize_weights(weights)
    if asset_returns is None or getattr(asset_returns, "empty", True):
        labels = [str(t).strip().upper() for t in (tickers or [])]
        if not labels:
            labels = [f"A{i}" for i in range(len(w))]
        return pd.DataFrame(columns=labels), w[: len(labels)], labels

    col_map = {str(c).strip().upper(): c for c in asset_returns.columns}
    if tickers is not None:
        labels = [str(t).strip().upper() for t in tickers]
        if len(labels) != len(w):
            raise ValueError(
                f"tickers length ({len(labels)}) must match weights length ({len(w)})"
            )
        missing = [t for t in labels if t not in col_map]
        if missing:
            raise ValueError(f"asset_returns missing columns for tickers: {missing}")
        ordered_cols = [col_map[t] for t in labels]
        aligned = asset_returns.loc[:, ordered_cols].copy()
        aligned.columns = labels
        return aligned, w, labels

    # Legacy: assume weights already match the first len(w) columns' order.
    labels = [str(c).strip().upper() for c in list(asset_returns.columns)[: len(w)]]
    aligned = asset_returns.iloc[:, : len(w)].copy()
    aligned.columns = labels
    return aligned, w, labels


def build_risk_pack(
    returns: pd.DataFrame,
    weights: Iterable[float],
    initial_value: float,
    tickers: Sequence[str] | None = None,
) -> dict[str, object]:
    """Build correlation / scenario / risk-contribution pack with ticker alignment.

    Aligns returns to ``tickers`` first, then calls contribution helpers with the
    aligned frame so callers never need to pass ``tickers=`` into legacy 2-arg
    signatures (avoids Cloud partial-reload TypeError mismatches).
    """
    aligned, w, _labels = align_returns_and_weights(returns, weights, tickers=tickers)
    port_rets = portfolio_daily_returns(aligned, w)
    return {
        "corr": correlation_matrix(aligned),
        "scenarios": scenario_analysis(aligned, w, initial_value),
        "vol_rank": volatility_ranking(aligned),
        "risk_contrib": risk_contribution(aligned, w),
        "roll_vol": rolling_volatility(port_rets),
        "roll_ret": rolling_returns(port_rets),
        "port_rets": port_rets,
    }


def fetch_price_history(
    tickers: list[str],
    start: str,
    end: str | None = None,
) -> pd.DataFrame:
    """Download adjusted close prices via centralized market data provider."""
    from investment_market_data import get_market_data_provider

    return get_market_data_provider().get_price_history(tickers, start, end)


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
    tickers: Sequence[str] | None = None,
) -> pd.Series:
    aligned, w, _labels = align_returns_and_weights(asset_returns, weights, tickers=tickers)
    return (aligned * w).sum(axis=1)


def compute_portfolio_metrics(
    asset_returns: pd.DataFrame,
    weights: np.ndarray,
    risk_free_rate: float,
    initial_value: float,
    years_forward: float = 1.0,
    tickers: Sequence[str] | None = None,
) -> PortfolioMetrics:
    ext = compute_extended_metrics(
        asset_returns,
        weights,
        risk_free_rate,
        initial_value,
        years_forward,
        tickers=tickers,
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


def compute_aligned_sharpe_sortino_diagnostics(
    portfolio_returns: pd.Series,
    policy_returns: pd.Series | None,
    risk_free_rate: float,
) -> dict[str, float]:
    """
    Risk-adjusted diagnostics on the same date-aligned window and rf.

    Returns portfolio and policy Sharpe/Sortino. Policy values use the objective
    policy benchmark series — never portfolio Sortino.
    """
    out: dict[str, float] = {
        "n_aligned": 0.0,
        "raw_sharpe": float("nan"),
        "policy_sharpe": float("nan"),
        "sortino": float("nan"),
        "policy_sortino": float("nan"),
        "annual_return": float("nan"),
        "policy_annual_return": float("nan"),
        "annual_volatility": float("nan"),
        "policy_volatility": float("nan"),
    }
    if portfolio_returns is None or len(portfolio_returns.dropna()) < 2:
        return out
    # Portfolio-only diagnostics always available.
    port = portfolio_returns.dropna()
    out["annual_return"] = float(annualized_return(port))
    out["annual_volatility"] = float(annualized_volatility(port))
    out["raw_sharpe"] = float(
        sharpe_ratio(out["annual_return"], out["annual_volatility"], risk_free_rate)
    )
    out["sortino"] = float(sortino_ratio(port, risk_free_rate))

    if policy_returns is None:
        return out
    pol = policy_returns.copy()
    port_a = portfolio_returns.copy()
    if not isinstance(port_a.index, pd.DatetimeIndex):
        port_a.index = pd.to_datetime(port_a.index)
    if not isinstance(pol.index, pd.DatetimeIndex):
        pol.index = pd.to_datetime(pol.index)
    aligned = pd.concat(
        [port_a.rename("port"), pol.rename("policy")], axis=1, join="inner"
    ).dropna()
    n = int(len(aligned))
    out["n_aligned"] = float(n)
    if n < 6:
        return out

    p_ann = float(annualized_return(aligned["port"]))
    p_vol = float(annualized_volatility(aligned["port"]))
    pol_ann = float(annualized_return(aligned["policy"]))
    pol_vol = float(annualized_volatility(aligned["policy"]))
    # Prefer aligned-window portfolio Sharpe when policy is available.
    out["annual_return"] = p_ann
    out["annual_volatility"] = p_vol
    out["raw_sharpe"] = float(sharpe_ratio(p_ann, p_vol, risk_free_rate))
    out["sortino"] = float(sortino_ratio(aligned["port"], risk_free_rate))
    out["policy_annual_return"] = pol_ann
    out["policy_volatility"] = pol_vol
    out["policy_sharpe"] = float(sharpe_ratio(pol_ann, pol_vol, risk_free_rate))
    out["policy_sortino"] = float(sortino_ratio(aligned["policy"], risk_free_rate))
    return out


def format_sharpe_vs_policy_display(diagnostics: dict[str, float]) -> str:
    """UI helper: portfolio Sharpe / policy-benchmark Sharpe — never Sortino.

    Reads only:
      - ``portfolio_sharpe`` (preferred) or ``raw_sharpe``
      - ``policy_benchmark_sharpe`` (preferred) or ``policy_sharpe``

    Never reads ``sortino`` / ``policy_sortino`` for either side. If the policy
    slot equals portfolio Sortino while a distinct policy Sortino exists, treats
    the policy Sharpe as corrupt and returns ``n/a`` (caller should refresh Health).
    """
    port_sh = diagnostics.get("portfolio_sharpe", diagnostics.get("raw_sharpe"))
    pol_sh = diagnostics.get(
        "policy_benchmark_sharpe", diagnostics.get("policy_sharpe")
    )
    try:
        port_f = float(port_sh) if port_sh is not None else float("nan")
        pol_f = float(pol_sh) if pol_sh is not None else float("nan")
    except (TypeError, ValueError):
        return "n/a"
    if not (np.isfinite(port_f) and np.isfinite(pol_f)):
        return "n/a"

    # Detect Sortino leakage into the policy-Sharpe slot.
    sortino = diagnostics.get("sortino")
    pol_sortino = diagnostics.get("policy_sortino")
    try:
        if (
            sortino is not None
            and np.isfinite(float(sortino))
            and abs(pol_f - float(sortino)) < 1e-12
            and pol_sortino is not None
            and np.isfinite(float(pol_sortino))
            and abs(pol_f - float(pol_sortino)) > 1e-4
        ):
            return "n/a"
    except (TypeError, ValueError):
        pass
    return f"{port_f:.3f} / {pol_f:.3f}"


def build_sharpe_vs_policy_metric_value(
    *,
    portfolio_sharpe: float,
    policy_benchmark_sharpe: float,
) -> str:
    """Caller-level builder: keyword-only — Sortino cannot be passed positionally."""
    try:
        port_f = float(portfolio_sharpe)
        pol_f = float(policy_benchmark_sharpe)
    except (TypeError, ValueError):
        return "n/a"
    if not (np.isfinite(port_f) and np.isfinite(pol_f)):
        return "n/a"
    return f"{port_f:.3f} / {pol_f:.3f}"


def concentration_status_note(
    *,
    top_ticker: str,
    top_weight: float,
    kind: str,
    concentration_pillar_pts: float,
    conc_engine_pts: float,
) -> str:
    """Kind-aware status blurb; does not treat broad-market ETF weight as auto-problem."""
    if top_weight < 0.30:
        return ""
    kind_key = str(kind or "unknown")
    kind_label = kind_key.replace("_", " ")
    ticker = str(top_ticker)
    pct = top_weight * 100.0
    # Soft bands: engine ≥ 8/12 (pillar ≥ 10/15) means within model tolerance for that kind.
    within_bands = float(conc_engine_pts) >= 8.0
    if kind_key == "broad_market_etf" and within_bands:
        return (
            f" Largest holding is {ticker} at {pct:.0f}%; concentration remains within "
            f"the model's broad-market ETF bands."
        )
    if within_bands:
        return (
            f" Largest holding is {ticker} at {pct:.0f}% ({kind_label}); "
            f"concentration remains within the model's bands for this security type "
            f"({concentration_pillar_pts:.0f}/{HEALTH_CONSTRUCTION_CONC_MAX:.0f})."
        )
    return (
        f" Largest holding is {ticker} at {pct:.0f}% ({kind_label}) — "
        f"review concentration diagnostics "
        f"({concentration_pillar_pts:.0f}/{HEALTH_CONSTRUCTION_CONC_MAX:.0f})."
    )


def stabilizer_exposure_phrase(profile: dict[str, float]) -> str | None:
    """Name only sleeves that are actually present (≥5%)."""
    parts: list[str] = []
    if float(profile.get("bonds") or 0.0) >= 0.05:
        parts.append("bond")
    if float(profile.get("tbills") or 0.0) >= 0.05:
        parts.append("T-bill")
    if not parts:
        return None
    if len(parts) == 1:
        return f"{parts[0]} exposure"
    return "bond and T-bill exposure"


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
    tickers: Sequence[str] | None = None,
) -> pd.DataFrame:
    aligned, w, labels = align_returns_and_weights(asset_returns, weights, tickers=tickers)
    cov = aligned.cov() * TRADING_DAYS
    port_vol = float(np.sqrt(np.dot(w.T, np.dot(cov.values, w))))
    if port_vol <= 0:
        marginal = np.zeros(len(w))
    else:
        marginal = w * (cov.values @ w) / port_vol
    contrib_pct = marginal / marginal.sum() if marginal.sum() > 0 else w
    return pd.DataFrame(
        {
            "Ticker": labels,
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
    tickers: Sequence[str] | None = None,
) -> ExtendedPortfolioMetrics:
    """Compute portfolio metrics with ticker-aware weight alignment.

    Pass ``tickers`` in holdings order whenever ``weights`` follow holdings rather
    than ``asset_returns.columns`` order (market data is often alphabetical).
    """
    port_rets = portfolio_daily_returns(asset_returns, weights, tickers=tickers)
    growth = portfolio_growth_series(
        asset_returns, weights, initial_value, tickers=tickers
    )
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
    tickers: Sequence[str] | None = None,
) -> pd.Series:
    port_rets = portfolio_daily_returns(asset_returns, weights, tickers=tickers)
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
    w = threshold_weight_dust(normalize_weights(result.x))
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
    w = threshold_weight_dust(normalize_weights(result.x))
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
    tickers: Sequence[str] | None = None,
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
        port_rets = portfolio_daily_returns(asset_returns, weights, tickers=tickers)
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
    tickers: Sequence[str] | None = None,
) -> pd.DataFrame:
    """
    Apply one-period return shocks to the portfolio.
    shocks are annualized decimal returns (e.g. -0.20 = -20%).
    """
    if scenarios is None:
        scenarios = {
            "Base Case (historical ann.)": annualized_return(
                portfolio_daily_returns(asset_returns, weights, tickers=tickers)
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


def _health_score_label(score: float) -> tuple[str, str]:
    """Labels for Core Health = construction + objective fit + risk fit + policy delivery."""
    if score >= 85:
        return "Well Aligned", "green"
    if score >= 70:
        return "Mostly On Plan", "green"
    if score >= 55:
        return "Mixed Alignment", "yellow"
    if score >= 40:
        return "Needs Attention", "orange"
    return "Off Plan", "red"


def _macro_sensitivity_by_type() -> dict[str, dict[str, float]]:
    return {
        "Equity": {
            "Falling Rates": 0.6,
            "Rising Rates": -0.4,
            "High Inflation": -0.3,
            "Recession": -0.8,
            "Credit Crisis": -0.9,
            "AI / Tech Boom": 0.9,
        },
        "Bonds": {
            "Falling Rates": 0.7,
            "Rising Rates": -0.8,
            "High Inflation": -0.7,
            "Recession": 0.2,
            "Credit Crisis": -0.3,
            "AI / Tech Boom": -0.1,
        },
        "T-Bills": {
            "Falling Rates": -0.2,
            "Rising Rates": 0.5,
            "High Inflation": 0.3,
            "Recession": 0.6,
            "Credit Crisis": 0.8,
            "AI / Tech Boom": 0.0,
        },
        "REIT": {
            "Falling Rates": 0.5,
            "Rising Rates": -0.5,
            "High Inflation": 0.2,
            "Recession": -0.6,
            "Credit Crisis": -0.7,
            "AI / Tech Boom": 0.1,
        },
        "Dividend ETF": {
            "Falling Rates": 0.3,
            "Rising Rates": -0.2,
            "High Inflation": -0.4,
            "Recession": -0.3,
            "Credit Crisis": -0.4,
            "AI / Tech Boom": 0.2,
        },
        "Other": {
            "Falling Rates": 0.0,
            "Rising Rates": 0.0,
            "High Inflation": 0.0,
            "Recession": -0.2,
            "Credit Crisis": -0.3,
            "AI / Tech Boom": 0.0,
        },
    }


def _return_contribution_df(
    asset_returns: pd.DataFrame,
    weights: np.ndarray,
    tickers: Sequence[str] | None = None,
) -> pd.DataFrame:
    aligned, w, labels = align_returns_and_weights(asset_returns, weights, tickers=tickers)
    ann = aligned.mean() * TRADING_DAYS
    contrib = w * ann.values
    total = float(contrib.sum())
    pct = contrib / total if abs(total) > 1e-9 else contrib
    return pd.DataFrame(
        {
            "Ticker": labels,
            "Weight": w,
            "Annual Return": ann.values[: len(w)],
            "Return Contribution": contrib,
            "Return Contribution (%)": pct * 100,
        }
    ).sort_values("Return Contribution", ascending=False)


def _drawdown_contribution_df(
    asset_returns: pd.DataFrame,
    weights: np.ndarray,
    tickers: Sequence[str] | None = None,
) -> pd.DataFrame:
    aligned, w, labels = align_returns_and_weights(asset_returns, weights, tickers=tickers)
    dds = [maximum_drawdown(aligned[col]) for col in labels]
    dds_arr = np.asarray(dds)
    contrib = w * np.abs(dds_arr)
    total = float(contrib.sum()) if contrib.sum() > 0 else 1.0
    return pd.DataFrame(
        {
            "Ticker": labels,
            "Weight": w,
            "Max Drawdown": dds_arr,
            "Drawdown Contribution (%)": contrib / total * 100,
        }
    ).sort_values("Drawdown Contribution (%)", ascending=False)


def _macro_heatmap_df(asset_types: list[str]) -> pd.DataFrame:
    sens = _macro_sensitivity_by_type()
    scenarios = ["Falling Rates", "Rising Rates", "High Inflation", "Recession", "Credit Crisis", "AI / Tech Boom"]
    unique_types = sorted(set(asset_types))
    rows = []
    for at in unique_types:
        row = {"Asset Type": at}
        for sc in scenarios:
            row[sc] = sens.get(at, sens["Other"]).get(sc, 0.0)
        rows.append(row)
    return pd.DataFrame(rows)


def _objective_type_targets(objective: str) -> dict[str, float]:
    key = objective.strip().lower()
    return OBJECTIVE_ALLOCATIONS.get(key, OBJECTIVE_ALLOCATIONS["balanced growth"])


def _make_rec_detail(
    text: str,
    issue: str,
    why_it_matters: str,
    triggered_by: str,
    possible_benefit: str,
    evidence: dict[str, str],
    *,
    rec_class: str = REC_CLASS_CORE,
) -> RecommendationDetail:
    cls = str(rec_class or REC_CLASS_CORE).strip().lower()
    if cls not in (REC_CLASS_CORE, REC_CLASS_DIAGNOSTIC, REC_CLASS_MACRO):
        cls = REC_CLASS_CORE
    return RecommendationDetail(
        text=text,
        issue=issue,
        why_it_matters=why_it_matters,
        triggered_by=triggered_by,
        possible_benefit=possible_benefit,
        evidence=evidence,
        rec_class=cls,
    )


def select_primary_recommendation_detail(
    details: list[RecommendationDetail] | None,
) -> RecommendationDetail | None:
    """
    Guided / coach primary issue: first Option C *core* actionable detail.

    Skips diagnostic-only Sharpe/Sortino/etc. and prefers core over macro.
    """
    if not details:
        return None
    core = [d for d in details if getattr(d, "rec_class", REC_CLASS_CORE) == REC_CLASS_CORE]
    pool = core or [
        d for d in details if getattr(d, "rec_class", REC_CLASS_CORE) == REC_CLASS_MACRO
    ]
    if not pool:
        return None
    actionable = [
        d
        for d in pool
        if not str(d.text or "").lower().startswith("no urgent")
        and not str(d.issue or "").lower().startswith("no urgent")
    ]
    return actionable[0] if actionable else pool[0]


def _core_recommendation_sort_key(detail: RecommendationDetail) -> tuple[int, str]:
    """Prefer objective / missing-sleeve / drift issues ahead of other core flags."""
    issue = str(detail.issue or "").lower()
    text = str(detail.text or "").lower()
    if "not represented" in issue or "unrepresented" in text or "orphan" in str(
        detail.evidence.get("Orphan sleeve", "")
    ).lower():
        return (0, issue)
    if "drifted" in issue or "drift" in issue:
        return (1, issue)
    if "objective" in issue or "bond/cash" in issue or "short-term cash" in issue:
        return (2, issue)
    if "concentration" in issue:
        return (3, issue)
    if "drawdown" in issue:
        return (4, issue)
    if issue.startswith("no urgent"):
        return (9, issue)
    return (5, issue)


def finalize_recommendation_details(
    core: list[RecommendationDetail],
    macro: list[RecommendationDetail],
    diagnostic: list[RecommendationDetail],
) -> list[RecommendationDetail]:
    """Order: Option C core (objective-first) → macro coaching → diagnostics."""
    core_sorted = sorted(core, key=_core_recommendation_sort_key)
    return list(core_sorted) + list(macro) + list(diagnostic)


def _build_portfolio_action_plan(
    score: float,
    objective: str,
    recommendation_details: list[RecommendationDetail],
    profile: dict,
    recession_prob: float,
    avg_drift: float,
    max_w: float,
) -> PortfolioActionPlan:
    obj_label = objective.strip().replace("_", " ").title()
    # Urgency from Option C / constraint core issues only — not diagnostic Sharpe/etc.
    urgent = any(
        getattr(d, "rec_class", REC_CLASS_CORE) == REC_CLASS_CORE
        and d.issue.lower().startswith(
            (
                "portfolio concentration",
                "objective",
                "a category",
                "equity weight",
                "bond/cash",
                "portfolio weight drifted",
            )
        )
        for d in recommendation_details
        if not d.text.lower().startswith("no urgent")
    )

    if score >= 75 and not urgent:
        headline = f"Your portfolio is currently aligned with your {obj_label} objective."
    elif score >= 55:
        headline = f"Your portfolio is moderately aligned with your {obj_label} objective — a review may help."
    else:
        headline = f"Your portfolio may need attention to stay aligned with your {obj_label} objective."

    today: list[str] = []
    if score >= 75 and not urgent:
        today.append(f"Portfolio Health Score: {score:.0f}/100 — no immediate model flags.")
        today.append("Skim your status summary and confirm holdings still match your plan.")
        today.append("No immediate changes are suggested by the model.")
    else:
        today.append(f"Portfolio Health Score: {score:.0f}/100 — review flagged items below.")
        today.append("Open each recommendation and read **Why?** to see what triggered it.")
        if recession_prob >= 0.45:
            today.append(f"Recession probability is elevated ({recession_prob * 100:.0f}%) in your macro settings.")
        if max_w >= 0.35:
            today.append(
                f"Largest holding concentration is {max_w * 100:.0f}% ({profile['top_ticker']}) — worth reviewing."
            )
        today.append("Based on the model, it may be worth reviewing allocation and diversification.")

    this_month: list[str] = [
        "Click **Refresh Market Data** in the sidebar, then rerun **Portfolio Health**.",
        "Compare your Portfolio Health Score to last month — note any drop of 5+ points.",
    ]
    if avg_drift >= 0.05:
        this_month.append("Check allocation drift vs. your objective — rebalance suggestions may apply.")
    else:
        this_month.append("Confirm weights have not drifted far from your target mix.")
    if urgent:
        this_month.append("Review at least one recommendation below and its tradeoffs before making changes.")
    else:
        this_month.append("Continue monitoring monthly; no rebalance required unless drift appears.")

    this_year: list[str] = [
        f"Reassess whether **{obj_label}** still matches your life goals and timeline.",
        "Review your comfort with ups and downs — has your risk tolerance changed?",
        "Update sidebar assumptions (portfolio value, date range, macro settings) if your situation changed.",
        "Rerun Portfolio Health after major market moves or life events.",
    ]

    return PortfolioActionPlan(
        headline=headline,
        today=today,
        this_month=this_month,
        this_year=this_year,
    )


def evaluate_portfolio_health(
    tickers: list[str],
    weights: np.ndarray,
    asset_types: list[str],
    metrics: ExtendedPortfolioMetrics,
    asset_returns: pd.DataFrame,
    corr: pd.DataFrame,
    risk_contrib_df: pd.DataFrame,
    assumptions: ForwardMacroAssumptions,
    objective: str,
    risk_free_rate: float,
    initial_value: float,
    benchmark_returns: pd.Series | None = None,
    optimizer_weights: np.ndarray | None = None,
    recommended_type_mix: dict[str, float] | None = None,
    bond_min_pct: float | None = None,
    policy_benchmark_returns: pd.Series | None = None,
    policy_benchmark_meta: dict[str, Any] | None = None,
) -> PortfolioHealthResult:
    w = normalize_weights(weights)
    profile = allocation_profile(tickers, w, asset_types)
    ret_contrib = _return_contribution_df(asset_returns, w, tickers=tickers)
    dd_contrib = _drawdown_contribution_df(asset_returns, w, tickers=tickers)
    risk_df = risk_contrib_df.copy()
    macro_heatmap = _macro_heatmap_df(asset_types)

    port_rets = portfolio_daily_returns(asset_returns, w, tickers=tickers)
    policy_meta = dict(policy_benchmark_meta or {})
    s_perf, port_ann_aligned, policy_ann, n_aligned = score_policy_relative_performance(
        port_rets, policy_benchmark_returns
    )
    # Do not fall back to 100% SPY for Health return scoring.
    if policy_benchmark_returns is None or n_aligned < 6:
        s_perf = 0.0
        policy_label = str(policy_meta.get("label") or "Policy benchmark unavailable")
        policy_detail = str(
            policy_meta.get("detail")
            or policy_meta.get("error")
            or "Policy benchmark series missing or too short after date alignment — "
            "Policy-Relative Performance scored 0."
        )
    else:
        policy_label = str(policy_meta.get("label") or "Policy benchmark")
        policy_detail = str(
            policy_meta.get("detail")
            or "Objective-aware policy benchmark (category-weighted proxies)."
        )
        policy_detail = (
            f"{policy_detail} Aligned observations: {n_aligned}. "
            f"Portfolio ann. return (aligned): {port_ann_aligned * 100:.2f}%; "
            f"policy ann. return: {policy_ann * 100:.2f}%."
        )

    # Legacy SPY series retained only for narrative beta context (not return score).
    spy_ann = 0.0
    if benchmark_returns is not None and len(benchmark_returns.dropna()) > 5:
        spy_ann = annualized_return(benchmark_returns.dropna())

    # Diagnostics from ticker-aligned portfolio + policy series (not Core Health points).
    # Sharpe vs policy must use policy-benchmark Sharpe — never portfolio Sortino.
    rad = compute_aligned_sharpe_sortino_diagnostics(
        port_rets, policy_benchmark_returns, risk_free_rate
    )
    port_ann = float(rad["annual_return"]) if np.isfinite(rad["annual_return"]) else annualized_return(port_rets)
    vol = (
        float(rad["annual_volatility"])
        if np.isfinite(rad["annual_volatility"])
        else annualized_volatility(port_rets)
    )
    raw_sharpe = float(rad["raw_sharpe"]) if np.isfinite(rad["raw_sharpe"]) else 0.0
    dd = maximum_drawdown(port_rets)
    port_sortino = float(rad["sortino"]) if np.isfinite(rad["sortino"]) else sortino_ratio(port_rets, risk_free_rate)
    policy_vol = float(rad["policy_volatility"]) if np.isfinite(rad["policy_volatility"]) else 0.0
    policy_sharpe = float(rad["policy_sharpe"]) if np.isfinite(rad["policy_sharpe"]) else float("nan")
    policy_sortino = float(rad["policy_sortino"]) if np.isfinite(rad["policy_sortino"]) else float("nan")

    # ── Option C Core Health pillars (sum = 100) ──
    ret_gap = port_ann_aligned - policy_ann if n_aligned >= 6 else port_ann - spy_ann

    s_obj, obj_diag = score_policy_objective_fit(profile, objective)
    avg_drift = float(obj_diag["avg_drift"])

    s_construction, construction_diag = score_portfolio_construction(
        tickers, w, asset_types, corr
    )
    div_diag = construction_diag["div_diag"]
    conc_diag = construction_diag["conc_diag"]
    max_corr = float(div_diag.get("max_abs_corr") or 0.0)
    max_w = float(conc_diag.get("top_weight") or profile["concentration"])
    s_div = float(construction_diag["diversification_pts"])
    s_conc = float(construction_diag["concentration_pts"])

    s_risk, risk_diag = score_risk_appropriateness(port_rets, policy_benchmark_returns)

    breakdown = {
        "Policy / Objective Fit": float(s_obj),
        "Portfolio Construction": float(s_construction),
        "Risk Appropriateness": float(s_risk),
        "Policy-Relative Performance": float(s_perf),
    }
    assert abs(sum(HEALTH_CORE_PILLAR_MAX.values()) - 100.0) < 1e-9
    score = float(np.clip(sum(breakdown.values()), 0, 100))
    score_label, score_color = _health_score_label(score)

    pillar_explanations = {
        "Policy / Objective Fit": (
            f"{s_obj:.1f}/{HEALTH_CORE_PILLAR_MAX['Policy / Objective Fit']:.0f} — "
            f"Category mix vs objective "
            f"(equity {obj_diag['current']['equity']*100:.0f}% / "
            f"bonds {obj_diag['current']['bonds']*100:.0f}% / "
            f"T-Bills {obj_diag['current']['tbills']*100:.0f}% vs target "
            f"{obj_diag['targets']['equity']*100:.0f}% / "
            f"{obj_diag['targets']['bonds']*100:.0f}% / "
            f"{obj_diag['targets']['tbills']*100:.0f}%; "
            f"avg drift {avg_drift*100:.1f}%)."
        ),
        "Portfolio Construction": (
            f"{s_construction:.1f}/{HEALTH_CORE_PILLAR_MAX['Portfolio Construction']:.0f} — "
            f"Diversification {s_div:.1f}/{HEALTH_CONSTRUCTION_DIV_MAX:.0f} "
            f"(sleeves, effective N, avg |corr|) + "
            f"Concentration {s_conc:.1f}/{HEALTH_CONSTRUCTION_CONC_MAX:.0f} "
            f"(kind-aware; top {conc_diag.get('top_ticker')} "
            f"{max_w*100:.0f}% as {str(conc_diag.get('kind','')).replace('_',' ')}). "
            f"Max pairwise |corr|={max_corr:.2f} is diagnostic only."
        ),
        "Risk Appropriateness": (
            f"{s_risk:.1f}/{HEALTH_CORE_PILLAR_MAX['Risk Appropriateness']:.0f} — "
            f"Policy-relative risk on {int(risk_diag.get('n_aligned') or 0)} aligned days: "
            f"port vol {float(risk_diag.get('port_vol') or 0)*100:.1f}% vs "
            f"policy vol {float(risk_diag.get('policy_vol') or 0)*100:.1f}% "
            f"(vol pts {float(risk_diag.get('vol_pts') or 0):.1f}/"
            f"{float(risk_diag.get('vol_max_pts') or 16):.0f}; "
            f"DD-vs-policy pts {float(risk_diag.get('dd_pts') or 0):.1f}/"
            f"{float(risk_diag.get('dd_max_pts') or 4):.0f}). "
            f"Absolute max drawdown is not graded here."
        ),
        "Policy-Relative Performance": (
            f"{s_perf:.1f}/{HEALTH_CORE_PILLAR_MAX['Policy-Relative Performance']:.0f} — "
            f"Aligned ann. return gap vs objective policy "
            f"({port_ann_aligned*100:.2f}% vs {policy_ann*100:.2f}%; "
            f"gap {(ret_gap if n_aligned >= 6 else 0)*100:.2f} pp). "
            f"Not an absolute SPY-beating score."
        ),
    }
    construction_subscores = {
        "Diversification": s_div,
        "Concentration": s_conc,
    }

    # Environment / Macro Check — diagnostic only (does not enter Core Health).
    s_macro, macro_fit = compute_macro_environment_check(profile, assumptions)
    recession_prob = assumptions.recession_probability

    health_diagnostics = {
        "_schema_version": HEALTH_DIAGNOSTICS_SCHEMA_VERSION,
        "annual_return": float(port_ann),
        "policy_annual_return": float(policy_ann) if n_aligned >= 6 else float("nan"),
        "annual_volatility": float(vol),
        "policy_volatility": float(policy_vol) if policy_vol > 0 else float(
            risk_diag.get("policy_vol") or float("nan")
        ),
        # Unambiguous Sharpe keys for the UI (prefer these over legacy aliases).
        "portfolio_sharpe": float(raw_sharpe),
        "policy_benchmark_sharpe": float(policy_sharpe),
        # Legacy aliases (same floats).
        "raw_sharpe": float(raw_sharpe),
        "policy_sharpe": float(policy_sharpe),
        "sortino": float(port_sortino),
        "policy_sortino": float(policy_sortino),
        "max_drawdown": float(dd),
        "max_pairwise_abs_corr": float(max_corr),
        "macro_check_score": float(s_macro),
        "risk_vol_ratio": float(risk_diag["vol_ratio"])
        if risk_diag.get("ok") and np.isfinite(risk_diag.get("vol_ratio", np.nan))
        else float("nan"),
    }

    # ── What's working / not ──
    whats_working: list[str] = []
    whats_not: list[str] = []

    for _, row in ret_contrib.head(3).iterrows():
        if row["Return Contribution"] > 0:
            whats_working.append(
                f"{row['Ticker']} contributed positively to modeled return ({row['Return Contribution'] * 100:.2f}%)."
            )

    stabilizers = [
        t for t in tickers
        if asset_types[tickers.index(t)] in ("T-Bills", "Bonds")
        and w[tickers.index(t)] >= 0.05
    ]
    for t in stabilizers[:3]:
        whats_working.append(f"{t} may act as a lower-volatility stabilizer in the model.")

    if n_aligned >= 6 and ret_gap > 0:
        whats_working.append(
            "Portfolio return is above the objective policy benchmark over the selected period (model-based)."
        )
    if max_corr < 0.65:
        whats_working.append("Holdings show moderate correlation — diversification may be helping.")
    if float(div_diag.get("n_sleeves_ge_min") or 0) >= 3:
        whats_working.append(
            "Multiple economic sleeves (e.g. equity / bonds / REIT) contribute portfolio-level diversification."
        )
    if metrics.beta_spy < 0.85 and float(profile["bonds"] + profile["tbills"]) >= 0.20:
        exposure = stabilizer_exposure_phrase(profile)
        if exposure:
            whats_working.append(
                f"Lower market sensitivity than SPY may be supported by {exposure}."
            )

    for _, row in ret_contrib.iterrows():
        if row["Return Contribution"] < -0.001:
            whats_not.append(f"{row['Ticker']} has a negative return contribution in the analysis window.")

    for _, row in dd_contrib.head(2).iterrows():
        if row["Max Drawdown"] < -0.15:
            whats_not.append(
                f"{row['Ticker']} experienced a deep drawdown ({row['Max Drawdown'] * 100:.1f}%) — a potential risk contributor."
            )

    if float(construction_diag.get("conc_engine_pts") or 0) <= 4.0:
        whats_not.append(
            f"Largest holding ({profile['top_ticker']}) is {max_w * 100:.1f}% "
            f"({str(conc_diag.get('kind', 'unknown')).replace('_', ' ')}) — concentration may be worth reviewing."
        )
    if max_corr >= 0.80:
        whats_not.append("Some holdings appear highly correlated — diversification benefits may be limited.")

    if assumptions.inflation == "High Inflation" and float(profile["long_duration_bonds"]) >= 0.15:
        whats_not.append("Long-duration bond exposure may be pressured under high-inflation assumptions.")
    if recession_prob >= 0.45 and float(profile["equity"]) >= 0.65:
        whats_not.append("Elevated recession probability with high equity weight may increase stress-test sensitivity.")

    if not whats_working:
        whats_working.append("No clear positive contributors identified — consider reviewing holdings and weights.")
    if not whats_not:
        whats_not.append("No major model flags detected — continue monitoring drift and macro assumptions.")

    # ── Recommendations (Option C core + macro coaching + diagnostic context) ──
    core_recs: list[RecommendationDetail] = []
    macro_recs: list[RecommendationDetail] = []
    diagnostic_recs: list[RecommendationDetail] = []
    obj_key = objective.strip().lower()
    obj_label = objective.strip().replace("_", " ").title()
    equity_pct = float(profile["equity"]) * 100
    bond_cash_pct = (float(profile["bonds"]) + float(profile["tbills"])) * 100
    long_bond_pct = float(profile["long_duration_bonds"]) * 100
    risk_max = float(HEALTH_CORE_PILLAR_MAX["Risk Appropriateness"])
    construction_max = float(HEALTH_CORE_PILLAR_MAX["Portfolio Construction"])

    if recession_prob > 0.50 and float(profile["equity"]) > 0.70:
        macro_recs.append(
            _make_rec_detail(
                "Based on the model, recession probability above 50% with equity above 70% may be worth reviewing for equity exposure.",
                issue="High equity exposure during elevated recession risk.",
                why_it_matters="When recession probability is high, equity-heavy portfolios may experience larger stress in the model.",
                triggered_by=f"Recession probability = {recession_prob * 100:.0f}% and equity allocation = {equity_pct:.0f}%.",
                possible_benefit="Reviewing equity exposure may reduce modeled sensitivity to a downturn.",
                evidence={
                    "Recession probability": f"{recession_prob * 100:.0f}%",
                    "Equity allocation": f"{equity_pct:.0f}%",
                    "Portfolio objective": obj_label,
                    "Portfolio Health Score": f"{score:.0f}/100",
                },
                rec_class=REC_CLASS_MACRO,
            )
        )
    if assumptions.inflation == "High Inflation" and float(profile["long_duration_bonds"]) > 0.20:
        macro_recs.append(
            _make_rec_detail(
                "High inflation assumptions combined with long-duration bonds may warrant reviewing bond sensitivity (for educational purposes).",
                issue="Long-duration bond exposure under high-inflation assumptions.",
                why_it_matters="Longer-maturity bonds can be more sensitive to inflation and rate changes in stress models.",
                triggered_by=f"Inflation assumption = High Inflation; long-duration bonds = {long_bond_pct:.0f}%.",
                possible_benefit="Reviewing bond duration mix may improve resilience under high-inflation scenarios.",
                evidence={
                    "Inflation assumption": assumptions.inflation,
                    "Long-duration bonds": f"{long_bond_pct:.0f}%",
                    "Bond/cash allocation": f"{bond_cash_pct:.0f}%",
                },
                rec_class=REC_CLASS_MACRO,
            )
        )
    if raw_sharpe < 0.4:
        diagnostic_recs.append(
            _make_rec_detail(
                "Sharpe ratio below 0.4 is a diagnostic flag for risk-adjusted return — supporting context only, not a Core Health allocation trigger.",
                issue="Risk-adjusted return appears weak in the model (diagnostic).",
                why_it_matters=(
                    "Sharpe is outside Option C Core Health. Use it as context alongside policy fit, "
                    "construction, risk appropriateness, and policy-relative performance."
                ),
                triggered_by=f"Sharpe ratio = {raw_sharpe:.2f} (below 0.4 diagnostic threshold).",
                possible_benefit="Review pillar diagnostics; do not reallocate solely on this absolute Sharpe flag.",
                evidence={
                    "Sharpe ratio": f"{raw_sharpe:.2f}",
                    "Annual return": f"{port_ann * 100:.1f}%",
                    "Volatility": f"{vol * 100:.1f}%",
                    "Role": "diagnostic context",
                },
                rec_class=REC_CLASS_DIAGNOSTIC,
            )
        )
    if dd < -0.25:
        # Absolute DD is diagnostic unless Risk Appropriateness is already weak.
        dd_rec_class = (
            REC_CLASS_CORE
            if float(s_risk) < 0.5 * risk_max
            else REC_CLASS_DIAGNOSTIC
        )
        dd_bucket = core_recs if dd_rec_class == REC_CLASS_CORE else diagnostic_recs
        dd_bucket.append(
            _make_rec_detail(
                "Max drawdown worse than -25% flags drawdown risk in the historical window — may be worth reviewing defensive buffers.",
                issue="Historical drawdown risk is elevated.",
                why_it_matters=(
                    "Large past drops may indicate the portfolio could fall sharply again in stress periods. "
                    + (
                        "Risk Appropriateness is also weak vs policy, so this reinforces a Core risk review."
                        if dd_rec_class == REC_CLASS_CORE
                        else "Shown as diagnostic context because Risk Appropriateness vs policy is not weak."
                    )
                ),
                triggered_by=f"Max drawdown = {dd * 100:.1f}% (worse than -25%).",
                possible_benefit="Adding stabilizers (bonds/cash) or reducing risk assets may lower drawdown severity in the model.",
                evidence={
                    "Max drawdown": f"{dd * 100:.1f}%",
                    "Volatility": f"{vol * 100:.1f}%",
                    "Beta vs SPY": f"{metrics.beta_spy:.2f}",
                    "Risk Appropriateness": f"{float(s_risk):.1f}/{risk_max:.0f}",
                    "Role": (
                        "core (policy risk weak)"
                        if dd_rec_class == REC_CLASS_CORE
                        else "diagnostic context"
                    ),
                },
                rec_class=dd_rec_class,
            )
        )
    if float(construction_diag.get("conc_engine_pts") or 0) <= 4.0:
        top_kind = str(conc_diag.get("kind") or "unknown")
        core_recs.append(
            _make_rec_detail(
                f"Largest holding ({profile['top_ticker']}) is {max_w * 100:.1f}% "
                f"({top_kind.replace('_', ' ')}) — concentration may deserve attention.",
                issue="Portfolio concentration is elevated for this security type.",
                why_it_matters=(
                    "A large position can increase portfolio sensitivity if that holding falls sharply. "
                    "Broad-market funds are treated more leniently than individual stocks or thematic ETFs."
                ),
                triggered_by=(
                    f"Largest holding = {profile['top_ticker']} at {max_w * 100:.1f}% "
                    f"(kind={top_kind}; concentration score "
                    f"{float(construction_diag.get('conc_engine_pts') or 0):.0f}/12 engine, "
                    f"{s_conc:.1f}/{HEALTH_CONSTRUCTION_CONC_MAX:.0f} pillar)."
                ),
                possible_benefit="Greater diversification and lower concentration risk.",
                evidence={
                    "Largest holding": profile["top_ticker"],
                    "Largest holding weight": f"{max_w * 100:.1f}%",
                    "Security kind": top_kind,
                    "Concentration points": (
                        f"{s_conc:.1f}/{HEALTH_CONSTRUCTION_CONC_MAX:.0f}"
                    ),
                    "Equity allocation": f"{equity_pct:.0f}%",
                    "Portfolio objective": obj_label,
                },
                rec_class=REC_CLASS_CORE,
            )
        )
    if obj_key == "short-term cash management" and float(profile["equity"]) > 0.40:
        core_recs.append(
            _make_rec_detail(
                "For a short-term cash objective, equity above 40% may not align with the selected objective in this model.",
                issue="Equity weight may exceed short-term cash objective.",
                why_it_matters="Short-term goals often prioritize stability over growth in this framework.",
                triggered_by=f"Portfolio objective = {obj_label}; equity allocation = {equity_pct:.0f}%.",
                possible_benefit="Aligning equity with the objective may reduce unwanted volatility for near-term needs.",
                evidence={
                    "Portfolio objective": obj_label,
                    "Equity allocation": f"{equity_pct:.0f}%",
                    "T-Bills/cash allocation": f"{float(profile['tbills']) * 100:.0f}%",
                },
                rec_class=REC_CLASS_CORE,
            )
        )
    if port_sortino < 0.35:
        diagnostic_recs.append(
            _make_rec_detail(
                "Sortino ratio is low — downside volatility may be elevated relative to return (diagnostic context).",
                issue="Downside risk appears elevated vs. return (diagnostic).",
                why_it_matters=(
                    "Sortino is outside Option C Core Health. Treat as supporting downside context, "
                    "not a standalone reason to reallocate a Mostly-On-Plan book."
                ),
                triggered_by=f"Sortino ratio = {port_sortino:.2f} (below 0.35 diagnostic threshold).",
                possible_benefit="Review defensive assets if Risk Appropriateness or objective fit also flag concern.",
                evidence={
                    "Sortino ratio": f"{port_sortino:.2f}",
                    "Max drawdown": f"{dd * 100:.1f}%",
                    "Volatility": f"{vol * 100:.1f}%",
                    "Role": "diagnostic context",
                },
                rec_class=REC_CLASS_DIAGNOSTIC,
            )
        )
    if metrics.beta_spy > 1.15:
        diagnostic_recs.append(
            _make_rec_detail(
                "Beta above 1.15 vs SPY is contextual risk information — not an independent Option C allocation trigger.",
                issue="Portfolio moves more than the broad market (diagnostic).",
                why_it_matters=(
                    "High beta can amplify market swings. Prefer policy-relative Risk Appropriateness "
                    "and objective fit when deciding whether allocation changes are warranted."
                ),
                triggered_by=f"Beta vs SPY = {metrics.beta_spy:.2f} (above 1.15 diagnostic threshold).",
                possible_benefit="Use as risk context when reviewing stabilizers or equity weight vs objective.",
                evidence={
                    "Beta vs SPY": f"{metrics.beta_spy:.2f}",
                    "Equity allocation": f"{equity_pct:.0f}%",
                    "Volatility": f"{vol * 100:.1f}%",
                    "Role": "diagnostic context",
                },
                rec_class=REC_CLASS_DIAGNOSTIC,
            )
        )
    if bond_min_pct is not None and (float(profile["bonds"]) + float(profile["tbills"])) * 100 < bond_min_pct:
        core_recs.append(
            _make_rec_detail(
                f"Bond/cash allocation is below the selected minimum constraint ({bond_min_pct:.0f}%) — may be worth reviewing.",
                issue="Bond/cash weight is below your stated minimum.",
                why_it_matters="Your constraint signals desired stability that the current mix may not meet.",
                triggered_by=f"Bond/cash = {bond_cash_pct:.0f}% vs minimum = {bond_min_pct:.0f}%.",
                possible_benefit="Raising bond/cash toward your minimum may improve stability in the model.",
                evidence={
                    "Bond/cash allocation": f"{bond_cash_pct:.0f}%",
                    "Minimum constraint": f"{bond_min_pct:.0f}%",
                    "Portfolio objective": obj_label,
                },
                rec_class=REC_CLASS_CORE,
            )
        )
    if max_corr >= 0.80:
        # Correlation is construction context; do not override a strong construction pillar.
        corr_rec_class = (
            REC_CLASS_DIAGNOSTIC
            if float(s_construction) >= 0.67 * construction_max
            else REC_CLASS_CORE
        )
        corr_bucket = (
            diagnostic_recs if corr_rec_class == REC_CLASS_DIAGNOSTIC else core_recs
        )
        corr_bucket.append(
            _make_rec_detail(
                "Some holdings appear highly correlated — diversification benefits may be limited.",
                issue="Holdings move together more than ideal.",
                why_it_matters=(
                    "If assets rise and fall together, the portfolio may not be as diversified as it looks. "
                    + (
                        "Construction score is already strong, so this stays diagnostic context."
                        if corr_rec_class == REC_CLASS_DIAGNOSTIC
                        else "Construction is soft, so correlation reinforces a Core construction review."
                    )
                ),
                triggered_by=f"Maximum pairwise correlation ≈ {max_corr:.2f} (≥ 0.80).",
                possible_benefit="Adding less-correlated assets may smooth combined volatility.",
                evidence={
                    "Max correlation": f"{max_corr:.2f}",
                    "Number of holdings": str(len(tickers)),
                    "Portfolio objective": obj_label,
                    "Portfolio Construction": f"{float(s_construction):.1f}/{construction_max:.0f}",
                    "Role": (
                        "diagnostic context"
                        if corr_rec_class == REC_CLASS_DIAGNOSTIC
                        else "core construction"
                    ),
                },
                rec_class=corr_rec_class,
            )
        )

    # Macro narrative comes from Environment / Macro Check (not Core Health).
    # ── Rebalance / drift table (category-preserving ticker targets) ──
    obj_targets = obj_diag["targets"]
    obj_eq, obj_bond, obj_tb = obj_targets["equity"], obj_targets["bonds"], obj_targets["tbills"]
    obj_w, obj_orphans = build_category_preserving_ticker_targets(tickers, asset_types, obj_targets)

    opt_w = optimizer_weights if optimizer_weights is not None else w.copy()
    if optimizer_weights is not None:
        opt_w = threshold_weight_dust(opt_w)
    rec_mix = recommended_type_mix or obj_targets
    rec_w, rec_orphans = build_category_preserving_ticker_targets(tickers, asset_types, rec_mix)

    rebalance_rows = []
    for i, t in enumerate(tickers):
        drift_obj = (w[i] - obj_w[i]) * 100
        drift_opt = (w[i] - opt_w[i]) * 100
        suggestion = ""
        if drift_obj >= 3:
            suggestion = f"Consider reducing {t} by ~{drift_obj:.1f}% (vs objective mix)"
        elif drift_obj <= -3:
            suggestion = f"Consider increasing {t} by ~{abs(drift_obj):.1f}% (vs objective mix)"
        elif drift_opt >= 3:
            suggestion = f"May be overweight vs optimizer — consider reducing {t} by ~{drift_opt:.1f}%"
        elif drift_opt <= -3:
            suggestion = f"May be underweight vs optimizer — consider increasing {t} by ~{abs(drift_opt):.1f}%"
        rebalance_rows.append(
            {
                "Ticker": t,
                "Current (%)": round(w[i] * 100, 1),
                "Objective (%)": round(obj_w[i] * 100, 1),
                "Optimizer (%)": round(float(opt_w[i]) * 100, 1),
                "Recommended (%)": round(rec_w[i] * 100, 1),
                "Drift vs Objective (%)": round(drift_obj, 1),
                "Drift vs Optimizer (%)": round(drift_opt, 1),
                "Model Note": suggestion or "Within tolerance",
                "Orphan Sleeve": False,
            }
        )

    for sleeve in obj_orphans:
        orphan_w = float(sleeve["weight"])
        orphan_ticker = str(sleeve["Ticker"])
        # Recommended orphan for same missing category (if present)
        rec_match = next(
            (s for s in rec_orphans if s.get("category") == sleeve.get("category")),
            None,
        )
        rec_orphan_w = float(rec_match["weight"]) if rec_match else 0.0
        drift_obj = (0.0 - orphan_w) * 100
        rebalance_rows.append(
            {
                "Ticker": orphan_ticker,
                "Current (%)": 0.0,
                "Objective (%)": round(orphan_w * 100, 1),
                "Optimizer (%)": 0.0,
                "Recommended (%)": round(rec_orphan_w * 100, 1),
                "Drift vs Objective (%)": round(drift_obj, 1),
                "Drift vs Optimizer (%)": 0.0,
                "Model Note": (
                    f"No holding maps to this category — keep {orphan_w * 100:.0f}% as an explicit "
                    f"{sleeve.get('Asset Type', 'category')} target (e.g. BIL/SGOV/cash). "
                    "Not added to My Portfolio automatically."
                ),
                "Orphan Sleeve": True,
            }
        )
        core_recs.append(
            _make_rec_detail(
                f"Objective includes {orphan_w * 100:.0f}% {sleeve.get('Asset Type', 'unrepresented')} "
                f"with no matching holding.",
                issue="A category in your objective is not represented in current holdings.",
                why_it_matters=(
                    "Without that sleeve, applying only existing tickers cannot fully match the "
                    "stated category objective."
                ),
                triggered_by=(
                    f"{orphan_ticker}: objective {orphan_w * 100:.1f}% vs current 0% "
                    f"(not auto-added to the portfolio)."
                ),
                possible_benefit=(
                    "Adding an appropriate cash/T-Bill (or other) holding would let the portfolio "
                    "match the full objective mix."
                ),
                evidence={
                    "Ticker": orphan_ticker,
                    "Current weight": "0%",
                    "Objective weight": f"{orphan_w * 100:.1f}%",
                    "Portfolio objective": obj_label,
                    "Orphan sleeve": "yes",
                },
                rec_class=REC_CLASS_CORE,
            )
        )

    rebalance_df = pd.DataFrame(rebalance_rows)

    for row in rebalance_rows:
        if row.get("Orphan Sleeve"):
            continue
        note = row["Model Note"]
        if not note or note == "Within tolerance":
            continue
        ticker = row["Ticker"]
        core_recs.append(
            _make_rec_detail(
                note,
                issue="Portfolio weight drifted from a reference mix.",
                why_it_matters="Drift can push your portfolio away from the risk profile you selected or modeled.",
                triggered_by=(
                    f"{ticker}: current {row['Current (%)']}% vs objective {row['Objective (%)']}% "
                    f"(drift {row['Drift vs Objective (%)']:+.1f}%)."
                ),
                possible_benefit="Rebalancing toward reference weights may restore intended diversification and risk balance.",
                evidence={
                    "Ticker": ticker,
                    "Current weight": f"{row['Current (%)']}%",
                    "Objective weight": f"{row['Objective (%)']}%",
                    "Optimizer weight": f"{row['Optimizer (%)']}%",
                    "Drift vs objective": f"{row['Drift vs Objective (%)']:+.1f}%",
                    "Portfolio objective": obj_label,
                },
                rec_class=REC_CLASS_CORE,
            )
        )

    if not core_recs and not macro_recs and not diagnostic_recs:
        core_recs.append(
            _make_rec_detail(
                "No urgent model flags — continue monitoring allocation drift and macro assumptions.",
                issue="No urgent model flags detected.",
                why_it_matters="Regular checkups help catch drift before it becomes a larger gap from your plan.",
                triggered_by=f"Portfolio Health Score = {score:.0f}/100 with no rule triggers active.",
                possible_benefit="Staying on your current plan while monitoring monthly.",
                evidence={
                    "Portfolio Health Score": f"{score:.0f}/100",
                    "Portfolio objective": obj_label,
                    "Recession probability": f"{recession_prob * 100:.0f}%",
                },
                rec_class=REC_CLASS_CORE,
            )
        )
    elif not core_recs:
        # Diagnostics/macro alone must not invent a Core allocation crisis.
        core_recs.append(
            _make_rec_detail(
                "No urgent Core Health allocation flags — diagnostic/macro notes below are supporting context.",
                issue="No urgent Core Health allocation flags detected.",
                why_it_matters=(
                    "Option C Core Health did not surface an objective, construction, risk, or "
                    "constraint action. Review diagnostics as context only."
                ),
                triggered_by=f"Portfolio Health Score = {score:.0f}/100; Core actionable list empty.",
                possible_benefit="Stay on plan unless objective drift or a Core pillar flags a change.",
                evidence={
                    "Portfolio Health Score": f"{score:.0f}/100",
                    "Portfolio objective": obj_label,
                    "Diagnostic notes": str(len(diagnostic_recs)),
                    "Macro notes": str(len(macro_recs)),
                },
                rec_class=REC_CLASS_CORE,
            )
        )

    recommendation_details = finalize_recommendation_details(
        core_recs, macro_recs, diagnostic_recs
    )
    recommendations = [d.text for d in recommendation_details]

    action_plan = _build_portfolio_action_plan(
        score=score,
        objective=objective,
        recommendation_details=recommendation_details,
        profile=profile,
        recession_prob=recession_prob,
        avg_drift=avg_drift,
        max_w=max_w,
    )

    alloc_compare = pd.DataFrame(
        {
            "Category": ["Equity", "Bonds", "T-Bills"],
            "Current (%)": [
                float(profile["equity"]) * 100,
                float(profile["bonds"]) * 100,
                float(profile["tbills"]) * 100,
            ],
            "Objective (%)": [
                round(obj_eq * 100, 1),
                round(obj_bond * 100, 1),
                round(obj_tb * 100, 1),
            ],
            "Recommended (%)": [
                round(float(rec_mix.get("equity", obj_eq)) * 100, 1),
                round(float(rec_mix.get("bonds", obj_bond)) * 100, 1),
                round(float(rec_mix.get("tbills", obj_tb)) * 100, 1),
            ],
        }
    )
    if optimizer_weights is not None:
        opt_eq = sum(opt_w[i] for i, at in enumerate(asset_types) if at in ("Equity", "REIT", "Dividend ETF"))
        opt_bond = sum(opt_w[i] for i, at in enumerate(asset_types) if at == "Bonds")
        opt_tb = sum(opt_w[i] for i, at in enumerate(asset_types) if at == "T-Bills")
        alloc_compare["Optimizer (%)"] = [
            round(float(opt_eq) * 100, 1),
            round(float(opt_bond) * 100, 1),
            round(float(opt_tb) * 100, 1),
        ]

    # ── Status message ──
    health_word = (
        "well aligned with your plan"
        if score >= 85
        else "mostly on plan"
        if score >= 70
        else "mixed in plan alignment"
        if score >= 55
        else "needing attention vs your plan"
        if score >= 40
        else "off plan versus your stated objective"
    )
    weak_pillars = sorted(
        ((k, v) for k, v in breakdown.items()),
        key=lambda kv: kv[1] / HEALTH_CORE_PILLAR_MAX[kv[0]],
    )
    weakest_name, weakest_pts = weak_pillars[0]
    weakest_max = HEALTH_CORE_PILLAR_MAX[weakest_name]
    conc_note = concentration_status_note(
        top_ticker=str(profile["top_ticker"]),
        top_weight=float(max_w),
        kind=str(conc_diag.get("kind") or "unknown"),
        concentration_pillar_pts=float(s_conc),
        conc_engine_pts=float(construction_diag.get("conc_engine_pts") or 0.0),
    )
    status_message = (
        f"Core Portfolio Health is {health_word} ({score:.0f}/100) based on "
        f"objective fit, construction, risk appropriateness, and policy-relative delivery. "
        f"Lowest pillar right now: {weakest_name} ({weakest_pts:.1f}/{weakest_max:.0f})."
        f"{conc_note} "
        f"Sharpe ({raw_sharpe:.2f}) and Sortino ({port_sortino:.2f}) are diagnostics — "
        f"not Health points. "
        f"This is model-based commentary for educational purposes — not financial advice."
    )

    rebalance_df = enrich_rebalance_with_dollars(rebalance_df, initial_value)
    alloc_compare = enrich_allocation_compare_with_dollars(alloc_compare, initial_value)
    recommendation_details = enrich_recommendation_details_with_dollars(
        recommendation_details, tickers, w, initial_value, obj_label
    )
    recommendations = [d.text for d in recommendation_details]

    return PortfolioHealthResult(
        score=score,
        score_label=score_label,
        score_color=score_color,
        status_message=status_message,
        whats_working=whats_working,
        whats_not_working=whats_not,
        recommendations=recommendations,
        recommendation_details=recommendation_details,
        action_plan=action_plan,
        macro_fit=macro_fit,
        rebalance_df=rebalance_df,
        return_contrib_df=ret_contrib,
        risk_contrib_df=risk_df,
        drawdown_contrib_df=dd_contrib,
        allocation_compare_df=alloc_compare,
        macro_heatmap_df=macro_heatmap,
        score_breakdown=breakdown,
        avg_drift=float(avg_drift),
        objective=objective,
        policy_benchmark_label=policy_label,
        policy_benchmark_detail=policy_detail,
        max_pairwise_abs_corr=float(max_corr),
        pillar_explanations=pillar_explanations,
        construction_subscores=construction_subscores,
        health_diagnostics=health_diagnostics,
        macro_check_score=float(s_macro),
        macro_check_max=10.0,
    )


@dataclass(frozen=True)
class InvestmentPlanResult:
    total_available: float
    suggested_emergency_reserve: float
    short_term_cash_amount: float
    debt_reserve: float
    amount_potentially_investable: float
    long_term_suggested: float
    short_term_investable: float
    monthly_contribution: float
    summary_lines: list[str]
    educational_notes: list[str]
    money_needed_1_2_years: float = 0.0
    planned_large_expenses: float = 0.0
    long_term_allocation_pct: float = 0.0
    safer_sleeve_allocation_pct: float = 0.0

    def to_dict(self) -> dict[str, float | list[str]]:
        """Stable dict view (includes legacy key aliases for UI fallbacks)."""
        return {
            "total_available": self.total_available,
            "emergency_reserve": self.suggested_emergency_reserve,
            "short_term_reserve": self.short_term_cash_amount,
            "debt_reserve": self.debt_reserve,
            "available_to_invest": self.amount_potentially_investable,
            "suggested_long_term_amount": self.long_term_suggested,
            "suggested_safer_amount": self.short_term_investable,
            "monthly_contribution": self.monthly_contribution,
            "money_needed_1_2_years": self.money_needed_1_2_years,
            "planned_large_expenses": self.planned_large_expenses,
            "long_term_allocation_pct": self.long_term_allocation_pct,
            "safer_sleeve_allocation_pct": self.safer_sleeve_allocation_pct,
            "summary_lines": list(self.summary_lines),
            "educational_notes": list(self.educational_notes),
            "rationale": list(self.educational_notes),
        }


def investment_plan_long_term_pct(*, horizon_years: int, risk_tolerance: str) -> float:
    """
    Share of *investable* cash suggested for long-term investing (remainder → safer sleeve).

    Base by horizon: ≤2y → 30%, ≤5y → 60%, else 85%. Adjusted by risk tolerance (Low −12pp, High +5pp),
    clipped to 20%–92%. Documented for UI transparency; logic may change in a future redesign.
    """
    if horizon_years <= 2:
        long_pct = 0.30
    elif horizon_years <= 5:
        long_pct = 0.60
    else:
        long_pct = 0.85
    risk_adj = {"Low": -0.12, "Medium": 0.0, "High": 0.05}.get(risk_tolerance, 0.0)
    return float(np.clip(long_pct + risk_adj, 0.20, 0.92))


def compute_investment_plan(
    total_available: float,
    emergency_fund_needed: float,
    money_needed_1_2_years: float,
    existing_debt_obligations: float,
    planned_large_expenses: float,
    horizon_years: int,
    risk_tolerance: str,
    monthly_contribution: float = 0.0,
    *,
    current_monthly_investment: float | None = None,
) -> InvestmentPlanResult:
    """Educational estimate of how much cash may be available to invest."""
    current = current_monthly_investment
    if current is None and monthly_contribution > 0:
        current = float(monthly_contribution)
    emergency = max(0.0, float(emergency_fund_needed))
    near_term = max(0.0, float(money_needed_1_2_years))
    planned_exp = max(0.0, float(planned_large_expenses))
    short_term = near_term + planned_exp
    debt = max(0.0, float(existing_debt_obligations))
    total = max(0.0, float(total_available))
    reserved = emergency + short_term + debt
    investable = max(0.0, total - reserved)

    long_pct = investment_plan_long_term_pct(
        horizon_years=int(horizon_years),
        risk_tolerance=str(risk_tolerance),
    )
    safer_pct = 1.0 - long_pct
    long_term = round(investable * long_pct)
    short_term_inv = max(0.0, round(investable) - long_term)

    pct_label = f"{long_pct * 100:.0f}%"
    safer_label = f"{safer_pct * 100:.0f}%"

    summary = [
        f"Total available cash: ${total:,.0f}",
        f"Emergency fund reserved: ${emergency:,.0f}",
        f"Money needed in 1–2 years: ${near_term:,.0f}",
        f"Planned large expenses reserved: ${planned_exp:,.0f}",
        f"Debt / obligations reserved: ${debt:,.0f}",
        f"Maximum potentially available to invest: ${investable:,.0f}",
        f"Long-term sleeve ({pct_label} of investable): ${long_term:,.0f}",
        f"Conservative / short-term reserve ({safer_label} of investable): ${short_term_inv:,.0f}",
    ]
    if current is not None and current > 0:
        summary.append(
            f"Current monthly investment noted: ${current:,.0f}/month (not a recommendation)"
        )
    elif current is not None and current <= 0:
        summary.append(
            "Current monthly investment noted: $0/month "
            "(no regular monthly investments entered; not a recommendation)"
        )

    notes = [
        "Investable amount = total cash − emergency − near-term needs − planned expenses − debt obligations.",
        "One-time investable cash and recurring monthly investments are separate; "
        "this plan does not divide available cash by 12 to infer a monthly amount.",
        f"Long-term vs safer split uses {pct_label} / {safer_label} of the investable amount "
        f"(from horizon {horizon_years}y and {risk_tolerance} risk tolerance).",
        "Consider keeping short-term needs in cash or T-bill style assets — educational estimate only.",
        "This is for educational purposes only, not financial advice.",
    ]
    return InvestmentPlanResult(
        total_available=total,
        suggested_emergency_reserve=emergency,
        short_term_cash_amount=short_term,
        debt_reserve=debt,
        amount_potentially_investable=investable,
        long_term_suggested=float(long_term),
        short_term_investable=float(short_term_inv),
        monthly_contribution=float(current if current is not None else 0.0),
        summary_lines=summary,
        educational_notes=notes,
        money_needed_1_2_years=near_term,
        planned_large_expenses=planned_exp,
        long_term_allocation_pct=long_pct,
        safer_sleeve_allocation_pct=safer_pct,
    )


def enrich_rebalance_with_dollars(rebalance_df: pd.DataFrame, initial_value: float) -> pd.DataFrame:
    """Add dollar columns and change guidance to rebalance table."""
    if rebalance_df.empty or initial_value <= 0:
        return rebalance_df
    out = rebalance_df.copy()
    pct_cols = {
        "Current (%)": "Current ($)",
        "Objective (%)": "Objective ($)",
        "Optimizer (%)": "Optimizer ($)",
        "Recommended (%)": "Recommended ($)",
    }
    for pct_col, dollar_col in pct_cols.items():
        if pct_col in out.columns:
            out[dollar_col] = (out[pct_col] / 100.0 * initial_value).round(0)

    if "Current (%)" in out.columns and "Objective (%)" in out.columns:
        out["Change (pp)"] = (out["Objective (%)"] - out["Current (%)"]).round(1)
        out["Dollar Change ($)"] = (out["Change (pp)"] / 100.0 * initial_value).round(0)
        notes = []
        for _, row in out.iterrows():
            ch_pp = float(row["Change (pp)"])
            ch_d = float(row["Dollar Change ($)"])
            if abs(ch_pp) < 1.0:
                notes.append("Within tolerance")
            elif ch_pp < 0:
                notes.append(
                    f"Consider reducing {row['Ticker']} by {abs(ch_pp):.1f} pp, about ${abs(ch_d):,.0f}."
                )
            else:
                notes.append(
                    f"Consider increasing {row['Ticker']} by {ch_pp:.1f} pp, about ${ch_d:,.0f}."
                )
        out["Dollar Guidance"] = notes
    return out


def enrich_allocation_compare_with_dollars(alloc_df: pd.DataFrame, initial_value: float) -> pd.DataFrame:
    if alloc_df.empty or initial_value <= 0:
        return alloc_df
    out = alloc_df.copy()
    for pct_col in ("Current (%)", "Objective (%)", "Recommended (%)"):
        if pct_col in out.columns:
            out[pct_col.replace("(%)", "($)")] = (out[pct_col] / 100.0 * initial_value).round(0)
    return out


def enrich_recommendation_details_with_dollars(
    details: list[RecommendationDetail],
    tickers: list[str],
    weights: np.ndarray,
    initial_value: float,
    objective_label: str,
) -> list[RecommendationDetail]:
    """Add dollar context to recommendation copy when portfolio value is known."""
    if initial_value <= 0:
        return details
    w = normalize_weights(weights)
    enriched: list[RecommendationDetail] = []
    for d in details:
        ev = dict(d.evidence)
        top_t = ev.get("Largest holding") or ev.get("Ticker")
        if top_t and top_t in tickers:
            idx = tickers.index(top_t)
            pct = w[idx] * 100
            dollars = initial_value * w[idx]
            ev["Approx. dollar amount"] = f"${dollars:,.0f} ({pct:.1f}%)"
        text = d.text
        if top_t and ("Largest holding" in d.issue or "concentration" in d.issue.lower()):
            text = (
                f"{top_t} is about {w[tickers.index(top_t)] * 100:.1f}% of your portfolio "
                f"(~${initial_value * w[tickers.index(top_t)]:,.0f}). "
                f"The model suggests reviewing whether concentration fits your {objective_label} goal."
            )
        enriched.append(
            RecommendationDetail(
                text=text,
                issue=d.issue,
                why_it_matters=d.why_it_matters,
                triggered_by=d.triggered_by,
                possible_benefit=d.possible_benefit,
                evidence=ev,
                rec_class=getattr(d, "rec_class", REC_CLASS_CORE),
            )
        )
    return enriched


def suggested_weights_from_rebalance(
    rebalance_df: pd.DataFrame,
    tickers: list[str],
    current_weights: np.ndarray,
    *,
    target_column: str = "Objective (%)",
) -> np.ndarray:
    """Build weight vector from rebalance table target column.

    Skips explicit unrepresented (orphan) sleeve rows so Apply does not invent
    holdings. Represented ticker targets are then normalized to a valid 100%
    book among current holdings only.
    """
    w = normalize_weights(current_weights)
    if target_column not in rebalance_df.columns:
        return w
    lookup: dict[str, float] = {}
    for _, row in rebalance_df.iterrows():
        if is_orphan_rebalance_row(row):
            continue
        ticker = str(row["Ticker"])
        lookup[ticker] = float(row[target_column]) / 100.0
    new_w = np.array([lookup.get(t, w[i]) for i, t in enumerate(tickers)], dtype=float)
    if new_w.sum() <= 0:
        return w
    return normalize_weights(new_w)


def holdings_records_from_weights(
    tickers: list[str],
    weights: np.ndarray,
    asset_types: list[str],
) -> list[dict]:
    w = normalize_weights(weights)
    return [
        {
            "Ticker": tickers[i],
            "Weight (%)": round(float(w[i]) * 100, 1),
            "Asset Type": asset_types[i] if i < len(asset_types) else "Equity",
        }
        for i in range(len(tickers))
    ]
