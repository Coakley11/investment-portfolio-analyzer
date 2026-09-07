"""Monte Carlo / scenario correctness regressions."""

from __future__ import annotations

import inspect
import unittest

import numpy as np
import pandas as pd

import portfolio_core as core


_PILOT = ["VTI", "VXUS", "BND", "VNQ"]
_PILOT_W = np.array([0.40, 0.20, 0.30, 0.10], dtype=float)
_PILOT_T = ["Equity", "Equity", "Bonds", "REIT"]
_INITIAL = 4250.0
_SEED = 42
_SERIES = {
    "VTI": (0.00055, 0.010),
    "VXUS": (0.00035, 0.012),
    "BND": (0.00008, 0.003),
    "VNQ": (0.00040, 0.014),
}


def _rets(columns: list[str], *, periods: int = 260, seed: int = 11) -> pd.DataFrame:
    idx = pd.date_range("2019-01-01", periods=periods, freq="B")
    data = {}
    for col in columns:
        mu, sigma = _SERIES[col]
        rng = np.random.default_rng(seed + hash(col) % 10_000)
        data[col] = rng.normal(mu, sigma, size=periods)
    return pd.DataFrame(data, index=idx)


class TestMonteCarloAlignmentAndCapital(unittest.TestCase):
    def test_a_permutation_invariance_of_moments_and_summary(self) -> None:
        summaries = []
        for cols in (
            ["VTI", "VXUS", "BND", "VNQ"],
            ["BND", "VNQ", "VTI", "VXUS"],
            ["VXUS", "VTI", "VNQ", "BND"],
        ):
            rets = _rets(cols)
            mc = core.monte_carlo_simulation(
                rets,
                _PILOT_W,
                _INITIAL,
                years=3,
                simulations=400,
                seed=_SEED,
                tickers=_PILOT,
            )
            summaries.append(
                (mc.summary["p50"], mc.summary["prob_loss"], mc.summary["mean"])
            )
        for other in summaries[1:]:
            np.testing.assert_allclose(summaries[0], other, rtol=1e-12, atol=1e-12)

    def test_b_wrong_ticker_identity_changes_results(self) -> None:
        rets = _rets(_PILOT)
        correct = core.monte_carlo_simulation(
            rets, _PILOT_W, _INITIAL, years=2, simulations=300, seed=_SEED, tickers=_PILOT
        )
        wrong = core.monte_carlo_simulation(
            rets,
            _PILOT_W,
            _INITIAL,
            years=2,
            simulations=300,
            seed=_SEED,
            tickers=["BND", "VNQ", "VTI", "VXUS"],
        )
        self.assertGreater(abs(correct.summary["p50"] - wrong.summary["p50"]), 1.0)

    def test_c_starting_value_exactly_4250(self) -> None:
        rets = _rets(_PILOT)
        mc = core.monte_carlo_simulation(
            rets, _PILOT_W, _INITIAL, years=1, simulations=200, seed=_SEED, tickers=_PILOT
        )
        day0 = mc.chart_df.loc[mc.chart_df["Day"] == 0].iloc[0]
        self.assertAlmostEqual(float(day0["Median"]), _INITIAL, places=9)
        for p in (5, 25, 75, 95):
            self.assertAlmostEqual(float(day0[f"{p}th Percentile"]), _INITIAL, places=9)


