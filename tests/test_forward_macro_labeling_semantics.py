"""Labeling regression: stress-adjusted drawdown + forward optimizer valuation scope."""

from __future__ import annotations

import unittest
from pathlib import Path

from components.calculation_transparency import (
    FORWARD_DRAWDOWN,
    FORWARD_OPTIMIZER_SNAPSHOT_SCOPE,
    FORWARD_OPTIMIZER_SNAPSHOT_SUBTITLE,
    OPTIMIZER,
    OPTIMIZER_CONFIDENCE,
    STRESS_ADJUSTED_MAX_DRAWDOWN_HELP,
    STRESS_ADJUSTED_MAX_DRAWDOWN_LABEL,
    optimizer_results_methodology_lead,
)

ROOT = Path(__file__).resolve().parents[1]


class TestForwardMacroLabelingSemantics(unittest.TestCase):
    def test_drawdown_label_is_stress_adjusted_not_simulated_forward(self) -> None:
        self.assertEqual(STRESS_ADJUSTED_MAX_DRAWDOWN_LABEL, "Stress-Adjusted Max Drawdown")
        self.assertNotEqual(STRESS_ADJUSTED_MAX_DRAWDOWN_LABEL, "Forward Max Drawdown")
        help_l = STRESS_ADJUSTED_MAX_DRAWDOWN_HELP.lower()
        self.assertIn("recession probability", help_l)
        self.assertIn("not a", help_l)
        self.assertIn("forward-simulated", help_l)
        body = FORWARD_DRAWDOWN.lower()
        self.assertIn("recession", body)
        self.assertIn("not", body)
        self.assertIn("forward-simulated", body)
        self.assertIn("valuation environment does not change this metric", body)

    def test_streamlit_forward_macro_uses_stress_adjusted_drawdown_label(self) -> None:
        src = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
        self.assertIn("STRESS_ADJUSTED_MAX_DRAWDOWN_LABEL", src)
        self.assertIn("STRESS_ADJUSTED_MAX_DRAWDOWN_HELP", src)
        # Bare UI string that implied simulated future DD without qualification.
        self.assertNotIn('m5.metric("Forward Max Drawdown"', src)
        self.assertNotIn('"Forward Max Drawdown"', src)

    def test_optimizer_scope_mentions_valuation_does_not_alter_per_asset_mu(self) -> None:
        scope = FORWARD_OPTIMIZER_SNAPSHOT_SCOPE.lower()
        self.assertIn("valuation", scope)
        self.assertIn("per-asset expected-return", scope)
        self.assertIn("does not currently alter", scope)
        self.assertIn("rates", scope)
        self.assertIn("inflation", scope)
        self.assertIn("covariance", scope)

        opt = OPTIMIZER.lower()
        self.assertIn("per-asset expected-return vector", opt)
        self.assertIn("valuation environment", opt)
        self.assertIn("does **not**", OPTIMIZER)
        self.assertIn("currently alter the optimizer's **per-asset expected-return vector**", OPTIMIZER)
        self.assertIn("does not currently alter", opt)

        conf = OPTIMIZER_CONFIDENCE.lower()
        self.assertIn("valuation environment", conf)
        self.assertIn("per-asset", conf)

        lead = optimizer_results_methodology_lead("Forward-looking (macro-adjusted)").lower()
        self.assertIn("valuation", lead)
        self.assertIn("per-asset expected returns", lead)

    def test_streamlit_forward_optimizer_snapshot_uses_scope_copy(self) -> None:
        src = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
        self.assertIn("FORWARD_OPTIMIZER_SNAPSHOT_SCOPE", src)
        self.assertIn("FORWARD_OPTIMIZER_SNAPSHOT_SUBTITLE", src)
        self.assertNotIn(
            '"Optimizer outputs under your forward assumptions."',
            src,
        )
        self.assertIn(FORWARD_OPTIMIZER_SNAPSHOT_SUBTITLE[:40], FORWARD_OPTIMIZER_SNAPSHOT_SUBTITLE)

    def test_labeling_constants_do_not_encode_calculation_changes(self) -> None:
        # Sanity: help/label are strings only — formula remains in methodology body.
        self.assertIn("historical_max_drawdown", FORWARD_DRAWDOWN)
        self.assertIn("drawdown_mult", FORWARD_DRAWDOWN)
        self.assertIn("recession_probability", FORWARD_DRAWDOWN)


if __name__ == "__main__":
    unittest.main()
