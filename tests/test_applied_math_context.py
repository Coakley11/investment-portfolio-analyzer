"""Tests for Investment Applied Math context extractors."""

from __future__ import annotations

import unittest

import pandas as pd

from applied_math_context import build_investment_applied_math_context


class TestInvestmentAppliedMathContext(unittest.TestCase):
    def test_portfolio_health_context(self) -> None:
        class _HR:
            score = 78.0
            expected_return = 8.2
            volatility = 12.1
            sharpe = 0.68
            max_drawdown = -18.3
            risk_level = "Moderate"

        session = {
            "investment_active_tab": "Portfolio Health",
            "investment_experience": "Beginner",
            "sidebar_portfolio_value": 250000,
            "health_result": _HR(),
            "holdings_df": pd.DataFrame(
                {"Ticker": ["VTI", "BND"], "Weight": [60.0, 40.0]},
            ),
        }
        ctx = build_investment_applied_math_context("Portfolio Health", session)
        self.assertEqual(ctx["health_score"], 78.0)
        self.assertIn("VTI", ctx.get("holdings", []))
        self.assertIn("context_note_historical", ctx)
        self.assertIn("sharpe_ratio", ctx)


if __name__ == "__main__":
    unittest.main()
