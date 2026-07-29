"""Phase 3.1 / 3.2 — PortfolioAnalysisBrief quality, invariants, and archetype fixtures."""

from __future__ import annotations

import unittest

from investment_ami.engines.support.portfolio_analysis_brief import (
    BRIEF_SCHEMA_VERSION,
    BRIEF_VERSION,
    build_portfolio_analysis_brief,
    validate_brief_invariants,
)

_DIVERSIFIED = {
    "current_weights": {"VTI": 40.0, "BND": 30.0, "VXUS": 20.0, "VNQ": 10.0},
    "asset_class_breakdown": {"Equity": 60.0, "Bond": 30.0, "REIT": 10.0},
    "health_score": 80,
    "volatility": "11%",
    "expected_return": "7%",
    "sharpe_ratio": "0.6",
    "analysis_start_date": "2020-01-01",
    "analysis_end_date": "2025-12-31",
    "risk_free_pct": 3.5,
    "health_rate_env": "Stable Rates",
    "health_inflation": "Moderate Inflation",
    "health_regime": "Expansion",
    "etf_overlap_pairs": [{"pair": "VTI/VXUS", "overlap_pct": 12.0}],
}

_DIVERSIFIED_NO_OVERLAP = {k: v for k, v in _DIVERSIFIED.items() if k != "etf_overlap_pairs"}

_ETF_HEAVY = {
    "current_weights": {"VOO": 35.0, "QQQ": 35.0, "BND": 30.0},
    "asset_class_breakdown": {"Equity": 70.0, "Bond": 30.0},
    "etf_overlap_pairs": [{"pair": "VOO/QQQ", "overlap_pct": 42.0}],
}

_CONCENTRATED = {"current_weights": {"AAPL": 85.0, "MSFT": 15.0}}

_SINGLE = {"current_weights": {"NVDA": 100.0}}

_EMPTY: dict = {}

_SPARSE = {"current_weights": {"SCHD": 50.0, "BND": 50.0}}


class TestPortfolioAnalysisBriefPhase3(unittest.TestCase):
    def test_schema_version_and_invariants(self) -> None:
        brief = build_portfolio_analysis_brief(_DIVERSIFIED)
        self.assertEqual(brief.brief_version, BRIEF_VERSION)
        self.assertEqual(brief.brief_schema_version, BRIEF_SCHEMA_VERSION)
        self.assertEqual(validate_brief_invariants(brief), [])

    def test_phase32_high_value_facts_present(self) -> None:
        brief = build_portfolio_analysis_brief(_DIVERSIFIED)
        for fid in (
            "measurement.context",
            "allocation.sleeve_summary",
            "concentration.summary",
            "overlap.summary",
            "scenario.summary",
            "sector.allocation_summary",
            "portfolio.archetype",
            "data_quality.completeness",
        ):
            self.assertIn(fid, brief.facts, msg=fid)
            self.assertIn(fid, brief.fact_index)
            self.assertIn("inference_class", brief.fact_index[fid].to_dict())

    def test_archetype_fixtures(self) -> None:
        cases = (
            (_EMPTY, "empty"),
            (_SINGLE, "single_stock"),
            (_CONCENTRATED, "concentrated"),
            (_ETF_HEAVY, "etf_heavy"),
            (_DIVERSIFIED_NO_OVERLAP, "diversified"),
            (_SPARSE, "balanced_two_fund"),
        )
        for ctx, expected in cases:
            with self.subTest(expected=expected):
                brief = build_portfolio_analysis_brief(ctx)
                self.assertEqual(brief.facts.get("portfolio.archetype"), expected)
                self.assertEqual(validate_brief_invariants(brief), [])

    def test_empty_portfolio_limitations_and_schema(self) -> None:
        brief = build_portfolio_analysis_brief(_EMPTY)
        self.assertTrue(brief.limitations)
        self.assertEqual(brief.facts.get("portfolio.archetype"), "empty")
        dq = brief.facts.get("data_quality.completeness") or {}
        self.assertEqual(dq.get("tier"), "empty")
        self.assertEqual(validate_brief_invariants(brief), [])

    def test_truncation_limitation(self) -> None:
        weights = {f"E{i}": 100.0 / 15 for i in range(15)}
        brief = build_portfolio_analysis_brief({"current_weights": weights})
        self.assertTrue(any("truncated" in x.lower() for x in brief.limitations))
        self.assertEqual(len(brief.facts["holdings.weights"]), 12)

    def test_no_duplicate_top3_fact_ids(self) -> None:
        brief = build_portfolio_analysis_brief(_DIVERSIFIED)
        self.assertIn("concentration.top3_weight_pct", brief.facts)
        self.assertNotIn("risk.top3_weight_pct", brief.facts)


if __name__ == "__main__":
    unittest.main()
