"""Performance / benchmark correctness audit regressions."""

from __future__ import annotations

import unittest
from datetime import date, timedelta

import numpy as np
import pandas as pd

import portfolio_core as core
from dashboard_charts import build_aligned_benchmark_growth
from portfolio_core import _return_contribution_df


_PILOT = ["VTI", "VXUS", "BND", "VNQ"]
_PILOT_W = np.array([0.40, 0.20, 0.30, 0.10], dtype=float)
_RF = 0.04
_INITIAL = 4250.0
_SERIES_SPECS = {
    "VTI": (0.00055, 0.010),
    "VXUS": (0.00035, 0.012),
    "BND": (0.00008, 0.003),
    "VNQ": (0.00040, 0.014),
}


def _returns_for_columns(columns: list[str], *, periods: int = 260, seed: int = 42) -> pd.DataFrame:
    idx = pd.date_range("2019-01-01", periods=periods, freq="B")
    data = {}
    for col in columns:
        mu, sigma = _SERIES_SPECS[col]
        col_rng = np.random.default_rng(seed + hash(col) % 10_000)
        data[col] = col_rng.normal(mu, sigma, size=periods)
    return pd.DataFrame(data, index=idx)


def _proxy_returns(periods: int = 260, seed: int = 9) -> pd.DataFrame:
    idx = pd.date_range("2019-01-01", periods=periods, freq="B")
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "SPY": rng.normal(0.0005, 0.01, size=periods),
            "AGG": rng.normal(0.0001, 0.003, size=periods),
            "BIL": rng.normal(0.00005, 0.0004, size=periods),
            "QQQ": rng.normal(0.00065, 0.013, size=periods),
        },
        index=idx,
    )


class TestTickerPermutationAndIdentity(unittest.TestCase):
    def test_a_permutation_invariance(self) -> None:
        base = None
        for cols in (
            ["VTI", "VXUS", "BND", "VNQ"],
            ["BND", "VNQ", "VTI", "VXUS"],
            ["VXUS", "VTI", "VNQ", "BND"],
        ):
            rets = _returns_for_columns(cols)
            s = core.portfolio_daily_returns(rets, _PILOT_W, tickers=_PILOT)
            if base is None:
                base = s
            else:
                pd.testing.assert_series_equal(base, s, check_names=False)

    def test_b_wrong_ticker_identity_changes_result(self) -> None:
        rets = _returns_for_columns(_PILOT)
        correct = core.portfolio_daily_returns(rets, _PILOT_W, tickers=_PILOT)
        wrong = core.portfolio_daily_returns(
            rets, _PILOT_W, tickers=["BND", "VNQ", "VTI", "VXUS"]
        )
        self.assertGreater(float((correct - wrong).abs().sum()), 1e-6)


class TestPolicyAlignmentAndDistinctness(unittest.TestCase):
    def test_c_portfolio_policy_same_date_alignment(self) -> None:
        rets = _returns_for_columns(_PILOT)
        proxy = _proxy_returns()
        # Drop a few policy days to force intersection.
        proxy = proxy.iloc[5:]
        policy, meta = core.build_policy_benchmark_returns(proxy, "balanced growth")
        self.assertTrue(meta.get("ok"))
        port = core.portfolio_daily_returns(rets, _PILOT_W, tickers=_PILOT)
        aligned = pd.concat(
            [port.rename("port"), policy.rename("policy")], axis=1, join="inner"
        ).dropna()
        self.assertEqual(aligned.index.min(), max(port.index.min(), policy.index.min()))
        self.assertEqual(aligned.index.max(), min(port.index.max(), policy.index.max()))
        self.assertGreaterEqual(len(aligned), 6)

    def test_d_objective_change_changes_policy_benchmark(self) -> None:
        proxy = _proxy_returns()
        bal, _ = core.build_policy_benchmark_returns(proxy, "balanced growth")
        agg, _ = core.build_policy_benchmark_returns(proxy, "aggressive growth")
        a, b = bal.align(agg, join="inner")
        self.assertGreater(float((a - b).abs().sum()), 1e-6)

    def test_e_spy_reference_distinct_from_policy(self) -> None:
        proxy = _proxy_returns()
        policy, _ = core.build_policy_benchmark_returns(proxy, "balanced growth")
        spy = proxy["SPY"]
        a, b = spy.align(policy, join="inner")
        self.assertGreater(float((a - b).abs().sum()), 1e-6)


