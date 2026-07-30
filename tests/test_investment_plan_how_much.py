"""How Much Should I Invest — calculation and portfolio value apply tests."""

from __future__ import annotations

import pytest
import streamlit as st

from components.investment_planning import (
    build_investable_waterfall_markdown,
    holding_dollar_from_weight,
    normalize_compare_amounts,
)
from components.ui_helpers import (
    PENDING_SIDEBAR_PORTFOLIO_VALUE_KEY,
    request_sidebar_portfolio_value,
)
from portfolio_core import compute_investment_plan, investment_plan_long_term_pct


def test_investable_waterfall_example():
    plan = compute_investment_plan(
        total_available=76_000,
        emergency_fund_needed=5_000,
        money_needed_1_2_years=18_000,
        existing_debt_obligations=1_375,
        planned_large_expenses=0,
        horizon_years=15,
        risk_tolerance="Medium",
        monthly_contribution=0,
    )
    assert plan.amount_potentially_investable == 51_625
    md = build_investable_waterfall_markdown(
        total=76_000,
        emergency=5_000,
        near_term=18_000,
        planned_expenses=0,
        debt=1_375,
        investable=plan.amount_potentially_investable,
    )
    assert "$51,625" in md
    assert "$76,000" in md


def test_eighty_five_fifteen_split_rounding():
    long_pct = investment_plan_long_term_pct(horizon_years=15, risk_tolerance="Medium")
    assert abs(long_pct - 0.85) < 1e-9
    plan = compute_investment_plan(
        total_available=76_000,
        emergency_fund_needed=5_000,
        money_needed_1_2_years=18_000,
        existing_debt_obligations=1_375,
        planned_large_expenses=0,
        horizon_years=15,
        risk_tolerance="Medium",
    )
    assert plan.long_term_allocation_pct == 0.85
    assert plan.safer_sleeve_allocation_pct == pytest.approx(0.15)
    assert plan.long_term_suggested == 43_881
    assert plan.short_term_investable == 7_744
    assert plan.long_term_suggested + plan.short_term_investable == round(plan.amount_potentially_investable)


def test_holding_dollar_from_weight_example():
    assert holding_dollar_from_weight(portfolio_value=43_881, weight_pct=60.0) == 26_328.60


def test_request_sidebar_portfolio_value_long_term_force(monkeypatch):
    class _SS(dict):
        def __getattr__(self, name):
            return self[name]

        def __setattr__(self, name, value):
            self[name] = value

    ss = _SS()
    monkeypatch.setattr(st, "session_state", ss)
    request_sidebar_portfolio_value(43_881.25, force=True)
    assert ss[PENDING_SIDEBAR_PORTFOLIO_VALUE_KEY] == 43_881
    assert ss["investment_plan_applied_portfolio_value"] == 43_881


def test_normalize_compare_amounts_dedupes_and_rejects_invalid():
    assert normalize_compare_amounts([50_000, 50_000, -1, 0, "bad", 25_000.4]) == [25_000.4, 50_000]
