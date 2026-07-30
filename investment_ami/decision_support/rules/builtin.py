"""Register allocation & cash-reserve reasoning rules."""

from __future__ import annotations

from investment_ami.decision_support.models import FinancialSnapshot, ReasoningFinding
from investment_ami.decision_support.modules import MODULE_ALLOCATION_ADVISOR, MODULE_CASH_RESERVE
from investment_ami.decision_support.rules import DecisionRule, GLOBAL_RULE_REGISTRY


def _money(x: float) -> str:
    return f"${x:,.0f}"


class _BaseRule:
    def matches(self, snapshot: FinancialSnapshot, question: str) -> bool:
        q = question.lower()
        return any(p in q for p in self.phrases)

    def analyze(self, snapshot: FinancialSnapshot, question: str) -> ReasoningFinding | None:
        raise NotImplementedError


class MonthlyContributionRule(_BaseRule):
    rule_id = "alloc_monthly_contribution"
    module_id = MODULE_ALLOCATION_ADVISOR
    topics = ("monthly_contribution",)
    phrases = (
        "how much should i invest this month",
        "invest this month",
        "investing enough",
        "increase my monthly",
        "decrease my monthly",
        "monthly contribution",
        "should i increase",
        "should i decrease",
    )

    def analyze(self, snapshot: FinancialSnapshot, question: str) -> ReasoningFinding | None:
        q = question.lower()
        contrib = snapshot.monthly_contribution
        investable = snapshot.investable_amount
        obs = []
        if contrib is not None:
            obs.append(f"Your plan notes about **{_money(contrib)}/month** in contributions.")
        if investable is not None:
            obs.append(f"Maximum investable after reserves is about **{_money(investable)}**.")
        action = "Align monthly investing with what remains after reserves and near-term needs."
        if "increase" in q:
            action = (
                "Consider increasing contributions only if emergency reserves and near-term cash "
                "are already funded and debt costs are manageable."
            )
        elif "decrease" in q or "pause" in q:
            action = (
                "Reducing or pausing contributions can make sense when cash buffers are thin or "
                "high-cost debt should be prioritized."
            )
        return ReasoningFinding(
            rule_id=self.rule_id,
            topic="monthly_contribution",
            observation=" ".join(obs) or "Contribution guidance depends on cash reserves and obligations.",
            concern="Contributing too much while cash is thin can force selling investments at the wrong time.",
            suggested_action=action,
            trade_off="Higher contributions accelerate growth but reduce liquidity for surprises.",
            confidence="medium" if contrib is not None else "placeholder",
        )


class LumpSumVsDcaRule(_BaseRule):
    rule_id = "alloc_lump_sum_dca"
    module_id = MODULE_ALLOCATION_ADVISOR
    topics = ("lump_sum", "dca")
    phrases = (
        "lump sum",
        "dollar-cost average",
        "dollar cost average",
        "dca",
        "invest all at once",
    )

    def analyze(self, snapshot: FinancialSnapshot, question: str) -> ReasoningFinding | None:
        return ReasoningFinding(
            rule_id=self.rule_id,
            topic="lump_sum_vs_dca",
            observation=(
                "Lump-sum investing historically participates in markets sooner; "
                "dollar-cost averaging spreads timing risk across months."
            ),
            concern="Large lump sums can feel stressful if markets drop soon after investing.",
            suggested_action=(
                "If the cash is truly long-term (after reserves), either approach can be reasonable — "
                "DCA is often chosen for behavioral comfort, not because it always maximizes returns."
            ),
            trade_off="Lump sum maximizes time in market; DCA trades some expected return for smoother emotions.",
            confidence="medium",
        )


class DebtBeforeInvestRule(_BaseRule):
    rule_id = "alloc_debt_vs_invest"
    module_id = MODULE_ALLOCATION_ADVISOR
    topics = ("debt",)
    phrases = (
        "pay off debt before",
        "pay down debt",
        "should i pay off",
        "debt before investing",
    )

    def analyze(self, snapshot: FinancialSnapshot, question: str) -> ReasoningFinding | None:
        rate = snapshot.debt_interest_rate_pct
        debt = snapshot.debt_obligations
        obs_parts = []
        if debt:
            obs_parts.append(f"Your plan reserves **{_money(debt)}** for debt obligations.")
        if rate:
            obs_parts.append(f"Stated debt interest is about **{rate:.1f}%**.")
        else:
            obs_parts.append("No debt interest rate was provided — compare payoff vs invest qualitatively.")
        return ReasoningFinding(
            rule_id=self.rule_id,
            topic="debt_priority",
            observation=" ".join(obs_parts),
            concern="Investing while carrying expensive debt can leave you behind on a net basis when rates are high.",
            suggested_action=(
                "Compare debt interest rates to expected long-term investment returns after tax; "
                "many planners prioritize high-rate debt before aggressive investing."
            ),
            trade_off="Aggressive debt payoff improves certainty but delays compounding in markets.",
            confidence="high" if rate and rate >= 6 else ("medium" if debt else "placeholder"),
        )


