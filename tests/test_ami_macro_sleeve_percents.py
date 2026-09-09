"""Regression: AMI macro sleeve line uses canonical allocation_profile decimals → percent."""

from __future__ import annotations

import unittest

from investment_ami.engines.support.macro_context import resolve_macro_scenario_context
from investment_ami_macro import (
    _macro_environment_solve,
    allocation_profile_from_ctx,
)


def _shadow1_ctx() -> dict:
    return {
        "experience_mode": "Advanced Mode",
        "current_weights": {
            "VTI": "40.0%",
            "VXUS": "20.0%",
            "BND": "30.0%",
            "VNQ": "10.0%",
        },
        "holdings": ["VTI", "VXUS", "BND", "VNQ"],
        "health_inflation": "High Inflation",
        "health_rate_env": "Rising Rates",
        "health_recession": 60,
        "health_valuation": "Expensive",
        "health_regime": "Recession",
        "objective": "balanced growth",
        "forward_modeled_return": -0.2104,
        "forward_modeled_volatility": 0.4712,
        "forward_modeled_sharpe": -0.53,
        "forward_modeled_return_display": "-21.04%",
        "forward_modeled_volatility_display": "47.12%",
        "forward_modeled_sharpe_display": "-0.53",
        "forward_metrics_are_scenario_outputs": True,
    }


class TestAmiMacroSleevePercents(unittest.TestCase):
    def test_shadow1_canonical_profile_decimals(self) -> None:
        prof = allocation_profile_from_ctx(_shadow1_ctx())
        # Health taxonomy: Equity includes REIT / Dividend ETF.
        self.assertAlmostEqual(float(prof["equity"]), 0.70, places=4)
        self.assertAlmostEqual(float(prof["bonds"]), 0.30, places=4)
        self.assertAlmostEqual(float(prof["reit"]), 0.10, places=4)
        self.assertAlmostEqual(float(prof["tbills"]), 0.0, places=4)
        # Equity + bonds = 100% (REIT already inside equity).
        self.assertAlmostEqual(float(prof["equity"]) + float(prof["bonds"]), 1.0, places=4)

    def test_decimal_to_percent_formatting_not_1_0_0(self) -> None:
        result = _macro_environment_solve(
            _shadow1_ctx(),
            beginner=False,
            question="How does the current macro environment affect my portfolio?",
        )
        sections = result.analyst_sections or {}
        blob = " ".join(str(v) for v in sections.values()) + "\n" + str(result.short_answer or "")
        self.assertIn("70%", blob)
        self.assertIn("30%", blob)
        self.assertIn("10%", blob)
        self.assertNotIn("1% / 0% / 0%", blob)
        self.assertNotRegex(blob, r"Equity / bonds / REIT:\s*\*\*1%\*\*")

    def test_reit_handling_and_equity_includes_reit(self) -> None:
        result = _macro_environment_solve(
            _shadow1_ctx(),
            beginner=False,
            question="How does the current macro environment affect my portfolio?",
        )
        computed = result.computed or {}
        self.assertEqual(computed.get("sleeve_source"), "portfolio_core.allocation_profile")
        self.assertAlmostEqual(float(computed["sleeve_equity_pct"]), 70.0, places=1)
        self.assertAlmostEqual(float(computed["sleeve_bonds_pct"]), 30.0, places=1)
        self.assertAlmostEqual(float(computed["sleeve_reit_pct"]), 10.0, places=1)
        self.assertAlmostEqual(float(computed["sleeve_equity_ex_reit_pct"]), 60.0, places=1)
        blob = str((result.analyst_sections or {}).get("key_variables") or "")
        self.assertIn("Equity includes REIT", blob)
        self.assertIn("60%", blob)

    def test_bond_sleeve_handling(self) -> None:
        result = _macro_environment_solve(
            _shadow1_ctx(),
            beginner=False,
            question="How does the current macro environment affect my portfolio?",
        )
        blob = str(result.short_answer or "") + str(result.analyst_sections or {})
        self.assertIn("Bond sleeve **30%**", blob)
        self.assertAlmostEqual(float((result.computed or {})["sleeve_bonds_pct"]), 30.0, places=1)

    def test_category_totals_consistent(self) -> None:
        prof = allocation_profile_from_ctx(_shadow1_ctx())
        eq = float(prof["equity"]) * 100
        bonds = float(prof["bonds"]) * 100
        reit = float(prof["reit"]) * 100
        # Exclusive partition for displayed taxonomy clarification:
        # equity ex-REIT + REIT + bonds ≈ 100
        self.assertAlmostEqual((eq - reit) + reit + bonds, 100.0, places=1)

    def test_macro_answer_uses_canonical_not_ad_hoc(self) -> None:
        ctx = _shadow1_ctx()
        # Ad-hoc wrong fields must not be preferred over allocation_profile.
        ctx["equity"] = 1
        ctx["bonds"] = 0
        ctx["reit"] = 0
        ctx["allocation_profile"] = {"equity": 0.01, "bonds": 0.0, "reit": 0.0}
        macro = resolve_macro_scenario_context(ctx)
        self.assertAlmostEqual(float(macro.allocation_profile["equity"]), 0.70, places=4)
        result = _macro_environment_solve(
            ctx,
            beginner=False,
            question="How does the current macro environment affect my portfolio?",
        )
        self.assertAlmostEqual(float((result.computed or {})["sleeve_equity_pct"]), 70.0, places=1)
        self.assertAlmostEqual(float((result.computed or {})["sleeve_bonds_pct"]), 30.0, places=1)
        self.assertAlmostEqual(float((result.computed or {})["sleeve_reit_pct"]), 10.0, places=1)


if __name__ == "__main__":
    unittest.main()
