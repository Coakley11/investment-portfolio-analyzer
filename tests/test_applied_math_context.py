"""Tests for Investment Applied Math context extractors."""

from __future__ import annotations

import unittest

import pandas as pd

import portfolio_core as core

from applied_math_context import (
    apply_source_state_to_session,
    build_investment_applied_math_context,
    build_source_state,
    record_rebalance_from_health,
)


class TestInvestmentAppliedMathContext(unittest.TestCase):
    def test_portfolio_health_context(self) -> None:
        class _HR:
            score = 78.0
            expected_return = 8.2
            volatility = 12.1
            sharpe = 0.68
            max_drawdown = -18.3
            risk_level = "Moderate"
            rebalance_df = pd.DataFrame()
            recommendations = []

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

    def test_build_source_state_uses_holdings_fingerprint(self) -> None:
        session = {
            "investment_active_tab": "⑤ Portfolio Health",
            "health_objective": "income",
            "experience": "Advanced Mode",
            "risk_free_pct": 3.5,
            "holdings_df": pd.DataFrame(
                {
                    "Ticker": ["VYM", "BND"],
                    "Weight (%)": [50.0, 50.0],
                    "Asset Type": ["Dividend ETF", "Bonds"],
                }
            ),
        }
        state = build_source_state("⑤ Portfolio Health", session)
        self.assertEqual(state["source_app"], "investment")
        ent = state["entity_params"]
        self.assertIn("BND:50.0:Bonds", ent["holdings_fingerprint"])
        self.assertIn("VYM:50.0:Dividend ETF", ent["holdings_fingerprint"])
        self.assertEqual(ent["objective"], "income")
        self.assertEqual(state["filter_params"].get("risk_free_pct"), 3.5)

    def test_apply_source_state_restores_holdings_and_goal(self) -> None:
        holdings = pd.DataFrame(
            {
                "Ticker": ["BND", "VYM"],
                "Weight (%)": [50.0, 50.0],
                "Asset Type": ["Bonds", "Dividend ETF"],
            }
        )
        session = {
            "investment_active_tab": "① Choose Goal",
            "holdings_df": pd.DataFrame(core.DEFAULT_HOLDINGS),
        }
        state = build_source_state(
            "⑤ Portfolio Health",
            {
                "investment_active_tab": "⑤ Portfolio Health",
                "guide_goal_choice": "Balanced growth",
                "preset_applied": "Balanced",
                "portfolio_built": True,
                "holdings_df": holdings,
            },
        )
        apply_source_state_to_session(session, state)
        self.assertEqual(session["investment_active_tab"], "⑤ Portfolio Health")
        self.assertEqual(session["guide_goal_choice"], "Balanced growth")
        restored = session["holdings_df"]
        self.assertEqual(len(restored), 2)
        tickers = set(restored["Ticker"].astype(str).str.upper())
        self.assertEqual(tickers, {"BND", "VYM"})

    def test_rebalance_drift_captured_from_health(self) -> None:
        class _HR:
            score = 72.0
            avg_drift = 0.042
            score_label = "Fair"
            rebalance_df = pd.DataFrame(
                {
                    "Ticker": ["VTI", "BND"],
                    "Current (%)": [60.0, 40.0],
                    "Objective (%)": [55.0, 45.0],
                    "Drift vs Objective (%)": [5.0, -5.0],
                }
            )
            recommendations = ["Reduce VTI overweight toward objective"]

        session: dict = {}
        record_rebalance_from_health(session, _HR())
        ctx = build_investment_applied_math_context("Portfolio Health", session)
        drift = ctx.get("rebalance_drift") or session.get("rebalance_drift")
        self.assertIsInstance(drift, dict)
        self.assertIn("VTI", drift)
        self.assertIn("rebalance_recommendation", ctx)


if __name__ == "__main__":
    unittest.main()
