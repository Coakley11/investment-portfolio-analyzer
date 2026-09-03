"""Regression: Risk Contribution ticker/weight alignment + Sharpe points vs ratio."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

import portfolio_core as core
from components.decision_coach import _iter_recommendation_entries


_PILOT_TICKERS = ["VTI", "VXUS", "BND", "VNQ"]
_PILOT_WEIGHTS = np.array([0.40, 0.20, 0.30, 0.10])
_PILOT_TYPES = ["Equity", "Equity", "Bonds", "REIT"]


def _synthetic_returns(columns: list[str], *, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=80, freq="B")
    data = rng.normal(0.0004, 0.01, size=(len(idx), len(columns)))
    # Make BND lower vol so risk shares differ from weights.
    for i, col in enumerate(columns):
        if col == "BND":
            data[:, i] *= 0.35
        elif col == "VNQ":
            data[:, i] *= 1.15
    return pd.DataFrame(data, index=idx, columns=columns)


class TestComputeRiskPackStreamlitPath(unittest.TestCase):
    def test_build_risk_pack_preserves_pilot_weights_with_reordered_columns(self) -> None:
        """Same contract as streamlit_app.compute_risk_pack → core.build_risk_pack."""
        rets = _synthetic_returns(sorted(_PILOT_TICKERS))
        pack = core.build_risk_pack(
            rets,
            tuple(_PILOT_WEIGHTS.tolist()),
            initial_value=10_000.0,
            tickers=_PILOT_TICKERS,
        )
        rc = pack["risk_contrib"]
        assert isinstance(rc, pd.DataFrame)
        weight_map = {str(r["Ticker"]): float(r["Weight"]) for _, r in rc.iterrows()}
        self.assertAlmostEqual(weight_map["VTI"], 0.40, places=6)
        self.assertAlmostEqual(weight_map["VXUS"], 0.20, places=6)
        self.assertAlmostEqual(weight_map["BND"], 0.30, places=6)
        self.assertAlmostEqual(weight_map["VNQ"], 0.10, places=6)
        self.assertIn("port_rets", pack)
        self.assertEqual(len(pack["port_rets"]), len(rets))

    def test_streamlit_compute_risk_pack_signature_matches_app(self) -> None:
        """Import the cached Streamlit wrapper and call it like streamlit_app does."""
        from streamlit_app import compute_risk_pack

        rets = _synthetic_returns(sorted(_PILOT_TICKERS))
        pack = compute_risk_pack(
            rets,
            tuple(_PILOT_WEIGHTS.tolist()),
            10_000.0,
            tickers_tuple=tuple(_PILOT_TICKERS),
        )
        weight_map = {
            str(r["Ticker"]): float(r["Weight"])
            for _, r in pack["risk_contrib"].iterrows()
        }
        self.assertAlmostEqual(weight_map["VTI"], 0.40, places=6)
        self.assertAlmostEqual(weight_map["VXUS"], 0.20, places=6)
        self.assertAlmostEqual(weight_map["BND"], 0.30, places=6)
        self.assertAlmostEqual(weight_map["VNQ"], 0.10, places=6)


    def test_return_and_drawdown_contribution_siblings_align(self) -> None:
        rets = _synthetic_returns(sorted(_PILOT_TICKERS))
        ret_df = core._return_contribution_df(rets, _PILOT_WEIGHTS, tickers=_PILOT_TICKERS)
        dd_df = core._drawdown_contribution_df(rets, _PILOT_WEIGHTS, tickers=_PILOT_TICKERS)
        for df in (ret_df, dd_df):
            m = {str(r["Ticker"]): float(r["Weight"]) for _, r in df.iterrows()}
            self.assertAlmostEqual(m["VTI"], 0.40, places=6)
            self.assertAlmostEqual(m["VXUS"], 0.20, places=6)
            self.assertAlmostEqual(m["BND"], 0.30, places=6)
            self.assertAlmostEqual(m["VNQ"], 0.10, places=6)

    def test_align_helper_reindexes_to_ticker_order(self) -> None:
        rets = _synthetic_returns(["VNQ", "BND", "VXUS", "VTI"])
        aligned, w, labels = core.align_returns_and_weights(
            rets, _PILOT_WEIGHTS, tickers=_PILOT_TICKERS
        )
        self.assertEqual(labels, _PILOT_TICKERS)
        self.assertEqual(list(aligned.columns), _PILOT_TICKERS)
        np.testing.assert_allclose(w, _PILOT_WEIGHTS)


class TestSharpePointsVsRatio(unittest.TestCase):
    def _metrics(self, sharpe: float) -> core.ExtendedPortfolioMetrics:
        return core.ExtendedPortfolioMetrics(
            annual_return=0.05,
            volatility=0.15,
            sharpe_ratio=sharpe,
            max_drawdown=-0.12,
            sortino_ratio=0.2,
            cagr=0.05,
            beta_spy=1.0,
            projected_value=105_000.0,
        )

    def test_breakdown_uses_sharpe_score_pts_not_ratio_label(self) -> None:
        rets = _synthetic_returns(_PILOT_TICKERS, seed=1)
        # Force known sharpe via metrics object (thresholds unchanged).
        metrics = self._metrics(0.14283771316050375)
        assumptions = core.ForwardMacroAssumptions(
            rate_environment="Stable Rates",
            inflation="Moderate Inflation",
            valuation="Fair",
            economic_regime="Expansion",
            recession_probability=0.20,
        )
        rc = core.risk_contribution(rets, _PILOT_WEIGHTS, tickers=_PILOT_TICKERS)
        corr = rets.corr()
        health = core.evaluate_portfolio_health(
            list(_PILOT_TICKERS),
            _PILOT_WEIGHTS,
            _PILOT_TYPES,
            metrics,
            rets,
            corr,
            rc,
            assumptions,
            objective="balanced growth",
            risk_free_rate=0.04,
            initial_value=100_000.0,
        )
        self.assertIn("Sharpe Score (pts)", health.score_breakdown)
        self.assertNotIn("Sharpe Ratio", health.score_breakdown)
        pts = float(health.score_breakdown["Sharpe Score (pts)"])
        self.assertAlmostEqual(pts, 1.4283771316050375, places=5)
        self.assertNotAlmostEqual(pts, metrics.sharpe_ratio, places=2)

        sharpe_recs = [
            d
            for d in health.recommendation_details
            if "Sharpe" in d.issue or "sharpe" in d.triggered_by.lower()
        ]
        self.assertTrue(sharpe_recs)
        self.assertIn("0.14", sharpe_recs[0].triggered_by)
        self.assertIn("below 0.4", sharpe_recs[0].triggered_by.lower())
        self.assertEqual(sharpe_recs[0].evidence.get("Sharpe ratio"), "0.14")


class TestRecommendationsRenderFallback(unittest.TestCase):
    def test_blank_detail_text_falls_back_to_recommendations_list(self) -> None:
        blank = core.RecommendationDetail(
            text="   ",
            issue="Issue",
            why_it_matters="Why",
            triggered_by="Trigger",
            possible_benefit="Benefit",
            evidence={},
        )
        health = core.PortfolioHealthResult(
            score=50.0,
            score_label="Fair",
            score_color="#f59e0b",
            status_message="ok",
            whats_working=["a"],
            whats_not_working=["b"],
            recommendations=["Fallback recommendation text"],
            recommendation_details=[blank],
            action_plan=core.PortfolioActionPlan(
                headline="h", today=[], this_month=[], this_year=[]
            ),
            macro_fit=[],
            rebalance_df=pd.DataFrame(),
            return_contrib_df=pd.DataFrame(),
            risk_contrib_df=pd.DataFrame(),
            drawdown_contrib_df=pd.DataFrame(),
            allocation_compare_df=pd.DataFrame(),
            macro_heatmap_df=pd.DataFrame(),
            score_breakdown={},
            avg_drift=0.0,
            objective="balanced growth",
        )
        entries = _iter_recommendation_entries(health)
        self.assertEqual(len(entries), 1)
        detail, fallback = entries[0]
        self.assertEqual(fallback, "Fallback recommendation text")
        self.assertFalse(str(detail.text or "").strip())


if __name__ == "__main__":
    unittest.main()
