"""Document intended Fair Value vs Expensive forward invariances (read-only methodology).

Valuation Environment adjusts portfolio-level forward return/vol via
``_valuation_effects``, but:
- Stress-Adjusted Max Drawdown scales historical DD by recession only
- Optimizer μ uses ``type_shifts`` (rate/inflation/selected regimes) and does
  **not** include valuation — so Max-Sharpe return can stay fixed while vol rises
"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

import portfolio_core as core

_TICKERS = ["VTI", "VXUS", "BND", "VNQ"]
_W = np.array([0.40, 0.20, 0.30, 0.10], dtype=float)
_TYPES = ["Equity", "Equity", "Bonds", "REIT"]
_RF = 0.04


def _synthetic_returns(seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2016-01-01", periods=800, freq="B")
    specs = {
        "VTI": (0.00055, 0.010),
        "VXUS": (0.00035, 0.012),
        "BND": (0.00008, 0.003),
        "VNQ": (0.00040, 0.014),
    }
    return pd.DataFrame(
        {t: rng.normal(mu, sig, size=len(idx)) for t, (mu, sig) in specs.items()},
        index=idx,
    )


def _assumptions(valuation: str) -> core.ForwardMacroAssumptions:
    return core.ForwardMacroAssumptions(
        rate_environment="Stable Rates",
        inflation="Moderate Inflation",
        recession_probability=0.25,
        valuation=valuation,
        economic_regime="Expansion",
    )


def _forward(valuation: str):
    rets = _synthetic_returns()
    aligned, w, used = core.align_returns_and_weights(rets, _W, tickers=_TICKERS)
    mean_rets, cov, _ = core.annualized_mean_and_cov(aligned, tickers=list(used), weights=w)
    metrics = core.compute_extended_metrics(aligned, w, _RF, 4250.0, tickers=list(used))
    fwd = core.compute_forward_projection_with_profile(
        metrics=metrics,
        mean_returns=mean_rets.copy(),
        cov=cov.values.copy(),
        tickers=list(used),
        weights=w,
        asset_types=_TYPES,
        assumptions=_assumptions(valuation),
        initial_value=4250.0,
        years=5.0,
        risk_free_rate=_RF,
    )
    return metrics, fwd, list(used), w


class TestValuationForwardPropagationInvariances(unittest.TestCase):
    def test_portfolio_forward_return_shifts_by_equity_weighted_valuation(self) -> None:
        _metrics, fair, _, _ = _forward("Fair Value")
        _metrics2, exp, _, _ = _forward("Expensive")
        profile = core.allocation_profile(_TICKERS, _W, _TYPES)
        expected = -0.015 * float(profile["equity"])
        self.assertAlmostEqual(exp.adjusted_return - fair.adjusted_return, expected, places=12)
        self.assertAlmostEqual(
            exp.adjusted_volatility / fair.adjusted_volatility, 1.08, places=12
        )

    def test_forward_max_drawdown_invariant_to_valuation_at_fixed_recession(self) -> None:
        metrics, fair, _, _ = _forward("Fair Value")
        _, exp, _, _ = _forward("Expensive")
        drawdown_mult = 1.0 + 0.25 * 0.90
        self.assertAlmostEqual(fair.adjusted_max_drawdown, metrics.max_drawdown * drawdown_mult)
        self.assertEqual(fair.adjusted_max_drawdown, exp.adjusted_max_drawdown)

    def test_optimizer_mu_and_max_sharpe_return_invariant_to_valuation(self) -> None:
        _, fair, used, _ = _forward("Fair Value")
        _, exp, _, _ = _forward("Expensive")
        self.assertTrue(np.allclose(fair.adjusted_mean_returns, exp.adjusted_mean_returns))
        # Valuation scales Σ uniformly via vol_scale; μ is unchanged, so Max-Sharpe
        # expected return is invariant even if SLSQP weight dust differs slightly.
        fair_opt = core.optimize_max_sharpe(
            fair.adjusted_mean_returns, fair.adjusted_cov, _RF, len(used)
        )
        exp_opt = core.optimize_max_sharpe(
            exp.adjusted_mean_returns, exp.adjusted_cov, _RF, len(used)
        )
        self.assertAlmostEqual(fair_opt.annual_return, exp_opt.annual_return, places=4)
        self.assertGreater(exp_opt.volatility, fair_opt.volatility)
        # Uniform Σ scale from valuation leaves Max-Sharpe return effectively unchanged
        # (display rounds to 0.01%); vol and Sharpe move.
        self.assertLess(
            abs(fair_opt.annual_return - exp_opt.annual_return),
            5e-5,
            "Max-Sharpe return should be valuation-invariant under current μ construction",
        )
        self.assertLess(exp_opt.sharpe_ratio, fair_opt.sharpe_ratio)
        # Same μ under both valuations: return equals w·μ for each solution.
        self.assertAlmostEqual(
            float(np.dot(fair_opt.weights, fair.adjusted_mean_returns)),
            fair_opt.annual_return,
            places=10,
        )
        self.assertAlmostEqual(
            float(np.dot(exp_opt.weights, exp.adjusted_mean_returns)),
            exp_opt.annual_return,
            places=10,
        )


if __name__ == "__main__":
    unittest.main()
