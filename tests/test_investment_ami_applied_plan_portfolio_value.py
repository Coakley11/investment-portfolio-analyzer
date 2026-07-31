"""AMI submit must not overwrite planning-page applied portfolio value."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import portfolio_core as core

from applied_math_context import apply_source_state_to_session, build_source_state
from components.investment_planning import PLAN_MONTHLY_PROVIDED_KEY
from components.ui_helpers import request_sidebar_portfolio_value
from investment_ami.decision_support.modules import MODULE_ALLOCATION_ADVISOR
from investment_ami.decision_support.pipeline import run_decision_support_module
from investment_ami.decision_support.presentation import render_user_analyst_sections
from investment_persistent_state import apply_investment_disk_state, build_investment_disk_state
from planning_portfolio_value import (
    APPLIED_PLAN_PORTFOLIO_VALUE_KEY,
    effective_planning_portfolio_value_for_ami,
    get_applied_plan_portfolio_value,
    prepare_session_for_investment_ami_submit,
    set_applied_plan_portfolio_value,
)
from suite_analytical_question import execute_investment_ami_submit_pipeline


def _sample_plan(long_term: float = 58_451.0) -> core.InvestmentPlanResult:
    return core.InvestmentPlanResult(
        total_available=100_000,
        suggested_emergency_reserve=20_000,
        short_term_cash_amount=10_000,
        debt_reserve=5_000,
        amount_potentially_investable=65_000,
        long_term_suggested=long_term,
        short_term_investable=6_549,
        monthly_contribution=0,
        summary_lines=[],
        educational_notes=[],
    )


class _FakeSessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class _FakeSt:
    def __init__(self) -> None:
        self.session_state = _FakeSessionState()


def _assert_applied(ss: dict, expected: int) -> None:
    assert get_applied_plan_portfolio_value(ss) == expected
    assert ss.get("sidebar_portfolio_value") == expected
    assert effective_planning_portfolio_value_for_ami(ss) == float(expected)


class TestAppliedPlanPortfolioValueAmiSubmit(unittest.TestCase):
    def test_apply_long_term_then_ami_pipeline_keeps_value(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        long_term = 58_451
        ss.update(
            {
                "investment_active_tab": "Portfolio Inputs",
                "plan_total_cash": 100_000,
                "plan_emergency": 20_000,
                "plan_near_term": 10_000,
                "plan_debt": 5_000,
                "plan_expenses": 5_000,
                "plan_horizon": 20,
                "plan_risk": "Medium",
                PLAN_MONTHLY_PROVIDED_KEY: False,
                "investment_plan_generated": True,
                "investment_plan": _sample_plan(long_term),
                "sidebar_portfolio_value": 100_000,
                "holdings_market_value_note": 100_000,
            }
        )
        set_applied_plan_portfolio_value(ss, long_term, source="long_term")
        request_sidebar_portfolio_value(long_term, force=True)
        prepare_session_for_investment_ami_submit(ss)
        _assert_applied(ss, long_term)

        question = "Is the amount I currently have invested appropriate?"

        with patch("applied_math_return_insight.store_applied_math_insight", return_value="pv-1"), patch(
            "suite_analytical_question.submit_analytical_question",
            wraps=__import__(
                "suite_analytical_question", fromlist=["submit_analytical_question"]
            ).submit_analytical_question,
        ), patch(
            "suite_analytical_question._upsert_applied_intelligence_resume",
        ), patch(
            "suite_analytical_question.build_submit_context",
            wraps=__import__(
                "suite_analytical_question", fromlist=["build_submit_context"]
            ).build_submit_context,
        ) as ctx_mock:
            ok, err = execute_investment_ami_submit_pipeline(
                st,
                ss,
                question=question,
                source_page="Portfolio Inputs",
                page_suffix="Portfolio_Inputs",
                send_gen=0,
            )
            ctx = ctx_mock.call_args.kwargs.get("session_state") or ss
            _assert_applied(dict(ctx), long_term)

        self.assertTrue(ok, err)
        _assert_applied(ss, long_term)

        ctx_arg = ctx_mock.call_args.kwargs.get("session_state") or ss
        source_state = build_source_state("Portfolio Inputs", dict(ctx_arg))
        self.assertEqual(source_state["filter_params"]["sidebar_portfolio_value"], long_term)

        stale_return = {
            "source_app": "investment",
            "source_page": "Portfolio Inputs",
            "filter_params": {"sidebar_portfolio_value": 100_000},
            "entity_params": {},
            "widget_params": {},
        }
        apply_source_state_to_session(ss, stale_return)
        _assert_applied(ss, long_term)

        disk = build_investment_disk_state(st)
        st2 = _FakeSt()
        st2.session_state.update(
            {
                "sidebar_portfolio_value": long_term,
                APPLIED_PLAN_PORTFOLIO_VALUE_KEY: long_term,
                "investment_plan_applied_portfolio_value": long_term,
                "investment_plan_applied_source": "long_term",
            }
        )
        disk["sidebar_portfolio_value"] = 100_000
        apply_investment_disk_state(st2, disk)
        _assert_applied(st2.session_state, long_term)

    def test_facts_used_shows_applied_not_holdings_sidebar(self) -> None:
        ss = {
            "plan_total_cash": 100_000,
            "plan_emergency": 20_000,
            "plan_near_term": 10_000,
            "plan_debt": 5_000,
            "plan_expenses": 5_000,
            "plan_horizon": 20,
            "plan_risk": "Medium",
            PLAN_MONTHLY_PROVIDED_KEY: False,
            "investment_plan_generated": True,
            "investment_plan": _sample_plan(58_451),
            "sidebar_portfolio_value": 100_000,
            "applied_plan_portfolio_value": 58_451,
            "investment_plan_applied_portfolio_value": 58_451,
            "investment_plan_applied_source": "long_term",
        }
        ctx = dict(ss)
        ctx["applied_plan_portfolio_value"] = 58_451
        ctx["sidebar_portfolio_value"] = 58_451
        response = run_decision_support_module(
            MODULE_ALLOCATION_ADVISOR,
            ctx,
            question="Is the amount I currently have invested appropriate?",
        )
        sections = render_user_analyst_sections(response)
        facts = sections.get("key_variables") or ""
        self.assertIn("Portfolio value: $58,451", facts)
        self.assertNotIn("Portfolio value: $100,000", facts)


if __name__ == "__main__":
    unittest.main()
