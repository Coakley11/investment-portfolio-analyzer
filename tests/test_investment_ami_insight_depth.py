"""Investment page vs AMI deep-dive insight rendering."""

from __future__ import annotations

import unittest

from investment_ami_answer_format import (
    build_analyst_sections,
    render_ami_deep_dive_markdown,
    render_investment_page_insight_markdown,
)


class TestInvestmentInsightDepth(unittest.TestCase):
    def test_investment_page_is_concise(self) -> None:
        sections = build_analyst_sections(
            direct_answer="Portfolio is moderately concentrated.",
            portfolio_analyst_view="Tech exposure drives most of the risk budget.",
            key_variables="Top holding: VTI 50%\nTech exposure: 36.7%",
            tradeoffs="Trimming tech reduces upside in rallies.",
            what_if_scenarios="A 20% tech drawdown would cut portfolio value materially.",
            recommended_actions="Reduce concentration modestly and add defensive ballast.",
            risk_notes="Concentration risk remains elevated.",
        )
        page_md = render_investment_page_insight_markdown(sections, beginner=False)
        deep_md = render_ami_deep_dive_markdown(sections, beginner=False)

        self.assertIn("Direct Answer", page_md)
        self.assertIn("Key Variables", page_md)
        self.assertIn("Recommended Actions", page_md)
        self.assertNotIn("Tradeoffs", page_md)
        self.assertNotIn("What-If", page_md)

        self.assertIn("Tradeoffs", deep_md)
        self.assertIn("What-If Scenarios", deep_md)
        self.assertIn("Portfolio Analyst View", deep_md)
        self.assertGreater(len(deep_md), len(page_md))


if __name__ == "__main__":
    unittest.main()