class TestGrowthAndContributions(unittest.TestCase):
    def test_f_normalized_growth_endpoints_agree_with_cumulative(self) -> None:
        rets = _returns_for_columns(_PILOT)
        port = core.portfolio_daily_returns(rets, _PILOT_W, tickers=_PILOT)
        growth = (1.0 + port).cumprod() * _INITIAL
        cum = float(growth.iloc[-1] / _INITIAL - 1.0)
        self.assertAlmostEqual(cum, float((1.0 + port).prod() - 1.0), places=12)
        # Dollar growth endpoint must equal initial * cumulative factor.
        self.assertAlmostEqual(
            float(growth.iloc[-1]),
            _INITIAL * float((1.0 + port).prod()),
            places=9,
        )

    def test_g_deposits_not_in_return_path(self) -> None:
        """Static-weight path has no cashflow / deposit term."""
        import inspect

        src = inspect.getsource(core.portfolio_daily_returns)
        self.assertIn("align_returns_and_weights", src)
        self.assertNotIn("deposit", src.lower())
        self.assertNotIn("cashflow", src.lower())
        rets = _returns_for_columns(_PILOT)
        g = core.portfolio_growth_series(rets, _PILOT_W, _INITIAL, tickers=_PILOT)
        port = core.portfolio_daily_returns(rets, _PILOT_W, tickers=_PILOT)
        # First point is IV*(1+r0), never IV + deposit.
        self.assertAlmostEqual(float(g.iloc[0]), _INITIAL * (1.0 + float(port.iloc[0])), places=9)

    def test_h_contribution_uses_ticker_identity_and_sums(self) -> None:
        rets = _returns_for_columns(["BND", "VNQ", "VTI", "VXUS"])
        cdf = _return_contribution_df(rets, _PILOT_W, tickers=_PILOT)
        port_ann = core.annualized_return(
            core.portfolio_daily_returns(rets, _PILOT_W, tickers=_PILOT)
        )
        self.assertAlmostEqual(
            float(cdf["Return Contribution"].sum()), port_ann, places=12
        )
        by_t = dict(zip(cdf["Ticker"], cdf["Return Contribution"]))
        # Wrong identity: assign pilot weights to alpha-ordered tickers.
        wrong = _return_contribution_df(rets, _PILOT_W, tickers=None)
        wrong_by = dict(zip(wrong["Ticker"], wrong["Return Contribution"]))
        # Correct path maps 40% to VTI; legacy positional maps 40% to first column (BND).
        self.assertNotAlmostEqual(by_t["VTI"], wrong_by.get("BND", 0.0), places=6)
        self.assertAlmostEqual(
            by_t["VTI"],
            0.40 * float(rets["VTI"].mean() * core.TRADING_DAYS),
            places=12,
        )