class StrategyCritiqueRule(_BaseRule):
    rule_id = "alloc_strategy_critique"
    module_id = MODULE_ALLOCATION_ADVISOR
    topics = ("strategy_critique",)
    phrases = (
        "critique my current investment strategy",
        "investment strategy",
        "financial setup",
        "what would you change about my",
        "too aggressively",
        "too conservatively",
        "investing too aggressive",
        "investing too conservative",
    )

    def analyze(self, snapshot: FinancialSnapshot, question: str) -> ReasoningFinding | None:
        risk = snapshot.risk_tolerance or "not specified"
        horizon = snapshot.horizon_years
        h_note = f"{horizon}-year horizon" if horizon else "unspecified horizon"
        return ReasoningFinding(
            rule_id=self.rule_id,
            topic="strategy_fit",
            observation=f"Stated risk tolerance: **{risk}**; {h_note}.",
            concern="Strategy fit depends on whether liquidity, debt, and horizon align with portfolio risk.",
            suggested_action=(
                "Reconcile three layers: (1) cash & debt, (2) portfolio risk, (3) contribution pace. "
                "Adjust the layer that is most out of line with your goals."
            ),
            trade_off="More equity risk may help long horizons but increases drawdowns you must tolerate.",
            confidence="placeholder",
        )


class EmergencyFundSizeRule(_BaseRule):
    rule_id = "cash_emergency_fund_size"
    module_id = MODULE_CASH_RESERVE
    topics = ("emergency_fund",)
    phrases = (
        "emergency fund",
        "emergency fund too small",
        "emergency fund larger than necessary",
        "large enough",
    )

    def analyze(self, snapshot: FinancialSnapshot, question: str) -> ReasoningFinding | None:
        q = question.lower()
        target = snapshot.emergency_fund_target
        exp = snapshot.monthly_expenses
        months = None
        if target and exp and exp > 0:
            months = target / exp
        obs = f"Plan emergency reserve target: **{_money(target)}**." if target else "Emergency fund target not set in plan."
        if months is not None:
            obs += f" That covers about **{months:.1f} months** of stated expenses."
        action = "Many planners use roughly 3–6 months of essential expenses as a starting benchmark."
        if "too small" in q or "large enough" in q:
            action = "If coverage is under ~3 months of expenses, prioritize cash before increasing market risk."
        elif "larger than necessary" in q:
            action = "Excess cash beyond your target can be directed toward long-term investing in stages."
        return ReasoningFinding(
            rule_id=self.rule_id,
            topic="emergency_fund",
            observation=obs,
            concern="Too little cash forces selling investments during income shocks.",
            suggested_action=action,
            trade_off="Extra cash is safe but may trail inflation over long periods.",
            confidence="medium" if months is not None else "placeholder",
        )


class KeepMoreCashRule(_BaseRule):
    rule_id = "cash_keep_more"
    module_id = MODULE_CASH_RESERVE
    topics = ("cash_buffer",)
    phrases = (
        "keep more cash",
        "hold more cash",
        "invest more of my savings",
        "saving too much cash",
        "invest less",
    )

    def analyze(self, snapshot: FinancialSnapshot, question: str) -> ReasoningFinding | None:
        investable = snapshot.investable_amount
        inv_note = f" Plan suggests up to **{_money(investable)}** may be investable after reserves." if investable else ""
        return ReasoningFinding(
            rule_id=self.rule_id,
            topic="cash_vs_invest",
            observation=f"Cash buffers fund emergencies and near-term spending before market investments.{inv_note}",
            concern="Investing cash needed within 1–2 years exposes you to market timing at withdrawal.",
            suggested_action=(
                "Hold additional cash when job stability, expenses, or upcoming purchases increase uncertainty; "
                "invest incremental dollars only above your combined reserve targets."
            ),
            trade_off="More cash reduces stress but may lower long-term expected returns.",
            confidence="medium" if investable is not None else "placeholder",
        )


class JobLossScenarioRule(_BaseRule):
    rule_id = "cash_job_loss"
    module_id = MODULE_CASH_RESERVE
    topics = ("job_loss",)
    phrases = (
        "lost my job",
        "lose my job",
        "lost my job tomorrow",
        "job tomorrow",
        "what if i lost my job",
        "unemployment",
    )

    def analyze(self, snapshot: FinancialSnapshot, question: str) -> ReasoningFinding | None:
        obs = "Job loss increases the value of liquid cash and reduces the case for aggressive new investing."
        exp = snapshot.monthly_expenses
        emergency = snapshot.emergency_fund_target
        if exp and exp > 0:
            six_mo = exp * 6
            obs += (
                f" At **{_money(exp)}/month** expenses, a common 6-month cushion is about **{_money(six_mo)}**."
            )
            if emergency is not None:
                if emergency < six_mo:
                    obs += (
                        f" Your plan emergency target (**{_money(emergency)}**) is below that cushion — "
                        "consider building reserves before resuming contributions."
                    )
                else:
                    obs += f" Your plan emergency target is **{_money(emergency)}**."
        elif emergency is not None:
            obs += f" Your plan emergency reserve target is **{_money(emergency)}** — preserve it before investing."
        return ReasoningFinding(
            rule_id=self.rule_id,
            topic="job_loss",
            observation=obs,
            concern="Without income, withdrawals from volatile assets may coincide with market downturns.",
            suggested_action=(
                "Pause or reduce new investing, preserve emergency reserves, and avoid locking cash in illiquid bets "
                "until income stabilizes."
            ),
            trade_off="Pausing contributions slows compounding but protects liquidity when it matters most.",
            confidence="high" if exp else "medium",
        )


