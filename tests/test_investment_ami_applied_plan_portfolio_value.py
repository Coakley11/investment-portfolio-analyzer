"""Widget-safe AMI submit and reboot persistence for applied plan portfolio value."""

from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

import portfolio_core as core

from applied_math_context import build_source_state
from components.investment_planning import PLAN_MONTHLY_PROVIDED_KEY, capture_investment_plan_persist_blob
from components.ui_helpers import PENDING_SIDEBAR_PORTFOLIO_VALUE_KEY, request_sidebar_portfolio_value
from investment_ami.decision_support.modules import MODULE_ALLOCATION_ADVISOR
from investment_ami.decision_support.pipeline import run_decision_support_module
from investment_ami.decision_support.presentation import render_user_analyst_sections
from investment_persistent_state import (
    apply_investment_disk_state,
    build_investment_disk_state,
    global_settings_payload_from_session,
)
from planning_portfolio_value import (
    APPLIED_PLAN_PORTFOLIO_VALUE_KEY,
    effective_planning_portfolio_value_for_ami,
    get_applied_plan_portfolio_value,
    initialize_sidebar_portfolio_value_before_widget,
    mark_sidebar_portfolio_widget_instantiated,
    set_applied_plan_portfolio_value,
    sidebar_portfolio_widget_instantiated,
)
from suite_analytical_question import build_submit_context, execute_investment_ami_submit_pipeline


def _plan(long_term: float = 58_451.0) -> core.InvestmentPlanResult:
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
        if name == "sidebar_portfolio_value" and self.get("_sidebar_portfolio_value_widget_instantiated"):
            raise RuntimeError("StreamlitAPIException: sidebar_portfolio_value widget already instantiated")
        if name != "_sidebar_portfolio_value_widget_instantiated":
            self[name] = value
        else:
            dict.__setitem__(self, name, value)


class _FakeSt:
    def __init__(self) -> None:
        self.session_state = _FakeSessionState()


class TestAppliedPlanPortfolioWidgetAndPersistence(unittest.TestCase):
    def _base_ss(self, *, sidebar: int = 100_000, applied: int | None = None) -> _FakeSessionState:
        ss = _FakeSessionState(
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
                "investment_plan": _plan(applied or 58_451),
                "sidebar_portfolio_value": sidebar,
            }
        )
        if applied is not None:
            set_applied_plan_portfolio_value(ss, applied, source="long_term")
        return ss

    def test_a_no_sidebar_mutation_after_widget_instantiation(self) -> None:
        st = _FakeSt()
        ss = self._base_ss(applied=58_451)
        st.session_state = ss
        mark_sidebar_portfolio_widget_instantiated(ss)
        sidebar_before = ss["sidebar_portfolio_value"]
        with patch("applied_math_return_insight.store_applied_math_insight", return_value="w-1"), patch(
            "suite_analytical_question._upsert_applied_intelligence_resume",
        ):
            ok, err = execute_investment_ami_submit_pipeline(
                st,
                ss,
                question="Is the amount I currently have invested appropriate?",
                source_page="Portfolio Inputs",
                page_suffix="Portfolio_Inputs",
                send_gen=0,
            )
        self.assertTrue(ok, err)
        self.assertEqual(ss["sidebar_portfolio_value"], sidebar_before)
        self.assertEqual(effective_planning_portfolio_value_for_ami(ss), 58_451.0)

    def test_b_apply_pending_before_widget(self) -> None:
        ss = self._base_ss(sidebar=100_000, applied=None)
        set_applied_plan_portfolio_value(ss, 58_451, source="long_term")
        ss[PENDING_SIDEBAR_PORTFOLIO_VALUE_KEY] = 58_451
        self.assertFalse(sidebar_portfolio_widget_instantiated(ss))
        initialize_sidebar_portfolio_value_before_widget(ss)
        self.assertEqual(get_applied_plan_portfolio_value(ss), 58_451)
        self.assertEqual(ss["sidebar_portfolio_value"], 58_451)
        self.assertNotIn(PENDING_SIDEBAR_PORTFOLIO_VALUE_KEY, ss)

    def test_c_reboot_persistence_precedence(self) -> None:
        st = _FakeSt()
        ss = self._base_ss(applied=58_451)
        st.session_state = ss
        disk = build_investment_disk_state(st)
        self.assertEqual(disk.get("applied_plan_portfolio_value"), 58_451)
        self.assertEqual(disk.get("sidebar_portfolio_value"), 58_451)
        disk["sidebar_portfolio_value"] = 100_000
        fresh = _FakeSt()
        fresh.session_state = _FakeSessionState()
        apply_investment_disk_state(fresh, disk)
        fss = fresh.session_state
        self.assertEqual(get_applied_plan_portfolio_value(fss), 58_451)
        initialize_sidebar_portfolio_value_before_widget(fss)
        self.assertEqual(fss["sidebar_portfolio_value"], 58_451)
        fresh2 = _FakeSt()
        fresh2.session_state = copy.deepcopy(fss)
        saved = build_investment_disk_state(fresh2)
        self.assertEqual(saved.get("applied_plan_portfolio_value"), 58_451)
        self.assertEqual(saved.get("sidebar_portfolio_value"), 58_451)
        payload = global_settings_payload_from_session(fss)
        self.assertEqual(payload.get("sidebar_portfolio_value"), 58_451)

    def test_d_full_ami_flow_reads_canonical(self) -> None:
        st = _FakeSt()
        ss = self._base_ss(applied=58_451)
        st.session_state = ss
        initialize_sidebar_portfolio_value_before_widget(ss)
        ctx = build_submit_context("investment", "Portfolio Inputs", ss)
        self.assertEqual(effective_planning_portfolio_value_for_ami(ctx), 58_451.0)
        response = run_decision_support_module(
            MODULE_ALLOCATION_ADVISOR,
            ctx,
            question="Is the amount I currently have invested appropriate?",
        )
        sections = render_user_analyst_sections(response)
        self.assertIn("Portfolio value: $58,451", sections.get("key_variables") or "")
        source_state = build_source_state("Portfolio Inputs", ss)
        self.assertEqual(source_state["filter_params"]["sidebar_portfolio_value"], 58_451)
        plan_blob = capture_investment_plan_persist_blob(ss)
        self.assertEqual(plan_blob.get("applied_plan_portfolio_value"), 58_451)


if __name__ == "__main__":
    unittest.main()
