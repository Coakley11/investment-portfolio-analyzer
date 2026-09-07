"""AMI / explanation-layer semantic consistency (Option C, basis labels, Guided≠Optimizer)."""

from __future__ import annotations

import unittest
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pandas as pd

import portfolio_core as core
from applied_math_context import (
    build_investment_applied_math_context,
    investment_ami_insight_staleness_reasons,
)
from investment_ami.engines.support.education_content import format_advanced_coach_snapshot
from investment_ami.engines.support.portfolio_analysis_brief import build_portfolio_analysis_brief
from investment_ami.pipeline.synthesis_prompts import build_system_prompt
from suite_analytical_question import _CONTEXT_LABELS


_PILOT = ["VTI", "VXUS", "BND", "VNQ"]
_PILOT_T = ["Equity", "Equity", "Bonds", "REIT"]
_PILOT_W = np.array([0.40, 0.20, 0.30, 0.10], dtype=float)

# Exact live strings reported as FAILING on Explain This Portfolio (must never reappear).
_FORBIDDEN_EXPLAIN_STRINGS = (
    "A low Sharpe ratio means the portfolio may not be earning enough return for the risk taken.",
    "Concentration in VTI increases idiosyncratic risk.",
    "Consider trimming VTI to reduce concentration risk.",
    "Rebalancing toward higher Sharpe sleeves (bonds, diversifiers) may improve efficiency.",
)


