"""Build financial snapshot from AMI submit context."""

from __future__ import annotations

import re
from typing import Any

from investment_ami.decision_support.models import FinancialSnapshot


def _float_or_none(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(str(val).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def _int_or_none(val: Any) -> int | None:
    f = _float_or_none(val)
    if f is None:
        return None
    return int(f)


def _plan_attr(plan: Any, name: str) -> float | None:
    if isinstance(plan, dict):
        return _float_or_none(plan.get(name))
    return _float_or_none(getattr(plan, name, None))


def _parse_expense_shift_from_question(question: str) -> tuple[float | None, float | None]:
    q = str(question or "")
    patterns = (
        r"from\s+\$?\s*([\d,]+(?:\.\d+)?)\s+to\s+\$?\s*([\d,]+(?:\.\d+)?)",
        r"increased\s+from\s+\$?\s*([\d,]+(?:\.\d+)?)\s+to\s+\$?\s*([\d,]+(?:\.\d+)?)",
        r"decreased\s+from\s+\$?\s*([\d,]+(?:\.\d+)?)\s+to\s+\$?\s*([\d,]+(?:\.\d+)?)",
    )
    for pat in patterns:
        m = re.search(pat, q, flags=re.IGNORECASE)
        if m:
            return _float_or_none(m.group(1)), _float_or_none(m.group(2))
    return None, None


def build_financial_snapshot(context: dict[str, Any] | None, *, question: str) -> FinancialSnapshot:
    ctx = dict(context or {})
    limitations: list[str] = []

    total = _float_or_none(ctx.get("plan_total_cash") or ctx.get("total_available_cash"))
    emergency = _float_or_none(ctx.get("plan_emergency") or ctx.get("emergency_fund_needed"))
    near_term = _float_or_none(ctx.get("plan_near_term") or ctx.get("money_needed_1_2_years"))
    debt = _float_or_none(ctx.get("plan_debt") or ctx.get("debt_obligations"))
    expenses = _float_or_none(ctx.get("plan_expenses") or ctx.get("planned_large_expenses"))
    monthly = _float_or_none(ctx.get("plan_monthly") if ctx.get("plan_monthly_provided") else None)
    monthly_known = bool(ctx.get("plan_monthly_provided"))
    horizon = _int_or_none(ctx.get("plan_horizon") or ctx.get("horizon_years"))
    risk = str(ctx.get("plan_risk") or ctx.get("risk_tolerance") or "").strip()
    pv = _float_or_none(ctx.get("applied_plan_portfolio_value"))
    if pv is None:
        pv = _float_or_none(ctx.get("sidebar_portfolio_value") or ctx.get("initial_value"))
    if pv is None:
        pv = _float_or_none(ctx.get("portfolio_value"))

    investable: float | None = None
    long_term: float | None = None
    plan = ctx.get("investment_plan")
    if plan is not None:
        total = total or _plan_attr(plan, "total_available")
        emergency = emergency or _plan_attr(plan, "suggested_emergency_reserve")
        near_term = near_term or _plan_attr(plan, "money_needed_1_2_years")
        debt = debt or _plan_attr(plan, "debt_reserve")
        expenses = expenses or _plan_attr(plan, "planned_large_expenses")
        investable = _plan_attr(plan, "amount_potentially_investable")
        long_term = _plan_attr(plan, "long_term_suggested")
        if monthly is None and monthly_known:
            monthly = _plan_attr(plan, "monthly_contribution")

    if investable is None and total is not None:
        reserved = sum(x or 0 for x in (emergency, near_term, debt, expenses))
        investable = max(0.0, total - reserved)

    income = _float_or_none(ctx.get("monthly_income"))
    monthly_exp = _float_or_none(ctx.get("monthly_expenses"))
    debt_rate = _float_or_none(ctx.get("debt_interest_rate_pct"))

    q_before, q_after = _parse_expense_shift_from_question(question)
    effective_expenses = monthly_exp
    if q_after is not None:
        effective_expenses = q_after
        if monthly_exp is not None and abs(monthly_exp - q_after) > 1:
            limitations.append(
                "Question describes a different monthly expense level than saved plan inputs."
            )

    return FinancialSnapshot(
        question=str(question or "").strip(),
        total_available_cash=total,
        emergency_fund_target=emergency,
        emergency_fund_actual=emergency,
        monthly_income=income,
        monthly_expenses=effective_expenses,
        monthly_contribution=monthly if monthly_known else None,
        monthly_contribution_known=monthly_known,
        debt_obligations=debt,
        debt_interest_rate_pct=debt_rate,
        near_term_cash_needs=near_term,
        planned_large_expenses=expenses,
        investable_amount=investable,
        long_term_suggested=long_term,
        horizon_years=horizon,
        risk_tolerance=risk,
        portfolio_value=pv,
        job_stability=str(ctx.get("job_stability") or "").strip(),
        income_predictability=str(ctx.get("income_predictability") or "").strip(),
        upcoming_major_purchase=str(ctx.get("upcoming_major_purchase") or "").strip(),
        question_expense_before=q_before,
        question_expense_after=q_after,
        raw_context_keys=tuple(sorted(k for k in ctx if str(k).startswith("plan_"))),
        limitations=limitations,
    )
