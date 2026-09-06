"""Regression: Health Guided targets, benchmark mini-chart alignment, presentation."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

import portfolio_core as core
from components.guided_adjustment import format_guided_step4_example
from dashboard_charts import (
    allocation_percentage_columns,
    build_aligned_benchmark_growth,
)


_PILOT_TICKERS = ["VTI", "VXUS", "BND", "VNQ"]
_PILOT_TYPES = ["Equity", "Equity", "Bonds", "REIT"]
_PILOT_WEIGHTS = np.array([0.40, 0.20, 0.30, 0.10])


class TestCategoryPreservingGuidedTargets(unittest.TestCase):
    def test_balanced_growth_splits_and_keeps_tbill_orphan(self) -> None:
        targets = core.OBJECTIVE_ALLOCATIONS["balanced growth"]
        w, orphans = core.build_category_preserving_ticker_targets(
            _PILOT_TICKERS, _PILOT_TYPES, targets
        )
        # Equity 60% across VTI/VXUS/VNQ; Bonds 30% on BND; T-Bills orphan 10%.
        self.assertAlmostEqual(float(w[0]), 0.20, places=6)  # VTI
        self.assertAlmostEqual(float(w[1]), 0.20, places=6)  # VXUS
        self.assertAlmostEqual(float(w[2]), 0.30, places=6)  # BND
        self.assertAlmostEqual(float(w[3]), 0.20, places=6)  # VNQ
        self.assertAlmostEqual(float(w.sum()), 0.90, places=6)
        self.assertEqual(len(orphans), 1)
        self.assertEqual(orphans[0]["category"], "tbills")
        self.assertAlmostEqual(float(orphans[0]["weight"]), 0.10, places=6)
        self.assertIn("T-Bills", orphans[0]["Ticker"])

        total = float(w.sum()) + sum(float(o["weight"]) for o in orphans)
        self.assertAlmostEqual(total, 1.0, places=6)

        cat = core.aggregate_guided_category_exposure(
            _PILOT_TICKERS, _PILOT_TYPES, w, orphans
        )
        self.assertAlmostEqual(cat["equity"], 0.60, places=6)
        self.assertAlmostEqual(cat["bonds"], 0.30, places=6)
        self.assertAlmostEqual(cat["tbills"], 0.10, places=6)

    def test_evaluate_health_rebalance_preserves_categories(self) -> None:
        idx = pd.date_range("2020-01-01", periods=60, freq="B")
        rng = np.random.default_rng(1)
        rets = pd.DataFrame(
            rng.normal(0.0003, 0.01, size=(len(idx), 4)),
            index=idx,
            columns=_PILOT_TICKERS,
        )
        metrics = core.compute_extended_metrics(rets, _PILOT_WEIGHTS, 0.04, 4250.0)
        corr = rets.corr()
        risk = core.risk_contribution(rets, _PILOT_WEIGHTS, tickers=_PILOT_TICKERS)
        assumptions = core.ForwardMacroAssumptions(
            rate_environment="Stable Rates",
            inflation="Moderate Inflation",
            valuation="Fair",
            economic_regime="Expansion",
            recession_probability=0.20,
        )
        health = core.evaluate_portfolio_health(
            tickers=_PILOT_TICKERS,
            weights=_PILOT_WEIGHTS,
            asset_types=_PILOT_TYPES,
            metrics=metrics,
            asset_returns=rets,
            corr=corr,
            risk_contrib_df=risk,
            assumptions=assumptions,
            objective="balanced growth",
            risk_free_rate=0.04,
            initial_value=4250.0,
            benchmark_returns=rets["VTI"],
            optimizer_weights=None,
            recommended_type_mix=core.OBJECTIVE_ALLOCATIONS["balanced growth"],
        )
        reb = health.rebalance_df
        by_ticker = {
            str(r["Ticker"]): float(r["Objective (%)"])
            for _, r in reb.iterrows()
        }
        self.assertAlmostEqual(by_ticker["VTI"], 20.0, places=1)
        self.assertAlmostEqual(by_ticker["VXUS"], 20.0, places=1)
        self.assertAlmostEqual(by_ticker["BND"], 30.0, places=1)
        self.assertAlmostEqual(by_ticker["VNQ"], 20.0, places=1)
        orphan_rows = reb[reb["Orphan Sleeve"] == True]  # noqa: E712
        self.assertEqual(len(orphan_rows), 1)
        self.assertAlmostEqual(float(orphan_rows.iloc[0]["Objective (%)"]), 10.0, places=1)
        obj_sum = float(reb["Objective (%)"].sum())
        self.assertAlmostEqual(obj_sum, 100.0, places=1)
        # Must not be the old 33.3/33.3/16.7/16.7 renormalized mix.
        self.assertNotAlmostEqual(by_ticker["VTI"], 33.3, places=1)

    def test_suggested_weights_skip_orphan_and_do_not_invent_holding(self) -> None:
        reb = pd.DataFrame(
            [
                {"Ticker": "VTI", "Objective (%)": 20.0, "Orphan Sleeve": False},
                {"Ticker": "VXUS", "Objective (%)": 20.0, "Orphan Sleeve": False},
                {"Ticker": "BND", "Objective (%)": 30.0, "Orphan Sleeve": False},
                {"Ticker": "VNQ", "Objective (%)": 20.0, "Orphan Sleeve": False},
                {
                    "Ticker": "Cash / T-Bills (unrepresented)",
                    "Objective (%)": 10.0,
                    "Orphan Sleeve": True,
                },
            ]
        )
        w = core.suggested_weights_from_rebalance(
            reb, _PILOT_TICKERS, _PILOT_WEIGHTS, target_column="Objective (%)"
        )
        self.assertEqual(len(w), 4)
        self.assertAlmostEqual(float(w.sum()), 1.0, places=6)
        # Absolute 20/20/30/20 renormalized among holdings → 22.2/22.2/33.3/22.2
        self.assertAlmostEqual(float(w[0]), 20 / 90, places=5)


class TestBenchmarkMiniAlignment(unittest.TestCase):
    def test_aligned_growth_has_finite_portfolio_spy_qqq(self) -> None:
        idx = pd.date_range("2021-01-04", periods=40, freq="B")
        rng = np.random.default_rng(2)
        port = pd.Series(rng.normal(0.0004, 0.01, size=len(idx)), index=idx, name="port")
        # Benchmarks on a slightly shifted / overlapping calendar
        bench_idx = idx[5:]
        cmp_rets = pd.DataFrame(
            {
                "SPY": rng.normal(0.0005, 0.011, size=len(bench_idx)),
                "QQQ": rng.normal(0.0006, 0.014, size=len(bench_idx)),
            },
            index=bench_idx,
        )
        mini = build_aligned_benchmark_growth(port, cmp_rets, 4250.0)
        for col in ("Portfolio", "SPY", "QQQ"):
            self.assertIn(col, mini.columns)
            vals = pd.to_numeric(mini[col], errors="coerce")
            self.assertTrue(np.isfinite(vals).any(), msg=f"{col} has no finite values")
            self.assertFalse(vals.isna().all(), msg=f"{col} is all-NaN")

    def test_old_rangeindex_assignment_pattern_is_broken_but_helper_works(self) -> None:
        """Document the bug we fixed: RangeIndex frame + DatetimeIndex series → NaNs."""
        idx = pd.date_range("2021-01-04", periods=10, freq="B")
        port = pd.Series(np.linspace(0.001, 0.002, len(idx)), index=idx)
        broken = pd.DataFrame({"Date": port.index})
        broken["Portfolio"] = 4250.0 * (1 + port).cumprod()
        self.assertTrue(broken["Portfolio"].isna().all())
        fixed = build_aligned_benchmark_growth(port, pd.DataFrame(), 4250.0)
        self.assertFalse(pd.to_numeric(fixed["Portfolio"], errors="coerce").isna().all())


class TestAllocationChartPercentOnly(unittest.TestCase):
    def test_percentage_columns_exclude_dollars(self) -> None:
        df = pd.DataFrame(
            {
                "Category": ["Equity", "Bonds", "T-Bills"],
                "Current (%)": [70.0, 30.0, 0.0],
                "Current ($)": [2975.0, 1275.0, 0.0],
                "Objective (%)": [60.0, 30.0, 10.0],
                "Objective ($)": [2550.0, 1275.0, 425.0],
                "Optimizer (%)": [0.0, 100.0, 0.0],
            }
        )
        cols = allocation_percentage_columns(df)
        self.assertEqual(
            cols,
            ["Current (%)", "Objective (%)", "Optimizer (%)"],
        )
        self.assertTrue(all("($)" not in c for c in cols))


class TestOptimizerDustAndGuidedProse(unittest.TestCase):
    def test_threshold_weight_dust(self) -> None:
        w = np.array([1.0 - 1e-12, 1e-12, 0.0])
        cleaned = core.threshold_weight_dust(w)
        self.assertAlmostEqual(float(cleaned[0]), 1.0, places=9)
        self.assertAlmostEqual(float(cleaned[1]), 0.0, places=12)
        self.assertEqual(core.format_weight_pct(1e-12), "0.00%")
        self.assertEqual(core.format_weight_pct(0.5), "50.00%")

    def test_guided_step4_prose_format(self) -> None:
        text = format_guided_step4_example("VTI", 40.0, 1700.0, 20.0, 850.0, -850.0)
        self.assertIn("Adjust **VTI** from 40.0% ($1,700)", text)
        self.assertIn("toward 20.0% ($850)", text)
        self.assertIn("a change of approximately $850", text)
        self.assertNotIn("40.0% (1,700)", text)


if __name__ == "__main__":
    unittest.main()
