"""Shared models for decision-support reasoning."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ConfidenceLevel = Literal["high", "medium", "low", "placeholder"]

MODULE_IDS = ("allocation_advisor", "cash_reserve_advisor")


@dataclass
class FinancialSnapshot:
    """Normalized inputs for reasoning rules (from submit context + plan)."""

    question: str = ""
    total_available_cash: float | None = None
    emergency_fund_target: float | None = None
    emergency_fund_actual: float | None = None
    monthly_income: float | None = None
    monthly_expenses: float | None = None
    monthly_contribution: float | None = None
    debt_obligations: float | None = None
    debt_interest_rate_pct: float | None = None
    near_term_cash_needs: float | None = None
    planned_large_expenses: float | None = None
    investable_amount: float | None = None
    long_term_suggested: float | None = None
    horizon_years: int | None = None
    risk_tolerance: str = ""
    portfolio_value: float | None = None
    job_stability: str = ""
    income_predictability: str = ""
    upcoming_major_purchase: str = ""
    question_expense_before: float | None = None
    question_expense_after: float | None = None
    monthly_contribution_known: bool = False
    raw_context_keys: tuple[str, ...] = ()
    limitations: list[str] = field(default_factory=list)

    def to_facts_dict(self) -> dict[str, Any]:
        return {
            k: v
            for k, v in {
                "total_available_cash": self.total_available_cash,
                "emergency_fund_target": self.emergency_fund_target,
                "monthly_income": self.monthly_income,
                "monthly_expenses": self.monthly_expenses,
                "monthly_contribution": self.monthly_contribution,
                "debt_obligations": self.debt_obligations,
                "debt_interest_rate_pct": self.debt_interest_rate_pct,
                "near_term_cash_needs": self.near_term_cash_needs,
                "planned_large_expenses": self.planned_large_expenses,
                "investable_amount": self.investable_amount,
                "long_term_suggested": self.long_term_suggested,
                "horizon_years": self.horizon_years,
                "risk_tolerance": self.risk_tolerance,
                "portfolio_value": self.portfolio_value,
                "job_stability": self.job_stability,
                "income_predictability": self.income_predictability,
            }.items()
            if v is not None and v != ""
        }


@dataclass
class ReasoningFinding:
    rule_id: str
    topic: str
    observation: str
    concern: str = ""
    suggested_action: str = ""
    trade_off: str = ""
    confidence: ConfidenceLevel = "medium"


@dataclass
class DecisionSupportResponse:
    module_id: str
    question: str
    facts: list[str]
    observations: list[str]
    concerns: list[str]
    suggested_actions: list[str]
    trade_offs: list[str]
    confidence: ConfidenceLevel
    limitations: list[str]
    findings: list[ReasoningFinding] = field(default_factory=list)
    applied_rule_ids: tuple[str, ...] = ()
    assessment: str = ""
    information_needed: list[str] = field(default_factory=list)
    confidence_pct: int = 65
    confidence_note: str = ""
    information_needed_markdown: str = ""
    monthly_contribution_recommendation: str = ""
