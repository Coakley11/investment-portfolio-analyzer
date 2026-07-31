"""Current monthly investment field — label, parsing, and separation from one-time investable cash."""

from __future__ import annotations

from components.investment_planning import (
    CURRENT_MONTHLY_INVESTMENT_HELP,
    CURRENT_MONTHLY_INVESTMENT_LABEL,
    PLAN_MONTHLY_PROVIDED_KEY,
    current_monthly_investment_for_plan,
    format_current_monthly_investment_for_widget,
    parse_current_monthly_investment_input,
)
from investment_ami.decision_support.modules import MODULE_ALLOCATION_ADVISOR
from investment_ami.decision_support.pipeline import run_decision_support_module
from investment_ami.decision_support.snapshot import build_financial_snapshot
from portfolio_core import compute_investment_plan


def test_current_monthly_investment_label_and_help():
    assert CURRENT_MONTHLY_INVESTMENT_LABEL == "Current monthly investment (optional)"
    assert "not the recommended amount" in CURRENT_MONTHLY_INVESTMENT_HELP
    assert "Leave blank if unknown" in CURRENT_MONTHLY_INVESTMENT_HELP
    assert "$0" in CURRENT_MONTHLY_INVESTMENT_HELP


def test_parse_blank_vs_zero():
    assert parse_current_monthly_investment_input("") == (None, False, None)
    assert parse_current_monthly_investment_input("   ") == (None, False, None)
    assert parse_current_monthly_investment_input("0") == (0.0, True, None)
    assert parse_current_monthly_investment_input("$2,500") == (2500.0, True, None)
    assert parse_current_monthly_investment_input("  $ 1,234.56  ") == (1234.56, True, None)


def test_parse_invalid_and_negative():
    bad, provided, err = parse_current_monthly_investment_input("abc")
    assert bad is None and provided is False and err
    neg, provided2, err2 = parse_current_monthly_investment_input("-100")
    assert neg is None and provided2 is False and "negative" in (err2 or "").lower()


def test_session_unknown_vs_explicit_zero():
    class _SS(dict):
        pass

    unknown = _SS()
    assert current_monthly_investment_for_plan(unknown) is None
    assert format_current_monthly_investment_for_widget(unknown) == ""

    explicit_zero = _SS({PLAN_MONTHLY_PROVIDED_KEY: True, "plan_monthly": 0})
    assert current_monthly_investment_for_plan(explicit_zero) == 0.0
    assert format_current_monthly_investment_for_widget(explicit_zero) == "0"


def test_one_time_investable_not_derived_from_monthly():
    kwargs = dict(
        total_available=100_000,
        emergency_fund_needed=20_000,
        money_needed_1_2_years=10_000,
        existing_debt_obligations=5_000,
        planned_large_expenses=0,
        horizon_years=15,
        risk_tolerance="Medium",
    )
    unknown = compute_investment_plan(**kwargs, current_monthly_investment=None)
    zero = compute_investment_plan(**kwargs, current_monthly_investment=0.0)
    high = compute_investment_plan(**kwargs, current_monthly_investment=3_000.0)
    assert unknown.amount_potentially_investable == zero.amount_potentially_investable == high.amount_potentially_investable
    assert unknown.amount_potentially_investable == 65_000
    assert unknown.long_term_suggested == zero.long_term_suggested == high.long_term_suggested
    assert unknown.short_term_investable == zero.short_term_investable == high.short_term_investable
    assert not any("Optional monthly" in line for line in unknown.summary_lines)
    assert any("$0/month" in line for line in zero.summary_lines)
    assert any("3,000" in line for line in high.summary_lines)
    assert any("does not divide available cash by 12" in note for note in unknown.educational_notes)


def test_investing_enough_uses_explicit_zero():
    ctx = {
        "plan_total_cash": 120_000,
        "plan_emergency": 30_000,
        "plan_monthly": 0,
        "plan_monthly_provided": True,
        "monthly_expenses": 5_000,
    }
    response = run_decision_support_module(
        MODULE_ALLOCATION_ADVISOR,
        ctx,
        question="Am I investing enough?",
    )
    assert "$0" in response.assessment


def test_invested_amount_assessment_ignores_unknown_monthly():
    q = "Is the amount I currently have invested appropriate?"
    ctx = {
        "plan_total_cash": 120_000,
        "plan_emergency": 30_000,
        "plan_horizon": 20,
        "plan_risk": "moderate",
        "investment_plan_generated": True,
        "plan_monthly_provided": False,
        "sidebar_portfolio_value": 50_000,
    }
    snap = build_financial_snapshot(ctx, question=q)
    response = run_decision_support_module(MODULE_ALLOCATION_ADVISOR, ctx, question=q)
    lower = response.assessment.lower()
    assert "monthly contribution" not in lower
    assert snap.monthly_contribution is None
    assert snap.monthly_contribution_known is False
    assert "portfolio" in lower
