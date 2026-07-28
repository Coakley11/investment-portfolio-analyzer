"""P2 — AssetAllocationEngine."""

from __future__ import annotations

import unittest

from investment_ami.engines.asset_allocation import AssetAllocationEngine, run_allocation_recommendation
from investment_ami.engines.base import InstantEngineRequest
from investment_ami.engines.portfolio_concentration import assess_concentration_from_rows
from investment_ami.pipeline.instant import run_instant_engine
from investment_ami_allocation import allocation_recommendation_answer


class TestAssetAllocationEngine(unittest.TestCase):
    _CTX = {
        "experience_mode": "Advanced Mode",
        "current_weights": {"VOO": "40%", "QQQ": "35%", "BND": "25%"},
        "holdings": ["VOO", "QQQ", "BND"],
        "risk_level": "Moderate",
    }

    def test_concentration_from_allocation_rows(self) -> None:
        rows = [("VOO", 40.0), ("QQQ", 35.0), ("BND", 25.0)]
        c = assess_concentration_from_rows(rows)
        self.assertEqual(c.top_ticker, "VOO")
        self.assertAlmostEqual(c.top3_pct, 100.0)

    def test_engine_metadata(self) -> None:
        result = AssetAllocationEngine().solve(
            InstantEngineRequest(context=self._CTX, beginner=False, question="Should I rebalance?")
        )
        self.assertEqual(result.problem_type, "allocation_recommendation")
        self.assertEqual(result.computed.get("ami_engine_id"), "allocation_recommendation")
        self.assertIn("risk_tolerance", result.computed)
        self.assertIn("recommendations", result.computed)

    def test_pipeline_matches_wrapper(self) -> None:
        ctx = dict(self._CTX)
        via_engine = run_instant_engine(
            "allocation_recommendation",
            ctx,
            beginner=False,
            question="Should I rebalance?",
        )
        via_wrapper = allocation_recommendation_answer(ctx, beginner=False, question="Should I rebalance?")
        self.assertEqual(via_engine.short_answer, via_wrapper.short_answer)
        self.assertEqual(
            via_engine.computed.get("top3_pct"),
            via_wrapper.computed.get("top3_pct"),
        )

    def test_asset_allocation_catalog_alias(self) -> None:
        ctx = dict(self._CTX)
        primary = run_instant_engine("allocation_recommendation", ctx, beginner=True, question="How should I allocate?")
        alias = run_instant_engine(
            "asset_allocation",
            dict(self._CTX),
            beginner=True,
            question="How should I allocate?",
        )
        self.assertEqual(primary.short_answer, alias.short_answer)

    def test_empty_weights_confidence(self) -> None:
        result = run_allocation_recommendation({}, beginner=True)
        self.assertEqual(result.confidence_pct, 55)
        self.assertEqual(result.computed.get("ami_engine_id"), "allocation_recommendation")


if __name__ == "__main__":
    unittest.main()