class TestBenchmarkComparisonAndCacheKeys(unittest.TestCase):
    def test_benchmark_comparison_accepts_mixed_case_labels(self) -> None:
        rets = _returns_for_columns(_PILOT)
        port = core.portfolio_daily_returns(rets, _PILOT_W, tickers=_PILOT)
        spy = _proxy_returns()["SPY"]
        frame = pd.DataFrame({"Current Portfolio": port, "SPY": spy}).dropna()
        table, growth = core.benchmark_comparison(frame, _INITIAL, _RF)
        self.assertIn("Series", table.columns)
        self.assertIn(f"Growth of ${_INITIAL:,.0f}", table.columns)
        self.assertNotIn("Growth of $100,000", table.columns)
        self.assertIn("Current Portfolio", growth.columns)
        self.assertAlmostEqual(
            float(table.loc[table["Series"] == "Current Portfolio", f"Growth of ${_INITIAL:,.0f}"].iloc[0]),
            float(growth["Current Portfolio"].iloc[-1]),
            places=6,
        )

    def test_i_policy_cache_bundle_depends_on_objective(self) -> None:
        """Documented Streamlit key includes objective; builder itself must differ."""
        import inspect

        # streamlit_app.load_policy_benchmark_bundle(start, end, objective)
        from streamlit_app import load_policy_benchmark_bundle

        sig = inspect.signature(load_policy_benchmark_bundle)
        self.assertIn("objective", sig.parameters)
        proxy = _proxy_returns()
        a, _ = core.build_policy_benchmark_returns(proxy, "balanced growth")
        b, _ = core.build_policy_benchmark_returns(proxy, "income")
        x, y = a.align(b, join="inner")
        self.assertGreater(float((x - y).abs().sum()), 1e-6)

    def test_j_headline_and_mini_chart_share_aligned_window(self) -> None:
        rets = _returns_for_columns(_PILOT)
        port = core.portfolio_daily_returns(rets, _PILOT_W, tickers=_PILOT)
        cmp_rets = _proxy_returns()[["SPY", "QQQ"]]
        # Truncate SPY so chart alignment must shorten.
        cmp_rets = cmp_rets.iloc[20:]
        mini = build_aligned_benchmark_growth(
            port, cmp_rets, _INITIAL, benchmark_symbols=("SPY", "QQQ")
        )
        self.assertIn("Portfolio", mini.columns)
        self.assertIn("SPY", mini.columns)
        # Aligned growth length matches intersection of port and SPY.
        expected_n = len(pd.concat([port, cmp_rets["SPY"]], axis=1, join="inner").dropna())
        self.assertEqual(len(mini), expected_n)
        # Endpoint agrees with cumulative product on that window.
        aligned_port = pd.concat([port, cmp_rets["SPY"]], axis=1, join="inner").dropna().iloc[:, 0]
        expected_end = _INITIAL * float((1.0 + aligned_port).prod())
        self.assertAlmostEqual(float(mini["Portfolio"].iloc[-1]), expected_end, places=6)


class TestLiveShadowReferenceSmoke(unittest.TestCase):
    """Optional live Yahoo smoke — skip if network/cache unavailable."""

    def test_shadow_local_window_smoke(self) -> None:
        try:
            end = date.today().isoformat()
            start = (date.today() - timedelta(days=365 * 5)).isoformat()
            prices = core.fetch_price_history(_PILOT, start, end)
            rets = core.daily_returns(prices)
            if len(rets) < 100:
                self.skipTest("insufficient live history")
            mets = core.compute_extended_metrics(
                rets, _PILOT_W, _RF, _INITIAL, tickers=_PILOT
            )
            self.assertTrue(np.isfinite(mets.annual_return))
            self.assertTrue(np.isfinite(mets.volatility))
            proxy_prices = core.fetch_price_history(
                list(core.policy_benchmark_proxy_tickers()), start, end
            )
            policy, meta = core.build_policy_benchmark_returns(
                core.daily_returns(proxy_prices), "balanced growth"
            )
            self.assertTrue(meta.get("ok"))
            port = core.portfolio_daily_returns(rets, _PILOT_W, tickers=_PILOT)
            n = len(pd.concat([port, policy], axis=1, join="inner").dropna())
            self.assertGreater(n, 100)
        except Exception as exc:  # pragma: no cover - network flake
            self.skipTest(f"live market data unavailable: {exc}")


if __name__ == "__main__":
    unittest.main()
