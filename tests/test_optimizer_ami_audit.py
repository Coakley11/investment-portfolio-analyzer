"""Optimizer / Recommended mix / AMI context correctness."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pandas as pd

import portfolio_core as core
from applied_math_context import build_investment_applied_math_context


_PILOT = ["VTI", "VXUS", "BND", "VNQ"]
_PILOT_T = ["Equity", "Equity", "Bonds", "REIT"]
_PILOT_W = np.array([0.40, 0.20, 0.30, 0.10])


class TestCategoryKeyNormalization(unittest.TestCase):
    def test_title_case_recommend_keys_map_to_targets(self) -> None:
        mix = {"Equity": 0.60, "Bonds": 0.30, "T-Bills": 0.10}
        norm = core.normalize_objective_category_weights(mix)
        self.assertAlmostEqual(norm["equity"], 0.60)
        self.assertAlmostEqual(norm["bonds"], 0.30)
        self.assertAlmostEqual(norm["tbills"], 0.10)
        w, orphans = core.build_category_preserving_ticker_targets(
            _PILOT, _PILOT_T, mix
        )
        self.assertAlmostEqual(float(w[0]), 0.20, places=6)  # VTI
        self.assertAlmostEqual(float(w[2]), 0.30, places=6)  # BND
        self.assertEqual(len(orphans), 1)
        self.assertAlmostEqual(float(orphans[0]["weight"]), 0.10, places=6)

    def test_recommend_portfolio_allocation_lowercase(self) -> None:
        rec = core.recommend_portfolio(35, 15, "Medium", "Medium", "balanced growth")
        self.assertIn("equity", rec.allocation)
        self.assertNotIn("Equity", rec.allocation)
        w, orphans = core.build_category_preserving_ticker_targets(
            _PILOT, _PILOT_T, rec.allocation
        )
        self.assertGreater(float(w.sum()), 0.5)
        self.assertTrue(any(float(o["weight"]) > 0 for o in orphans) or float(w.sum()) > 0.89)


class TestOptimizerConstraints(unittest.TestCase):
    def test_weights_sum_to_one(self) -> None:
        rng = np.random.default_rng(0)
        n = 4
        mu = rng.normal(0.08, 0.03, size=n)
        a = rng.normal(0.0, 0.02, size=(n, n))
        cov = a @ a.T + np.eye(n) * 0.01
        ms = core.optimize_max_sharpe(mu, cov, 0.04, n)
        mv = core.optimize_min_volatility(mu, cov, 0.04, n)
        self.assertAlmostEqual(float(ms.weights.sum()), 1.0, places=6)
        self.assertAlmostEqual(float(mv.weights.sum()), 1.0, places=6)
        self.assertTrue(np.all(ms.weights >= -1e-9))
        self.assertTrue(np.all(mv.weights >= -1e-9))

    def test_mean_cov_and_optimizer_permutation_invariant(self) -> None:
        """μ/Σ for optimizer must follow holdings tickers, not column order."""
        specs = {
            "VTI": (0.00055, 0.010),
            "VXUS": (0.00035, 0.012),
            "BND": (0.00008, 0.003),
            "VNQ": (0.00040, 0.014),
        }
        idx = pd.date_range("2019-01-01", periods=260, freq="B")

        def _rets(cols: list[str]) -> pd.DataFrame:
            data = {}
            for col in cols:
                mu, sigma = specs[col]
                rng = np.random.default_rng(42 + hash(col) % 10_000)
                data[col] = rng.normal(mu, sigma, size=len(idx))
            return pd.DataFrame(data, index=idx)

        orders = [
            list(_PILOT),
            ["BND", "VNQ", "VTI", "VXUS"],
            ["VNQ", "VTI", "BND", "VXUS"],
        ]
        packs = []
        for cols in orders:
            mu, cov, aligned = core.annualized_mean_and_cov(
                _rets(cols), _PILOT, _PILOT_W
            )
            self.assertEqual(list(aligned.columns), list(_PILOT))
            self.assertEqual(list(cov.index), list(_PILOT))
            ms = core.optimize_max_sharpe(mu, cov.values, 0.04, len(_PILOT))
            packs.append(ms.weights.copy())
        for other in packs[1:]:
            np.testing.assert_allclose(packs[0], other, rtol=1e-9, atol=1e-9)

        # Positional .values without align must NOT match holdings-labeled μ.
        alpha = _rets(["BND", "VNQ", "VTI", "VXUS"])
        wrong_mu = alpha.mean().to_numpy(dtype=float) * float(core.TRADING_DAYS)
        right_mu, _, _ = core.annualized_mean_and_cov(alpha, _PILOT, _PILOT_W)
        self.assertFalse(np.allclose(wrong_mu, right_mu, rtol=1e-6, atol=1e-6))


class TestAmiHealthDiagnostics(unittest.TestCase):
    def test_reads_health_diagnostics_not_missing_attrs(self) -> None:
        health = SimpleNamespace(
            score=81.0,
            health_diagnostics={
                "annual_return": 0.0738,
                "annual_volatility": 0.1187,
                "portfolio_sharpe": 0.285,
                "raw_sharpe": 0.285,
                "max_drawdown": -0.2329,
            },
        )
        st = MagicMock()
        st.session_state = {
            "health_result": health,
            "holdings_df": pd.DataFrame(
                {
                    "Ticker": _PILOT,
                    "Weight (%)": [40, 20, 30, 10],
                    "Asset Type": _PILOT_T,
                }
            ),
            "sidebar_portfolio_value": 4250.0,
        }
        ctx = build_investment_applied_math_context("Portfolio Health", st.session_state)
        self.assertIn("sharpe_ratio", ctx)
        self.assertIn("0.28", str(ctx["sharpe_ratio"]))
        self.assertIn("7.4", str(ctx["expected_return"]))
        self.assertTrue(str(ctx["expected_return"]).endswith("%"))
        self.assertIn("volatility", ctx)
        self.assertIn("max_drawdown", ctx)


if __name__ == "__main__":
    unittest.main()
