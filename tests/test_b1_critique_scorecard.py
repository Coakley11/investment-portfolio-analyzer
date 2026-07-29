"""B1 critique structural metrics and prompt version tests."""

from __future__ import annotations

import unittest

from investment_ami.evaluation.b1_critique_scorecard import compute_b1_structural_metrics
from investment_ami.pipeline.analytical_synthesis import _compose_answer_markdown
from investment_ami.pipeline.synthesis_prompts import SYNTHESIS_PROMPT_VERSION, build_system_prompt


class TestB1CritiqueScorecard(unittest.TestCase):
    def test_structural_score_prefers_thesis_and_holdings(self) -> None:
        weak = compute_b1_structural_metrics(
            answer_markdown="Generic diversify more.",
            parsed_response={},
            holdings={"VOO": 55, "BND": 45},
        )
        strong_md = (
            "## Investment Thesis\n\nVOO dominates equity risk while BND provides ballast because rates "
            "and inflation regimes transmit differently through each sleeve.\n\n"
            "## Executive Summary\nBecause [concentration.summary] …\n\n"
            "## Scenario Analysis\nRecession: BND may benefit; VOO may struggle. Rising rates: …"
        )
        strong = compute_b1_structural_metrics(
            answer_markdown=strong_md,
            parsed_response={
                "investment_thesis": "VOO/BND barbell thesis.",
                "priority_recommendations": {"highest_priority": "Review VOO weight."},
                "citations": [{"fact_id": "concentration.summary", "excerpt": "x"}],
            },
            holdings={"VOO": 55, "BND": 45},
        )
        self.assertGreater(strong.structural_score, weak.structural_score)
        self.assertEqual(strong.holding_symbols_mentioned, 2)

    def test_compose_answer_prepends_thesis(self) -> None:
        md = _compose_answer_markdown(
            {"investment_thesis": "Central narrative.", "answer_markdown": "## Executive Summary\nBody."}
        )
        self.assertIn("## Investment Thesis", md)
        self.assertIn("Central narrative", md)

    def test_prompt_version_includes_cio_thesis(self) -> None:
        self.assertEqual(SYNTHESIS_PROMPT_VERSION, "p4-v3-cio-thesis")
        sys_prompt = build_system_prompt(beginner=False)
        self.assertIn("investment_thesis", sys_prompt)
        self.assertIn("Coherent investment thesis", sys_prompt)


if __name__ == "__main__":
    unittest.main()
