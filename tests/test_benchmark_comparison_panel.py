"""Benchmark & Alternative Comparison panel regressions."""

from __future__ import annotations

import inspect
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

import portfolio_core as core
from components.benchmark_comparison_panel import (
    build_market_alternative_comparison_returns,
    ending_value_column_name,
    render_benchmark_alternative_comparison,
    run_market_alternative_comparison,
)


def _port_and_cmp(periods: int = 80, seed: int = 3):
    idx = pd.date_range("2020-01-01", periods=periods, freq="B")
    rng = np.random.default_rng(seed)
    port = pd.Series(rng.normal(0.0004, 0.01, size=periods), index=idx, name="port")
    cmp_rets = pd.DataFrame(
        {
            "SPY": rng.normal(0.0005, 0.01, size=periods),
            "QQQ": rng.normal(0.0006, 0.012, size=periods),
            "AGG": rng.normal(0.0001, 0.003, size=periods),
            "BIL": rng.normal(0.00005, 0.0004, size=periods),
        },
        index=idx,
    )
    return port, cmp_rets


class TestMarketAlternativeComparisonCore(unittest.TestCase):
    def test_no_keyerror_on_current_portfolio_label(self) -> None:
        port, cmp_rets = _port_and_cmp()
        table, growth = run_market_alternative_comparison(
            port, cmp_rets, initial_value=4250.0, risk_free_rate=0.04
        )
        self.assertIn("Series", table.columns)
        self.assertIn("Current Portfolio", set(table["Series"]))
        self.assertIn("Current Portfolio", growth.columns)
        self.assertIn(ending_value_column_name(4250.0), table.columns)
        self.assertNotIn("Growth of $100,000", table.columns)

    def test_dynamic_initial_value_title(self) -> None:
        self.assertEqual(ending_value_column_name(4250.0), "Growth of $4,250")
        self.assertEqual(ending_value_column_name(100_000.0), "Growth of $100,000")

    def test_labels_are_market_reference_not_policy(self) -> None:
        port, cmp_rets = _port_and_cmp()
        frame = build_market_alternative_comparison_returns(port, cmp_rets)
        cols = list(frame.columns)
        self.assertEqual(cols[0], "Current Portfolio")
        self.assertTrue(any("SPY" in c and "market reference" in c for c in cols))
        self.assertTrue(any("QQQ" in c and "market reference" in c for c in cols))
        self.assertFalse(any("policy" in c.lower() for c in cols))
        # Distinct from a bare ambiguous "Benchmark" label.
        self.assertFalse(any(c.strip().lower() == "benchmark" for c in cols))

    def test_ending_value_matches_growth_endpoint(self) -> None:
        port, cmp_rets = _port_and_cmp()
        table, growth = run_market_alternative_comparison(
            port, cmp_rets, initial_value=4250.0, risk_free_rate=0.04
        )
        col = ending_value_column_name(4250.0)
        row = table.loc[table["Series"] == "Current Portfolio"].iloc[0]
        self.assertAlmostEqual(float(row[col]), float(growth["Current Portfolio"].iloc[-1]), places=6)


class TestAnalyticsPathWiring(unittest.TestCase):
    def test_analytics_path_imports_shared_renderer(self) -> None:
        import streamlit_app as app

        src = inspect.getsource(app)
        self.assertIn("render_benchmark_alternative_comparison", src)
        self.assertIn("analytics_benchmark_alt", src)
        self.assertIn("Benchmark & Alternative Comparison", src)
        # Must appear in analytics section context (key prefix unique to analytics).
        self.assertIn('key_prefix="analytics_benchmark_alt"', src)

    def test_render_callable_without_crash_when_not_run(self) -> None:
        port, cmp_rets = _port_and_cmp()
        tickers = ["VTI", "BND"]
        weights = np.array([0.6, 0.4])
        rets = pd.DataFrame(
            {"VTI": port.values, "BND": port.values * 0.2},
            index=port.index,
        )
        settings = {
            "initial_value": 4250.0,
            "start": "2020-01-01",
            "end": "2020-12-31",
            "risk_free": 0.04,
        }
        fake_st = MagicMock()
        fake_st.session_state = {}
        fake_st.button.return_value = False

        with patch("components.benchmark_comparison_panel.st", fake_st):
            render_benchmark_alternative_comparison(
                returns=rets,
                weights=weights,
                tickers=tickers,
                settings=settings,
                load_comparison_prices=lambda *_a, **_k: pd.DataFrame(),
                compute_daily_returns=lambda p: cmp_rets,
                key_prefix="test_bench",
                section_title="Benchmark & Alternative Comparison",
            )
        fake_st.button.assert_called()
        # Click path not activated → no dataframe render required.
        self.assertFalse(fake_st.session_state.get("test_bench_run", False))


if __name__ == "__main__":
    unittest.main()
