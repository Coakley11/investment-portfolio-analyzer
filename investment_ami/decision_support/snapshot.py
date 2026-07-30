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
    monthly = _float_or_none(ctx.get("plan_monthly") or ctx.get("monthly_contribution"))
    horizon = _int_or_none(ctx.get("plan_horizon") or ctx.get("horizon_years"))
    risk = str(ctx.get("plan_risk") or ctx.get("risk_tolerance") or "").strip()
    pv = _float_or_none(ctx.get("sidebar_portfolio_value") or ctx.get("initial_value"))

    plan = ctx.get("investment_plan")
    if isinstance(plan, dict):
        total = total or _float_or_none(plan.get("total_available"))
        emergency = emergency or _float_or_none(plan.get("suggested_emergency_reserve"))
        investable = _float_or_none(plan.get("amount_potentially_investable"))
        long_term = _float_or_none(plan.get("long_term_suggested"))
    else:
        investable = None
        long_term = None
        if hasattr(plan, "amount_potentially_investable"):
            investable = _float_or_none(getattr(plan, "amount_potentially_investable", None))
            long_term = _float_or_none(getattr(plan, "long_term_suggested", None))

    if investable is None and total is not None:
        reserved = sum(x or 0 for x in (emergency, near_term, debt, expenses))
        investable = max(0.0, total - reserved)

    income = _float_or_none(ctx.get("monthly_income"))
    monthly_exp = _float_or_none(ctx.get("monthly_expenses"))
    debt_rate = _float_or_none(ctx.get("debt_interest_rate_pct"))

    if income is None:
        limitations.append("Monthly income not provided — contribution guidance uses plan inputs only.")
    if monthly_exp is None:
        limitations.append("Monthly expenses not provided — emergency fund months cannot be estimated precisely.")
    if debt is not None and debt_rate is None:
        limitations.append("Debt amount is set but interest rate is unknown — payoff vs invest trade-offs stay qualitative.")
    if not str(ctx.get("job_stability") or "").strip():
        limitations.append("Job stability not provided — reserve guidance uses general assumptions.")

    q_before, q_after = _parse_expense_shift_from_question(question)
    effective_expenses = monthly_exp
    if q_after is not None:
        effective_expenses = q_after
        if monthly_exp is not None and abs(monthly_exp - q_after) > 1:
            limitations.append(
                "Question describes a different monthly expense level than saved plan inputs — "
                "scenario uses the expense levels stated in your question."
            )

    return FinancialSnapshot(
        question=str(question or "").strip(),
        total_available_cash=total,
        emergency_fund_target=emergency,
        emergency_fund_actual=emergency,
        monthly_income=income,
        monthly_expenses=effective_expenses,
        monthly_contribution=monthly,
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
