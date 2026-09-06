"""Permutation-invariance: portfolio metrics must follow ticker identity, not column order."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

import portfolio_core as core


_PILOT = ["VTI", "VXUS", "BND", "VNQ"]
_PILOT_W = np.array([0.40, 0.20, 0.30, 0.10], dtype=float)
_PILOT_T = ["Equity", "Equity", "Bonds", "REIT"]
_RF = 0.04
_INITIAL = 4250.0

# Distinct drift/vol so wrong ticker↔weight mapping cannot accidentally match.
_SERIES_SPECS = {
    "VTI": (0.00055, 0.010),
    "VXUS": (0.00035, 0.012),
    "BND": (0.00008, 0.003),
    "VNQ": (0.00040, 0.014),
}


def _assumptions() -> core.ForwardMacroAssumptions:
    return core.ForwardMacroAssumptions(
        rate_environment="Stable Rates",
        inflation="Moderate Inflation",
        valuation="Fair",
        economic_regime="Expansion",
        recession_probability=0.25,
    )


def _returns_for_columns(columns: list[str], *, periods: int = 260, seed: int = 42) -> pd.DataFrame:
    idx = pd.date_range("2019-01-01", periods=periods, freq="B")
    data = {}
    for col in columns:
        mu, sigma = _SERIES_SPECS[col]
        col_rng = np.random.default_rng(seed + hash(col) % 10_000)
        data[col] = col_rng.normal(mu, sigma, size=periods)
    return pd.DataFrame(data, index=idx)


def _metric_tuple(mets: core.ExtendedPortfolioMetrics) -> tuple[float, ...]:
    return (
        mets.annual_return,
        mets.volatility,
        mets.sharpe_ratio,
        mets.sortino_ratio,
        mets.max_drawdown,
    )


def _aligned_corr(rets: pd.DataFrame) -> pd.DataFrame:
    aligned, _, _ = core.align_returns_and_weights(rets, _PILOT_W, tickers=_PILOT)
    return aligned.corr()


class TestExtendedMetricsTickerAlignment(unittest.TestCase):
    def test_permutation_invariance_of_extended_metrics(self) -> None:
        orders = [
            ["VTI", "VXUS", "BND", "VNQ"],
            ["BND", "VNQ", "VTI", "VXUS"],
            ["VNQ", "VTI", "BND", "VXUS"],
        ]
        results = [
            _metric_tuple(
                core.compute_extended_metrics(
                    _returns_for_columns(cols),
                    _PILOT_W,
                    _RF,
                    _INITIAL,
                    tickers=_PILOT,
                )
            )
            for cols in orders
        ]
        for other in results[1:]:
            np.testing.assert_allclose(results[0], other, rtol=1e-12, atol=1e-12)

    def test_wrong_ticker_identity_with_same_positional_weights_changes_result(self) -> None:
        """Ticker-aware alignment must not be masked by positional coincidence."""
        cols = ["BND", "VNQ", "VTI", "VXUS"]
        rets = _returns_for_columns(cols)
        correct = core.compute_extended_metrics(
            rets, _PILOT_W, _RF, _INITIAL, tickers=_PILOT
        )
        # Same weight array, but labels claim those weights belong to alphabetical columns.
        wrong = core.compute_extended_metrics(
            rets, _PILOT_W, _RF, _INITIAL, tickers=cols
        )
        self.assertFalse(
            np.allclose(_metric_tuple(correct), _metric_tuple(wrong), rtol=1e-6, atol=1e-6),
            msg="Changing ticker identity with identical positional weights must change metrics",
        )
        holdings_order = rets.loc[:, _PILOT]
        baseline = core.compute_extended_metrics(
            holdings_order, _PILOT_W, _RF, _INITIAL, tickers=_PILOT
        )
        np.testing.assert_allclose(
            _metric_tuple(correct), _metric_tuple(baseline), rtol=1e-12, atol=1e-12
        )

    def test_health_vol_sharpe_dd_permutation_invariant(self) -> None:
        orders = [
            ["VTI", "VXUS", "BND", "VNQ"],
            ["BND", "VNQ", "VTI", "VXUS"],
            ["VXUS", "BND", "VNQ", "VTI"],
        ]
        scores = []
        for cols in orders:
            rets = _returns_for_columns(cols)
            # Misaligned metrics on purpose — Health must use aligned port_rets.
            metrics = core.compute_extended_metrics(
                rets, _PILOT_W, _RF, _INITIAL, tickers=None
            )
            health = core.evaluate_portfolio_health(
                tickers=_PILOT,
                weights=_PILOT_W,
                asset_types=_PILOT_T,
                metrics=metrics,
                asset_returns=rets,
                corr=_aligned_corr(rets),
                risk_contrib_df=core.risk_contribution(rets, _PILOT_W, tickers=_PILOT),
                assumptions=_assumptions(),
                objective="balanced growth",
                risk_free_rate=_RF,
                initial_value=_INITIAL,
            )
            scores.append(
                (
                    health.score_breakdown["Risk Appropriateness"],
                    health.score_breakdown["Policy-Relative Performance"],
                    health.score_breakdown["Portfolio Construction"],
                    health.score,
                )
            )
        for other in scores[1:]:
            np.testing.assert_allclose(scores[0], other, rtol=1e-12, atol=1e-12)

    def test_return_vs_policy_unchanged_under_column_permutation(self) -> None:
        idx = pd.date_range("2019-01-01", periods=260, freq="B")
        rng = np.random.default_rng(7)
        spy = pd.Series(rng.normal(0.0005, 0.01, size=len(idx)), index=idx)
        agg = pd.Series(rng.normal(0.0001, 0.003, size=len(idx)), index=idx)
        bil = pd.Series(rng.normal(0.00005, 0.0004, size=len(idx)), index=idx)
        policy, meta = core.build_policy_benchmark_returns(
            pd.DataFrame({"SPY": spy, "AGG": agg, "BIL": bil}), "balanced growth"
        )
        s_vals = []
        for cols in (["VTI", "VXUS", "BND", "VNQ"], ["BND", "VNQ", "VTI", "VXUS"]):
            rets = _returns_for_columns(cols)
            metrics = core.compute_extended_metrics(
                rets, _PILOT_W, _RF, _INITIAL, tickers=_PILOT
            )
            health = core.evaluate_portfolio_health(
                tickers=_PILOT,
                weights=_PILOT_W,
                asset_types=_PILOT_T,
                metrics=metrics,
                asset_returns=rets,
                corr=_aligned_corr(rets),
                risk_contrib_df=core.risk_contribution(rets, _PILOT_W, tickers=_PILOT),
                assumptions=_assumptions(),
                objective="balanced growth",
                risk_free_rate=_RF,
                initial_value=_INITIAL,
                policy_benchmark_returns=policy,
                policy_benchmark_meta=meta,
            )
            s_vals.append(health.score_breakdown["Policy-Relative Performance"])
        self.assertEqual(s_vals[0], s_vals[1])


if __name__ == "__main__":
    unittest.main()