class TestMonteCarloHorizonPercentilesSeed(unittest.TestCase):
    def test_d_horizon_scaling(self) -> None:
        rets = _rets(_PILOT)
        y1 = core.monte_carlo_simulation(
            rets, _PILOT_W, _INITIAL, years=1, simulations=500, seed=_SEED, tickers=_PILOT
        )
        y5 = core.monte_carlo_simulation(
            rets, _PILOT_W, _INITIAL, years=5, simulations=500, seed=_SEED, tickers=_PILOT
        )
        self.assertEqual(int(y1.chart_df["Day"].max()), core.TRADING_DAYS)
        self.assertEqual(int(y5.chart_df["Day"].max()), 5 * core.TRADING_DAYS)
        # Longer horizon disperses endings more under same μ/σ seed family.
        self.assertGreater(float(np.std(y5.ending_values)), float(np.std(y1.ending_values)))

    def test_e_percentile_ordering(self) -> None:
        rets = _rets(_PILOT)
        mc = core.monte_carlo_simulation(
            rets, _PILOT_W, _INITIAL, years=4, simulations=800, seed=_SEED, tickers=_PILOT
        )
        s = mc.summary
        self.assertLessEqual(s["p5"], s["p25"])
        self.assertLessEqual(s["p25"], s["p50"])
        self.assertLessEqual(s["p50"], s["p75"])
        self.assertLessEqual(s["p75"], s["p95"])

    def test_f_fixed_seed_reproducibility(self) -> None:
        rets = _rets(_PILOT)
        a = core.monte_carlo_simulation(
            rets, _PILOT_W, _INITIAL, years=2, simulations=250, seed=_SEED, tickers=_PILOT
        )
        b = core.monte_carlo_simulation(
            rets, _PILOT_W, _INITIAL, years=2, simulations=250, seed=_SEED, tickers=_PILOT
        )
        np.testing.assert_allclose(a.ending_values, b.ending_values)
        self.assertEqual(a.summary["p50"], b.summary["p50"])

    def test_g_changed_weights_change_results(self) -> None:
        rets = _rets(_PILOT)
        a = core.monte_carlo_simulation(
            rets, _PILOT_W, _INITIAL, years=2, simulations=300, seed=_SEED, tickers=_PILOT
        )
        heavy_equity = np.array([0.70, 0.20, 0.05, 0.05])
        b = core.monte_carlo_simulation(
            rets, heavy_equity, _INITIAL, years=2, simulations=300, seed=_SEED, tickers=_PILOT
        )
        self.assertGreater(abs(a.summary["mean"] - b.summary["mean"]), 1.0)

    def test_h_deposits_excluded_from_return_path(self) -> None:
        src = inspect.getsource(core.monte_carlo_simulation)
        # Compounding loop is return-only; no cashflow operators on the path.
        self.assertIn("paths[:, t] = paths[:, t - 1] * (1 + shocks[:, t - 1])", src)
        self.assertIn("paths[:, 0] = start_val", src)
        body = src.split('"""', 2)[-1]  # exclude docstring mentions
        self.assertNotIn("monthly_contribution", body)
        self.assertNotIn("cash_deposit", body)
        self.assertNotIn("+ deposit", body.lower())


class TestMonteCarloProbabilityAndCacheDocs(unittest.TestCase):
    def test_k_probability_of_loss_definition(self) -> None:
        rets = _rets(_PILOT)
        mc = core.monte_carlo_simulation(
            rets,
            _PILOT_W,
            _INITIAL,
            years=3,
            simulations=500,
            seed=_SEED,
            tickers=_PILOT,
            target_value=_INITIAL * 1.75,
        )
        expected = float((mc.ending_values < _INITIAL).mean())
        self.assertAlmostEqual(mc.summary["prob_loss"], expected, places=12)
        self.assertAlmostEqual(mc.summary["prob_below_start"], expected, places=12)
        self.assertAlmostEqual(
            mc.summary["prob_reach_target"],
            float((mc.ending_values >= _INITIAL * 1.75).mean()),
            places=12,
        )

    def test_l_cache_wrapper_includes_key_inputs(self) -> None:
        from streamlit_app import compute_monte_carlo

        sig = inspect.signature(compute_monte_carlo)
        for name in (
            "returns",
            "weights_tuple",
            "initial_value",
            "years",
            "simulations",
            "target_value",
            "expected_annual_return",
            "expected_annual_volatility",
            "tickers_tuple",
        ):
            self.assertIn(name, sig.parameters)


class TestScenarioEngine(unittest.TestCase):
    def test_i_scenario_mapping_uses_economic_types(self) -> None:
        # macro_regime maps Bonds/REIT/Equity — not bare "ETF".
        src = inspect.getsource(core.macro_regime_analysis)
        self.assertIn('at == "Bonds"', src)
        self.assertIn("REIT", src)
        self.assertNotIn('== "ETF"', src)

        rets = _rets(_PILOT)
        metrics = core.compute_extended_metrics(rets, _PILOT_W, 0.04, _INITIAL, tickers=_PILOT)
        before = _PILOT_W.copy()
        df = core.macro_regime_analysis(
            metrics, _INITIAL, years=1, weights=_PILOT_W, asset_types=_PILOT_T
        )
        self.assertFalse(df.empty)
        np.testing.assert_allclose(before, _PILOT_W)

    def test_j_scenario_engine_does_not_mutate_weights(self) -> None:
        rets = _rets(_PILOT)
        w = _PILOT_W.copy()
        _ = core.scenario_analysis(rets, w, _INITIAL, tickers=_PILOT)
        np.testing.assert_allclose(w, _PILOT_W)
        names = set(core.scenario_analysis(rets, w, _INITIAL, tickers=_PILOT)["Scenario"])
        self.assertTrue(any("Stagflation-like" in n for n in names))
        self.assertFalse(any("high vol" in n.lower() for n in names))

    def test_docstring_not_claiming_classical_gbm_only(self) -> None:
        doc = core.monte_carlo_simulation.__doc__ or ""
        self.assertIn("Parametric portfolio Monte Carlo", doc)
        self.assertIn("pointwise", doc.lower())


if __name__ == "__main__":
    unittest.main()
