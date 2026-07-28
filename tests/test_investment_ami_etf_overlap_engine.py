"""P2 — EtfOverlapEngine."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from investment_ami.engines.base import InstantEngineRequest
from investment_ami.engines.etf_overlap import EtfOverlapEngine, assess_etf_overlap
from investment_ami.engines.support.overlap_data import resolve_etf_overlap_pairs
from investment_ami.pipeline.instant import run_instant_engine
from investment_ami_phase2_solvers import etf_overlap_answer


class TestEtfOverlapData(unittest.TestCase):
    def test_resolve_pairs_from_context(self) -> None:
        ctx = {"etf_overlap_pairs": [{"pair": "VOO/QQQ", "overlap_pct": 72.5}]}
        pairs = resolve_etf_overlap_pairs(ctx, question="Should I own both VOO and QQQ?")
        self.assertGreaterEqual(len(pairs), 1)
        self.assertEqual(pairs[0].get("pair"), "VOO/QQQ")

    @patch("investment_ami.engines.support.overlap_data.compute_pairwise_overlap_pct", return_value=68.2)
    def test_resolve_live_pair_when_pair_not_in_context_list(self, _mock: MagicMock) -> None:
        pairs = resolve_etf_overlap_pairs(
            {"etf_overlap_pairs": [{"pair": "VTI/SPY", "overlap_pct": 40.0}]},
            question="Should I own both VOO and QQQ?",
        )
        self.assertEqual(pairs[0]["pair"], "VOO/QQQ")
        self.assertAlmostEqual(float(pairs[0]["overlap_pct"]), 68.2)


class TestEtfOverlapEngine(unittest.TestCase):
    def test_assessment_from_pairs(self) -> None:
        a = assess_etf_overlap(
            {"etf_overlap_pairs": [{"pair": "VOO/QQQ", "overlap_pct": 72.0}]},
            question="Should I own both VOO and QQQ?",
        )
        self.assertFalse(a.empty)
        self.assertAlmostEqual(a.overlap_pct, 72.0)
        self.assertTrue(a.compare_mode)

    def test_engine_computed_fields(self) -> None:
        result = EtfOverlapEngine().solve(
            InstantEngineRequest(
                context={"etf_overlap_pairs": [{"pair": "VOO/QQQ", "overlap_pct": 72.5}]},
                beginner=False,
                question="Should I own both VOO and QQQ?",
            )
        )
        self.assertEqual(result.problem_type, "etf_overlap")
        self.assertEqual(result.computed.get("ami_engine_id"), "etf_overlap")
        self.assertEqual(result.computed.get("max_overlap_pair"), "VOO/QQQ")
        self.assertEqual(result.computed.get("max_overlap_pct"), 72.5)
        self.assertEqual(result.confidence_pct, 82)

    def test_pipeline_matches_wrapper(self) -> None:
        ctx = {
            "etf_overlap_pairs": [{"pair": "VOO/QQQ", "overlap_pct": 72.0}],
            "current_weights": {"VOO": "50%", "QQQ": "50%"},
        }
        via_engine = run_instant_engine(
            "etf_overlap",
            ctx,
            beginner=False,
            question="Should I own both VOO and QQQ?",
        )
        via_wrapper = etf_overlap_answer(ctx, beginner=False, question="Should I own both VOO and QQQ?")
        self.assertEqual(via_engine.short_answer, via_wrapper.short_answer)
        self.assertEqual(via_engine.computed.get("max_overlap_pct"), via_wrapper.computed.get("max_overlap_pct"))

    def test_empty_pairs_low_holdings(self) -> None:
        result = run_instant_engine("etf_overlap", {}, beginner=True)
        self.assertIn("two", result.short_answer.lower())
        self.assertEqual(result.confidence_pct, 55)


if __name__ == "__main__":
    unittest.main()