def _synthetic_returns(periods: int = 260, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2019-01-01", periods=periods, freq="B")
    data = {
        "VTI": rng.normal(0.00015, 0.012, size=periods),
        "VXUS": rng.normal(0.00010, 0.013, size=periods),
        "BND": rng.normal(0.00002, 0.003, size=periods),
        "VNQ": rng.normal(0.00012, 0.014, size=periods),
    }
    return pd.DataFrame(data, index=idx)


class TestExplainThisPortfolioLiveForbiddenStrings(unittest.TestCase):
    """Regression: exact live FAIL strings cannot appear for Shadow #1."""

    def test_source_bans_legacy_phrases(self) -> None:
        import inspect

        src = inspect.getsource(core.generate_portfolio_explanation)
        for phrase in _FORBIDDEN_EXPLAIN_STRINGS:
            self.assertNotIn(phrase, src, msg=f"legacy phrase still in source: {phrase!r}")
        self.assertNotIn("increases idiosyncratic risk.", src)
        self.assertNotIn("Consider trimming {profile['top_ticker']}", src)
        self.assertNotIn("higher Sharpe sleeves", src)
        self.assertNotIn("may not be earning enough return for the risk taken", src)

    def test_shadow1_memo_runtime_bans(self) -> None:
        rets = _synthetic_returns()
        metrics = replace(
            core.compute_extended_metrics(rets, _PILOT_W, 0.04, 4250.0, tickers=_PILOT),
            sharpe_ratio=0.28,
            sortino_ratio=0.25,
            annual_return=0.0737,
            volatility=0.14,
            max_drawdown=-0.23,
        )
        expl = core.generate_portfolio_explanation(
            _PILOT,
            _PILOT_W,
            _PILOT_T,
            metrics,
            rets.corr(),
            core.risk_contribution(rets, _PILOT_W, tickers=_PILOT),
        )
        memo = expl.full_memo
        for phrase in _FORBIDDEN_EXPLAIN_STRINGS:
            self.assertNotIn(phrase, memo)
        # Positive Option C alignment for 40% VTI broad-market sleeve.
        joined_risk = " ".join(expl.risk_analysis).lower()
        self.assertIn("vti", joined_risk)
        self.assertIn("40", joined_risk)
        self.assertIn("broad-market", joined_risk)
        self.assertNotIn("increases idiosyncratic risk", joined_risk)
        self.assertIn("not single-name idiosyncratic", joined_risk)
        improv = " ".join(expl.suggested_improvements).lower()
        self.assertIn("guided", improv)
        self.assertNotIn("consider trimming vti", improv)
        sharpe_bits = " ".join(
            x for x in (expl.risk_analysis + expl.suggested_improvements) if "sharpe" in x.lower()
        ).lower()
        self.assertIn("diagnostic", sharpe_bits)
        self.assertIn("not a core health allocation trigger", sharpe_bits)
        self.assertNotIn("earning enough", sharpe_bits)


class TestExplanationDoesNotOverrideMostlyOnPlan(unittest.TestCase):
    """A — low Sharpe wording is diagnostic, not a Health override."""

    def test_low_sharpe_insight_is_diagnostic_not_verdict(self) -> None:
        rets = _synthetic_returns()
        metrics = replace(
            core.compute_extended_metrics(rets, _PILOT_W, 0.04, 4250.0, tickers=_PILOT),
            sharpe_ratio=0.28,
            sortino_ratio=0.25,
            annual_return=0.04,
            volatility=0.14,
        )
        insights = core.generate_portfolio_insights(
            _PILOT,
            _PILOT_W,
            _PILOT_T,
            metrics,
            rets.corr(),
            core.risk_contribution(rets, _PILOT_W, tickers=_PILOT),
        )
        joined = " ".join(insights).lower()
        self.assertTrue(any("sharpe" in i.lower() for i in insights))
        self.assertIn("diagnostic", joined)
        self.assertNotIn("may not be earning enough return for the risk taken", joined)

    def test_explanation_weakness_not_forward_expected(self) -> None:
        rets = _synthetic_returns()
        metrics = replace(
            core.compute_extended_metrics(rets, _PILOT_W, 0.04, 4250.0, tickers=_PILOT),
            annual_return=0.037,
            volatility=0.15,
            sharpe_ratio=0.25,
        )
        expl = core.generate_portfolio_explanation(
            _PILOT,
            _PILOT_W,
            _PILOT_T,
            metrics,
            rets.corr(),
            core.risk_contribution(rets, _PILOT_W, tickers=_PILOT),
        )
        weak = " ".join(expl.weaknesses).lower()
        self.assertIn("historical modeled", weak)
        self.assertNotIn("low expected return relative to volatility", weak)
        improv = " ".join(expl.suggested_improvements).lower()
        self.assertIn("guided", improv)
        self.assertNotIn("higher sharpe sleeves", improv)


class TestGuidedVsOptimizerWording(unittest.TestCase):
    """B/C — Guided ≠ Optimizer; corner solutions are not recommended allocation."""

    def test_context_model_note_and_synthesis_guardrails(self) -> None:
        ctx = build_investment_applied_math_context(
            "Portfolio Health",
            {
                "investment_active_tab": "Portfolio Health",
                "health_result": SimpleNamespace(
                    score=81.0,
                    score_label="Mostly On Plan",
                    status_message="Core Portfolio Health is mostly on plan (81/100).",
                    health_diagnostics={
                        "annual_return": 0.0737,
                        "annual_volatility": 0.12,
                        "portfolio_sharpe": 0.28,
                        "max_drawdown": -0.23,
                    },
                ),
                "holdings_df": pd.DataFrame(
                    {"Ticker": _PILOT, "Weight (%)": [40, 20, 30, 10]}
                ),
            },
        )
        note = str(ctx.get("context_note_models") or "").lower()
        self.assertIn("guided", note)
        self.assertIn("optimizer", note)
        self.assertIn("monte carlo", note)
        self.assertEqual(ctx.get("health_score_label"), "Mostly On Plan")

        prompt = build_system_prompt(beginner=False).lower()
        self.assertIn("guided", prompt)
        self.assertIn("optimizer", prompt)
        self.assertIn("recommended allocation", prompt)
        self.assertIn("corner solutions", prompt)
        self.assertIn("mostly on plan", prompt)
        self.assertIn("not** the app's recommended allocation".replace("**", ""), prompt.replace("**", ""))


class TestHistoricalVsForwardLabels(unittest.TestCase):
    """D/E — historical return display is not 'Expected return' / forward."""

    def test_display_and_brief_labels(self) -> None:
        self.assertEqual(_CONTEXT_LABELS["expected_return"], "Historical modeled return")
        brief = build_portfolio_analysis_brief(
            {
                "expected_return": "7.4%",
                "sharpe_ratio": "0.28",
                "health_score": 81,
                "health_score_label": "Mostly On Plan",
                "context_note_historical": "historical modeled",
            }
        )
        er = brief.fact_index["performance.expected_return_historical"]
        self.assertIn("Historical modeled", er.label)
        self.assertNotIn("forward", er.label.lower())
        self.assertEqual(brief.facts.get("health.score_label"), "Mostly On Plan")


class TestMonteCarloAndBenchmarkSemantics(unittest.TestCase):
    """F/G — MC modeled; policy ≠ SPY alone."""

    def test_synthesis_and_model_notes(self) -> None:
        prompt = build_system_prompt(beginner=False).lower()
        self.assertIn("monte carlo", prompt)
        self.assertIn("simulated", prompt)
        self.assertIn("not forecast certainty", prompt)
        self.assertIn("spy/agg/bil", prompt)
        self.assertIn("spy alone", prompt)


class TestLedgerVsBacktestAndMacro(unittest.TestCase):
    """H/I — ledger ≠ static backtest; macro what-if."""

    def test_historical_note_mentions_static_weights_not_ledger(self) -> None:
        ctx = build_investment_applied_math_context(
            "Portfolio Health",
            {
                "health_result": SimpleNamespace(
                    score=81.0,
                    score_label="Mostly On Plan",
                    health_diagnostics={"annual_return": 0.0737, "portfolio_sharpe": 0.28},
                ),
            },
        )
        note = str(ctx.get("context_note_historical") or "").lower()
        self.assertIn("static current weights", note)
        self.assertIn("not ledger", note)
        prompt = build_system_prompt(beginner=False).lower()
        self.assertIn("what-if", prompt)


class TestAmiCacheInvalidationSignal(unittest.TestCase):
    """J — stale insight detection on objective/basis change."""

    def test_staleness_on_objective_and_basis(self) -> None:
        insight = {
            "source_app": "investment",
            "source_state": {
                "entity_params": {
                    "objective": "balanced growth",
                    "holdings_fingerprint": "fp-old",
                },
                "filter_params": {
                    "mc_assumption_mode": "Historical returns",
                    "opt_assumption_mode": "Historical returns",
                },
            },
        }
        session = {
            "health_objective": "capital preservation",
            "holdings_df": pd.DataFrame({"Ticker": _PILOT, "Weight (%)": [40, 20, 30, 10]}),
            "mc_assumption_mode": "Forward-looking (macro-adjusted)",
            "opt_assumption_mode": "Forward-looking (macro-adjusted)",
        }
        reasons = investment_ami_insight_staleness_reasons(session, insight)
        self.assertTrue(any("objective" in r for r in reasons))
        self.assertTrue(any("Monte Carlo" in r for r in reasons))
        self.assertTrue(any("optimizer" in r for r in reasons))


class TestEconomicExposureAndCanonicalDiagnostics(unittest.TestCase):
    """K/L — education mapping; diagnostics from health_diagnostics."""

    def test_coach_and_diagnostics(self) -> None:
        text = format_advanced_coach_snapshot("Balanced Growth").lower()
        self.assertIn("historical modeled return", text)
        self.assertNotIn("framework: expected return vs", text)
        ctx = build_investment_applied_math_context(
            "Portfolio Health",
            {
                "health_result": SimpleNamespace(
                    score=81.0,
                    score_label="Mostly On Plan",
                    sharpe=None,
                    expected_return=None,
                    health_diagnostics={
                        "annual_return": 0.0559,
                        "annual_volatility": 0.1337,
                        "portfolio_sharpe": 0.28,
                        "max_drawdown": -0.20,
                    },
                ),
            },
        )
        self.assertIn("5.6", str(ctx["expected_return"]))
        self.assertIn("0.28", str(ctx["sharpe_ratio"]))
        prefix = str(ctx.get("context_note_historical") or "").split("unless")[0].lower()
        self.assertNotIn("forward", prefix)


class TestContributionLanguage(unittest.TestCase):
    def test_whats_working_arithmetic_contribution_language(self) -> None:
        src = open(core.__file__, encoding="utf-8").read()
        self.assertIn("weight × asset arithmetic ann. return", src)
        self.assertIn("modeled annualized return", src)


if __name__ == "__main__":
    unittest.main()
