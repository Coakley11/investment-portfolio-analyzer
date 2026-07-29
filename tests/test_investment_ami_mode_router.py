"""Phase 1 routing validation matrix + Phase 2 portfolio analysis brief tests."""

from __future__ import annotations

import unittest

from investment_ami.engines.support.portfolio_analysis_brief import build_portfolio_analysis_brief
from investment_ami.routing.mode_router import route_investment_response_mode

_BENCH_CTX = {
    "page": "Portfolio Health",
    "current_weights": {"VOO": 60.0, "BND": 40.0},
    "asset_class_breakdown": {"Equity": 60.0, "Bond": 40.0},
    "health_score": 72.0,
    "volatility": "12.5%",
    "expected_return": "8.1%",
    "sharpe_ratio": "0.65",
    "health_rate_env": "Stable Rates",
    "health_inflation": "Moderate Inflation",
    "health_regime": "Expansion",
    "scenario_params": {"rate_shock": "Stable Rates"},
}

_ANALYTICAL_CASES: tuple[tuple[str, str], ...] = (
    ("Critique my portfolio as an institutional portfolio manager.", "critique"),
    ("What are the five biggest risks facing my portfolio?", "ranked_risks"),
    ("Argue against my portfolio.", "devils_advocate"),
    ("What would Ray Dalio think of this portfolio?", "philosophy_lens"),
    ("Compare my portfolio to a university endowment.", "peer_compare"),
    (
        "If inflation remains elevated for five years, what changes would you make?",
        "conditional_macro",
    ),
    (
        "Analyze how my portfolio would likely have performed during the 2008 Financial Crisis, "
        "the COVID-19 crash of 2020, and the inflationary period of 2022. Which holdings would have "
        "been the primary drivers of performance in each environment?",
        "historical_scenario",
    ),
)

_DETERMINISTIC_CASES: tuple[tuple[str, str], ...] = (
    ("What percentage of my portfolio is technology?", "sector_exposure"),
    ("What is my largest holding?", "portfolio_concentration"),
    ("What is my current sector allocation?", "sector_exposure"),
    ("Should I own both VOO and QQQ?", "etf_overlap"),
    ("What is my expected volatility?", "portfolio_risk"),
)


class TestInvestmentAmiModeRouterMatrix(unittest.TestCase):
    def test_starter_questions_remain_deterministic(self) -> None:
        import investment_ami_context as legacy

        for starter in legacy.INVESTMENT_AMI_STARTER_QUESTIONS:
            with self.subTest(starter=starter):
                mode = route_investment_response_mode(starter, _BENCH_CTX)
                self.assertEqual(mode.response_mode, "deterministic")

    def test_analytical_benchmark_matrix(self) -> None:
        for question, expected_tag in _ANALYTICAL_CASES:
            with self.subTest(question=question):
                mode = route_investment_response_mode(question, _BENCH_CTX)
                self.assertEqual(
                    mode.response_mode,
                    "analytical_synthesis",
                    msg=mode.reasons,
                )
                self.assertEqual(mode.question_tag, expected_tag)
                self.assertEqual(mode.effective_intent_id, "analytical_synthesis")

    def test_deterministic_benchmark_matrix(self) -> None:
        for question, expected_intent in _DETERMINISTIC_CASES:
            with self.subTest(question=question):
                mode = route_investment_response_mode(question, _BENCH_CTX)
                self.assertEqual(
                    mode.response_mode,
                    "deterministic",
                    msg=(mode.reasons, mode.matched_rules),
                )
                self.assertEqual(mode.deterministic_intent, expected_intent)


class TestPortfolioAnalysisBrief(unittest.TestCase):
    def test_brief_includes_core_facts_and_provenance(self) -> None:
        brief = build_portfolio_analysis_brief(_BENCH_CTX, question="Critique my portfolio.")
        self.assertEqual(brief.brief_version, "2.1.0")
        self.assertGreaterEqual(len(brief.facts), 8)
        self.assertIn("holdings.largest_weight_ticker", brief.facts)
        self.assertIn("holdings.largest_weight_ticker", brief.fact_index)
        desc = brief.fact_index["holdings.largest_weight_ticker"]
        self.assertEqual(desc.source_engine, "portfolio_concentration")
        self.assertIn("concentration", brief.sections)
        self.assertIn("macro", brief.sections)
        payload = brief.to_dict()
        self.assertIn("fact_index", payload)
        self.assertIn("sections", payload)

    def test_brief_records_limitations_without_weights(self) -> None:
        brief = build_portfolio_analysis_brief({}, question="Open question.")
        self.assertTrue(any("No portfolio weights" in x for x in brief.limitations))


if __name__ == "__main__":
    unittest.main()
