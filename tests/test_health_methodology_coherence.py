"""Regression: Health policy benchmark, diversification, kind-aware concentration."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

import portfolio_core as core
from investment_ami.decision_support.real_portfolio_security_types import (
    BROAD_MARKET_ETF_TICKERS,
    classify_ticker_security,
)


_PILOT = ["VTI", "VXUS", "BND", "VNQ"]
_PILOT_W = np.array([0.40, 0.20, 0.30, 0.10])
_PILOT_T = ["Equity", "Equity", "Bonds", "REIT"]


def _assumptions() -> core.ForwardMacroAssumptions:
    return core.ForwardMacroAssumptions(
        rate_environment="Stable Rates",
        inflation="Moderate Inflation",
        valuation="Fair",
        economic_regime="Expansion",
        recession_probability=0.25,
    )


class TestPolicyBenchmarkConstruction(unittest.TestCase):
    def test_balanced_growth_uses_60_30_10_proxies_not_100_spy(self) -> None:
        idx = pd.date_range("2020-01-01", periods=80, freq="B")
        rng = np.random.default_rng(10)
        # Make SPY distinctly higher return than AGG/BIL so a 100% SPY benchmark
        # would differ from a 60/30/10 policy mix.
        spy = pd.Series(rng.normal(0.0008, 0.01, size=len(idx)), index=idx)
        agg = pd.Series(rng.normal(0.0001, 0.003, size=len(idx)), index=idx)
        bil = pd.Series(rng.normal(0.00005, 0.0005, size=len(idx)), index=idx)
        proxy = pd.DataFrame({"SPY": spy, "AGG": agg, "BIL": bil})
        series, meta = core.build_policy_benchmark_returns(proxy, "balanced growth")
        self.assertTrue(meta["ok"])
        self.assertAlmostEqual(meta["weights"]["equity"], 0.60, places=6)
        self.assertAlmostEqual(meta["weights"]["bonds"], 0.30, places=6)
        self.assertAlmostEqual(meta["weights"]["tbills"], 0.10, places=6)
        self.assertIsNotNone(series)
        assert series is not None
        expected = 0.6 * spy + 0.3 * agg + 0.1 * bil
        pd.testing.assert_series_equal(series, expected, check_names=False)
        self.assertFalse(np.allclose(series.values, spy.values))

    def test_aggressive_growth_policy_weights(self) -> None:
        idx = pd.date_range("2020-01-01", periods=40, freq="B")
        proxy = pd.DataFrame(
            {
                "SPY": np.linspace(0.001, 0.002, len(idx)),
                "AGG": np.linspace(0.0001, 0.0002, len(idx)),
                "BIL": np.linspace(0.00005, 0.00006, len(idx)),
            },
            index=idx,
        )
        series, meta = core.build_policy_benchmark_returns(proxy, "aggressive growth")
        self.assertTrue(meta["ok"])
        self.assertAlmostEqual(meta["weights"]["equity"], 0.85, places=6)
        self.assertAlmostEqual(meta["weights"]["bonds"], 0.10, places=6)
        self.assertAlmostEqual(meta["weights"]["tbills"], 0.05, places=6)
        assert series is not None
        self.assertAlmostEqual(float(series.iloc[0]), float(0.85 * 0.001 + 0.10 * 0.0001 + 0.05 * 0.00005), places=8)

    def test_missing_proxy_does_not_silently_use_spy(self) -> None:
        idx = pd.date_range("2020-01-01", periods=40, freq="B")
        proxy = pd.DataFrame({"SPY": np.ones(len(idx)) * 0.001}, index=idx)
        series, meta = core.build_policy_benchmark_returns(proxy, "balanced growth")
        self.assertIsNone(series)
        self.assertFalse(meta["ok"])
        self.assertIn("missing_proxy", str(meta.get("error", "")))

    def test_date_alignment_intersection(self) -> None:
        idx_a = pd.date_range("2020-01-01", periods=50, freq="B")
        idx_b = pd.date_range("2020-02-01", periods=50, freq="B")
        port = pd.Series(np.linspace(0.001, 0.002, len(idx_a)), index=idx_a)
        policy = pd.Series(np.linspace(0.0005, 0.001, len(idx_b)), index=idx_b)
        s_ret, p_ann, pol_ann, n = core.score_return_vs_policy_benchmark(port, policy)
        self.assertGreater(n, 0)
        self.assertLess(n, len(idx_a))
        self.assertLess(n, len(idx_b))
        # Gap thresholds still apply on aligned window (Option C: 20-pt scale).
        allowed = {0.0, 20.0, 16.0, 8.0 * 20.0 / 15.0, 4.0 * 20.0 / 15.0}
        self.assertTrue(any(abs(s_ret - a) < 1e-9 for a in allowed))

    def test_health_return_component_uses_policy_not_spy_label(self) -> None:
        idx = pd.date_range("2020-01-01", periods=80, freq="B")
        rng = np.random.default_rng(11)
        rets = pd.DataFrame(
            {
                "VTI": rng.normal(0.0005, 0.01, size=len(idx)),
                "VXUS": rng.normal(0.00045, 0.011, size=len(idx)),
                "BND": rng.normal(0.0001, 0.003, size=len(idx)),
                "VNQ": rng.normal(0.0004, 0.012, size=len(idx)),
            },
            index=idx,
        )
        # Policy with weak SPY vs strong AGG would not match 100% SPY scoring.
        spy = pd.Series(rng.normal(0.0012, 0.012, size=len(idx)), index=idx)
        agg = pd.Series(rng.normal(0.0002, 0.003, size=len(idx)), index=idx)
        bil = pd.Series(rng.normal(0.00005, 0.0004, size=len(idx)), index=idx)
        policy, meta = core.build_policy_benchmark_returns(
            pd.DataFrame({"SPY": spy, "AGG": agg, "BIL": bil}), "balanced growth"
        )
        metrics = core.compute_extended_metrics(rets, _PILOT_W, 0.04, 4250.0, tickers=_PILOT)
        health = core.evaluate_portfolio_health(
            tickers=_PILOT,
            weights=_PILOT_W,
            asset_types=_PILOT_T,
            metrics=metrics,
            asset_returns=rets,
            corr=rets.corr(),
            risk_contrib_df=core.risk_contribution(rets, _PILOT_W, tickers=_PILOT),
            assumptions=_assumptions(),
            objective="balanced growth",
            risk_free_rate=0.04,
            initial_value=4250.0,
            benchmark_returns=spy,
            policy_benchmark_returns=policy,
            policy_benchmark_meta=meta,
            recommended_type_mix=core.OBJECTIVE_ALLOCATIONS["balanced growth"],
        )
        self.assertIn("Policy-Relative Performance", health.score_breakdown)
        self.assertNotIn("Return vs Benchmark", health.score_breakdown)
        self.assertNotIn("Return vs Policy Benchmark", health.score_breakdown)
        self.assertNotIn("Sharpe Score (pts)", health.score_breakdown)
        self.assertNotIn("Macro Regime Fit", health.score_breakdown)
        self.assertIn("60%", health.policy_benchmark_label)
        self.assertIn("SPY", health.policy_benchmark_detail)
        self.assertIn("AGG", health.policy_benchmark_detail)
        self.assertIn("BIL", health.policy_benchmark_detail)


class TestDiversificationPortfolioLevel(unittest.TestCase):
    def test_pilot_gets_credit_not_forced_to_max(self) -> None:
        # Synthetic corr: equities correlated, bonds diversifying.
        corr = pd.DataFrame(
            [
                [1.0, 0.82, 0.15, 0.70],
                [0.82, 1.0, 0.12, 0.65],
                [0.15, 0.12, 1.0, 0.20],
                [0.70, 0.65, 0.20, 1.0],
            ],
            index=_PILOT,
            columns=_PILOT,
        )
        score, diag = core.score_portfolio_diversification(_PILOT, _PILOT_W, _PILOT_T, corr)
        self.assertGreaterEqual(score, 6.0)
        self.assertLess(score, 12.0)  # not automatically forced to 12
        self.assertGreaterEqual(diag["n_sleeves_ge_min"], 4)
        self.assertGreater(diag["max_abs_corr"], 0.70)  # worst pair still high

    def test_single_ticker_scores_poorly(self) -> None:
        corr = pd.DataFrame([[1.0]], index=["VTI"], columns=["VTI"])
        score, _ = core.score_portfolio_diversification(["VTI"], np.array([1.0]), ["Equity"], corr)
        self.assertLessEqual(score, 2.0)

    def test_highly_correlated_equities_score_worse_than_multi_sleeve(self) -> None:
        tickers = ["VTI", "VOO", "ITOT", "SPY"]
        w = np.ones(4) / 4
        types = ["Equity"] * 4
        corr_hi = pd.DataFrame(np.full((4, 4), 0.95), index=tickers, columns=tickers)
        np.fill_diagonal(corr_hi.values, 1.0)
        score_red, _ = core.score_portfolio_diversification(tickers, w, types, corr_hi)

        corr_div = pd.DataFrame(
            [
                [1.0, 0.75, 0.10, 0.55],
                [0.75, 1.0, 0.12, 0.50],
                [0.10, 0.12, 1.0, 0.15],
                [0.55, 0.50, 0.15, 1.0],
            ],
            index=_PILOT,
            columns=_PILOT,
        )
        score_ok, _ = core.score_portfolio_diversification(_PILOT, _PILOT_W, _PILOT_T, corr_div)
        self.assertLess(score_red, score_ok)


class TestConcentrationKindAware(unittest.TestCase):
    def test_vti_40_differs_from_individual_stock_40(self) -> None:
        s_vti, d_vti = core.score_concentration_risk_kind_aware(
            ["VTI", "VXUS", "BND"], np.array([0.40, 0.30, 0.30]), ["Equity", "Equity", "Bonds"]
        )
        s_aapl, d_aapl = core.score_concentration_risk_kind_aware(
            ["AAPL", "VXUS", "BND"], np.array([0.40, 0.30, 0.30]), ["Equity", "Equity", "Bonds"]
        )
        self.assertEqual(d_vti["kind"], "broad_market_etf")
        self.assertEqual(d_vti["top_ticker"], "VTI")
        self.assertEqual(d_aapl["kind"], "individual_equity")
        self.assertEqual(d_aapl["top_ticker"], "AAPL")
        self.assertGreater(s_vti, s_aapl)
        self.assertEqual(s_vti, 12.0)  # 40% broad ETF within soft band
        self.assertEqual(s_aapl, 4.0)  # 40% single name on strict band

    def test_ami_classification_consistent_for_pilot(self) -> None:
        self.assertIn("VTI", BROAD_MARKET_ETF_TICKERS)
        self.assertEqual(
            classify_ticker_security("VTI", asset_type_label="Equity").kind,
            "broad_market_etf",
        )
        self.assertEqual(
            classify_ticker_security("BND", asset_type_label="Bonds").kind,
            "bond_etf_or_bond_fund",
        )
        self.assertEqual(
            classify_ticker_security("VNQ", asset_type_label="REIT").kind,
            "narrow_or_thematic_etf",
        )


class TestObjectiveAlignmentUnchanged(unittest.TestCase):
    def test_objective_alignment_still_category_60_30_10(self) -> None:
        idx = pd.date_range("2020-01-01", periods=60, freq="B")
        rng = np.random.default_rng(3)
        rets = pd.DataFrame(rng.normal(0.0003, 0.01, size=(len(idx), 4)), index=idx, columns=_PILOT)
        spy = pd.Series(rng.normal(0.0005, 0.01, size=len(idx)), index=idx)
        policy, meta = core.build_policy_benchmark_returns(
            pd.DataFrame(
                {
                    "SPY": spy,
                    "AGG": rng.normal(0.0001, 0.003, size=len(idx)),
                    "BIL": rng.normal(0.00005, 0.0005, size=len(idx)),
                },
                index=idx,
            ),
            "balanced growth",
        )
        metrics = core.compute_extended_metrics(rets, _PILOT_W, 0.04, 4250.0, tickers=_PILOT)
        health = core.evaluate_portfolio_health(
            tickers=_PILOT,
            weights=_PILOT_W,
            asset_types=_PILOT_T,
            metrics=metrics,
            asset_returns=rets,
            corr=rets.corr(),
            risk_contrib_df=core.risk_contribution(rets, _PILOT_W, tickers=_PILOT),
            assumptions=_assumptions(),
            objective="balanced growth",
            risk_free_rate=0.04,
            initial_value=4250.0,
            benchmark_returns=spy,
            policy_benchmark_returns=policy,
            policy_benchmark_meta=meta,
            recommended_type_mix=core.OBJECTIVE_ALLOCATIONS["balanced growth"],
        )
        # avg_drift ≈ 0.0667 → s_obj = 30 - 0.0667*75 = 25
        self.assertAlmostEqual(
            float(health.score_breakdown["Policy / Objective Fit"]), 25.0, places=5
        )
        self.assertAlmostEqual(health.avg_drift, (0.10 + 0.0 + 0.10) / 3, places=5)


if __name__ == "__main__":
    unittest.main()
