"""Optimizer Results methodology lead must match the selected basis."""

from __future__ import annotations

import unittest

from components.calculation_transparency import (
    is_forward_optimizer_basis,
    optimizer_results_methodology_lead,
)


class TestOptimizerBasisLabel(unittest.TestCase):
    def test_historical_lead_does_not_claim_forward(self) -> None:
        lead = optimizer_results_methodology_lead("Historical returns")
        self.assertTrue(lead.startswith("Historical long-only mean-variance"))
        self.assertIn("SLSQP", lead)
        self.assertIn("historical expected returns", lead.lower())
        self.assertNotIn("Forward-looking", lead)
        self.assertNotIn("macro-adjusted expected returns", lead)

    def test_forward_lead_does_not_claim_historical(self) -> None:
        lead = optimizer_results_methodology_lead(
            "Forward-looking (macro-adjusted)"
        )
        self.assertTrue(
            lead.startswith("Forward-looking (macro-adjusted) long-only mean-variance")
        )
        self.assertIn("SLSQP", lead)
        self.assertIn("forward-adjusted covariance", lead.lower())
        self.assertIn("valuation", lead.lower())
        self.assertIn("per-asset expected returns", lead.lower())
        # Must not open with / assert Historical as the active basis.
        self.assertFalse(lead.startswith("Historical"))
        self.assertNotIn("Historical long-only", lead)
        self.assertNotIn("historical expected returns", lead.lower())

    def test_streamlit_optimizer_section_uses_basis_aware_helper(self) -> None:
        from pathlib import Path

        src = Path(__file__).resolve().parents[1] / "streamlit_app.py"
        text = src.read_text(encoding="utf-8")
        # Narrow regression: must call helper; must not hardcode Historical-only lead.
        self.assertIn("optimizer_results_methodology_lead(opt_assumption_mode)", text)
        self.assertNotIn(
            '"Historical long-only mean-variance experiment (SLSQP). "',
            text,
        )


if __name__ == "__main__":
    unittest.main()
