"""Phase 3.1 — MacroIntelligenceBrief and Macro Outlook."""

from __future__ import annotations

import unittest

from investment_ami.engines.support.macro_context import resolve_macro_intelligence
from investment_ami.engines.support.macro_intelligence import (
    BRIEF_VERSION,
    build_macro_intelligence_brief,
)
from investment_ami.engines.support.macro_outlook_render import (
    render_compact_macro_outlook,
    render_full_macro_outlook,
)
from investment_ami.pipeline.instant import run_instant_engine


class TestMacroIntelligenceBrief(unittest.TestCase):
    _CTX = {
        "experience_mode": "Advanced Mode",
        "current_weights": {"VTI": "50%", "BND": "50%"},
        "health_rate_env": "Rising Rates",
        "health_inflation": "Moderate Inflation",
        "health_regime": "Expansion",
        "health_recession": 25,
        "health_valuation": "Fair Value",
    }

    def test_brief_populates_trace_sections(self) -> None:
        brief = build_macro_intelligence_brief(self._CTX, macro_intent="macro_rates")
        trace = brief.trace.to_computed_dict()
        self.assertEqual(brief.brief_version, BRIEF_VERSION)
        self.assertTrue(brief.trace.economic_regime)
        self.assertTrue(brief.trace.supporting_evidence)
        self.assertGreaterEqual(len(brief.trace.key_drivers), 2)
        self.assertGreaterEqual(len(brief.trace.primary_risks), 1)
        self.assertGreaterEqual(len(brief.trace.opportunities), 1)
        self.assertTrue(brief.trace.recommendation_drivers)
        self.assertTrue(brief.trace.final_macro_conclusion)
        self.assertIn("economic_regime", trace)

    def test_same_regime_across_intents(self) -> None:
        rates = build_macro_intelligence_brief(self._CTX, macro_intent="macro_rates")
        rec = build_macro_intelligence_brief(self._CTX, macro_intent="macro_recession")
        infl = build_macro_intelligence_brief(self._CTX, macro_intent="macro_inflation")
        self.assertEqual(rates.trace.economic_regime, rec.trace.economic_regime)
        self.assertEqual(rates.trace.key_drivers, infl.trace.key_drivers)
        self.assertNotEqual(rates.trace.recommendation_drivers, rec.trace.recommendation_drivers)

    def test_rising_rates_expansion_moderately_restrictive(self) -> None:
        brief = build_macro_intelligence_brief(self._CTX, macro_intent="macro_rates")
        self.assertEqual(brief.trace.economic_regime, "Moderately Restrictive")

    def test_missing_weights_caps_confidence(self) -> None:
        brief = build_macro_intelligence_brief({}, macro_intent="macro_rates")
        self.assertEqual(brief.confidence_pct, 55)
        self.assertFalse(brief.scenario.has_portfolio_weights)

    def test_compact_render_contains_regime_and_confidence(self) -> None:
        brief = build_macro_intelligence_brief(self._CTX, macro_intent="macro_rates")
        text = render_compact_macro_outlook(brief, beginner=False, macro_intent="macro_rates")
        self.assertIn("Macro Outlook", text)
        self.assertIn("Moderately Restrictive", text)
        self.assertIn("**Primary Risks:**", text)
        self.assertIn("**Opportunities:**", text)
        self.assertIn("\n- ", text)
        self.assertIn(f"{brief.confidence_pct}%", text)

    def test_stable_rates_hypothetical_note(self) -> None:
        ctx = {
            **self._CTX,
            "health_rate_env": "Stable Rates",
        }
        brief = build_macro_intelligence_brief(ctx, macro_intent="macro_rates")
        text = render_compact_macro_outlook(
            brief,
            beginner=False,
            macro_intent="macro_rates",
            question="What happens if interest rates rise 2%?",
        )
        self.assertIn("hypothetical", text.lower())

    def test_advanced_analyst_view_without_conclusion_prefix(self) -> None:
        result = run_instant_engine(
            "macro_rates",
            dict(self._CTX),
            beginner=False,
            question="What happens if interest rates rise 2%?",
        )
        pov = (result.analyst_sections or {}).get("portfolio_analyst_view", "")
        self.assertNotIn("Overall macro view is", pov)
        self.assertIn("Bond duration", pov)

    def test_full_render_includes_recommendation_drivers(self) -> None:
        brief = build_macro_intelligence_brief(self._CTX, macro_intent="macro_recession")
        full = render_full_macro_outlook(brief, beginner=False)
        self.assertIn("Recommendation drivers", full)
        self.assertIn(brief.trace.recommendation_drivers[0], full)

    def test_resolve_macro_intelligence_alias(self) -> None:
        brief = resolve_macro_intelligence(self._CTX, macro_intent="macro_inflation")
        self.assertEqual(brief.trace.economic_regime, "Moderately Restrictive")


class TestMacroSolverIntegration(unittest.TestCase):
    _CTX = {
        "experience_mode": "Advanced Mode",
        "current_weights": {
            "VTI": "50.0%",
            "QQQ": "20.0%",
            "VXUS": "20.0%",
            "VNQ": "10.0%",
        },
        "health_rate_env": "Stable Rates",
        "health_inflation": "Moderate Inflation",
        "health_regime": "Expansion",
        "health_recession": 20,
    }

    def test_rates_answer_has_outlook_and_trace(self) -> None:
        result = run_instant_engine(
            "macro_rates",
            dict(self._CTX),
            beginner=False,
            question="What happens if interest rates rise 2%?",
        )
        self.assertIn("**Macro Outlook**", result.short_answer)
        self.assertIn("---", result.short_answer)
        self.assertEqual(result.computed.get("macro_brief_version"), BRIEF_VERSION)
        self.assertIn("macro_reasoning_trace", result.computed)
        self.assertIn("net_return_shift_pp", result.computed)

    def test_shock_math_preserved_in_computed(self) -> None:
        from investment_ami_macro import (
            allocation_profile_from_ctx,
            parse_rate_rise_pct,
            rate_rise_portfolio_impacts,
        )

        ctx = dict(self._CTX)
        question = "What happens if interest rates rise 2%?"
        params = dict(ctx.get("scenario_params") or {})
        profile = allocation_profile_from_ctx(ctx)
        bump = parse_rate_rise_pct(question, scenario_params=params)
        expected_net = float(rate_rise_portfolio_impacts(profile, bump)["net_return_shift_pp"])
        enriched = run_instant_engine("macro_rates", ctx, beginner=False, question=question)
        self.assertEqual(enriched.computed.get("net_return_shift_pp"), expected_net)

    def test_inflation_computed_fields_preserved(self) -> None:
        result = run_instant_engine(
            "macro_inflation",
            {**self._CTX, "scenario_params": {"inflation_pct": 6.0}},
            beginner=False,
            question="What happens if inflation rises to 6%?",
        )
        self.assertEqual(result.computed.get("inflation_pct"), 6.0)
        self.assertIn("real_return_estimate_pct", result.computed)


if __name__ == "__main__":
    unittest.main()