class ExpenseIncomeShiftRule(_BaseRule):
    rule_id = "cash_expense_income_shift"
    module_id = MODULE_CASH_RESERVE
    topics = ("expense_change", "income_change")
    phrases = (
        "expenses increased",
        "expenses decreased",
        "expense increased",
        "expense decreased",
        "income became less predictable",
        "income less predictable",
        "unpredictable income",
        "can i safely invest more",
    )

    def analyze(self, snapshot: FinancialSnapshot, question: str) -> ReasoningFinding | None:
        q = question.lower()
        before = snapshot.question_expense_before
        after = snapshot.question_expense_after
        obs = "Changes in monthly cash flow should flow through to reserve targets before portfolio risk."
        if before is not None and after is not None and after > before:
            delta = after - before
            pct = (delta / before * 100) if before > 0 else 0
            obs = (
                f"You described monthly expenses rising from **{_money(before)}** to **{_money(after)}** "
                f"(+{_money(delta)}/month, about **{pct:.0f}%**)."
            )
            old_ef = before * 6
            new_ef = after * 6
            obs += (
                f" A 6-month emergency benchmark would shift from about **{_money(old_ef)}** "
                f"to **{_money(new_ef)}**."
            )
        elif before is not None and after is not None and after < before:
            obs = (
                f"You described monthly expenses falling from **{_money(before)}** to **{_money(after)}**."
            )

        if "increased" in q or "less predictable" in q or "unpredictable" in q or (
            before is not None and after is not None and after > before
        ):
            action = (
                "Increase cash reserves or reduce new investing until the new expense level is stable — "
                "re-size emergency fund targets to match the higher burn rate."
            )
            trade = "You give up some expected return to absorb budgeting uncertainty."
        else:
            action = "If lower expenses are durable, consider raising monthly investing after confirming emergency fund targets."
            trade = "Higher investing accelerates goals but assumes the expense reduction persists."
        return ReasoningFinding(
            rule_id=self.rule_id,
            topic="cash_flow_change",
            observation=obs,
            concern="Investing based on temporary expense swings can leave you short when patterns revert.",
            suggested_action=action,
            trade_off=trade,
            confidence="medium" if (before and after) or snapshot.monthly_expenses else "placeholder",
        )


class MajorPurchaseRule(_BaseRule):
    rule_id = "cash_major_purchase"
    module_id = MODULE_CASH_RESERVE
    topics = ("major_purchase",)
    phrases = (
        "buy a house",
        "buying a house",
        "large purchase",
        "next year",
        "next 12 months",
    )

    def analyze(self, snapshot: FinancialSnapshot, question: str) -> ReasoningFinding | None:
        near = snapshot.near_term_cash_needs
        planned = snapshot.planned_large_expenses
        note = ""
        if near or planned:
            note = f" Your plan already reserves **{_money((near or 0) + (planned or 0))}** for near-term needs."
        return ReasoningFinding(
            rule_id=self.rule_id,
            topic="major_purchase",
            observation=f"Upcoming large purchases are usually funded from cash, not from equity risk.{note}",
            concern="Market drops near purchase dates can force delaying the goal or selling at a loss.",
            suggested_action=(
                "Shift planned purchase money to stable cash or short-term holdings and reduce new long-term investing "
                "until the purchase is complete."
            ),
            trade_off="Conservative positioning lowers return but increases purchase certainty.",
            confidence="medium",
        )


class BaselineAllocationContextRule:
    rule_id = "alloc_baseline_context"
    module_id = MODULE_ALLOCATION_ADVISOR
    topics = ("baseline",)
    phrases = ()

    def matches(self, snapshot: FinancialSnapshot, question: str) -> bool:
        return True

    def analyze(self, snapshot: FinancialSnapshot, question: str) -> ReasoningFinding | None:
        if snapshot.to_facts_dict():
            return None
        return ReasoningFinding(
            rule_id=self.rule_id,
            topic="baseline",
            observation="Limited plan data was available — add cash, emergency, and horizon inputs for sharper guidance.",
            suggested_action="Complete the How Much Should I Invest inputs, then re-ask this question.",
            confidence="medium",
        )


def register_default_rules() -> None:
    for rule in (
        MonthlyContributionRule(),
        LumpSumVsDcaRule(),
        DebtBeforeInvestRule(),
        StrategyCritiqueRule(),
        BaselineAllocationContextRule(),
        EmergencyFundSizeRule(),
        KeepMoreCashRule(),
        JobLossScenarioRule(),
        ExpenseIncomeShiftRule(),
        MajorPurchaseRule(),
    ):
        GLOBAL_RULE_REGISTRY.register(rule)


register_default_rules()
