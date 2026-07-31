"""User-facing decision-support copy (assessment, facts, confidence)."""

from __future__ import annotations

from investment_ami.decision_support.question_topics import is_invested_amount_question, is_monthly_contribution_question

from investment_ami.decision_support.models import DecisionSupportResponse, FinancialSnapshot, ReasoningFinding

_FACT_LABELS: dict[str, str] = {
    "total_available_cash": "Total available cash",
    "emergency_fund_target": "Emergency fund target",
    "monthly_income": "Monthly income",
    "monthly_expenses": "Monthly expenses",
    "monthly_contribution": "Current monthly investment (optional)",
    "debt_obligations": "Debt or obligations reserve",
    "debt_interest_rate_pct": "Debt interest rate",
    "near_term_cash_needs": "Near-term cash needs (1–2 years)",
    "planned_large_expenses": "Planned large expenses",
    "investable_amount": "Potentially investable amount",
    "long_term_suggested": "Recommended long-term amount",
    "horizon_years": "Investment time horizon (years)",
    "risk_tolerance": "Risk tolerance",
    "portfolio_value": "Portfolio value",
    "job_stability": "Job stability",
    "income_predictability": "Income predictability",
}


def _money(x: float) -> str:
    return f"${x:,.0f}"


def _format_fact_line(key: str, value: Any) -> str:
    label = _FACT_LABELS.get(key, key.replace("_", " ").title())
    if isinstance(value, (int, float)) and key == "debt_interest_rate_pct":
        return f"- {label}: {float(value):.1f}%"
    if isinstance(value, (int, float)) and key == "horizon_years":
        return f"- {label}: {int(value)}"
    if isinstance(value, (int, float)):
        return f"- {label}: {_money(float(value))}"
    return f"- {label}: {value}"


def build_facts_used(snapshot: FinancialSnapshot) -> list[str]:
    lines: list[str] = []
    for key, value in snapshot.to_facts_dict().items():
        if key == "monthly_contribution" and snapshot.monthly_contribution_known and value == 0:
            lines.append("- Current monthly investment: $0 (entered in your plan — not a recommendation)")
            continue
        lines.append(_format_fact_line(key, value))
    return lines


def build_information_needed(snapshot: FinancialSnapshot, question: str) -> list[str]:
    q = question.lower()
    if is_invested_amount_question(q):
        items: list[str] = []
        if snapshot.portfolio_value is None:
            items.append("Current portfolio value (sidebar portfolio value or holdings)")
        if snapshot.long_term_suggested is None and snapshot.investable_amount is None:
            items.append("How Much Should I Invest plan (investable and long-term suggested amounts)")
        if snapshot.total_available_cash is None:
            items.append("Total available cash from your plan")
        if not snapshot.risk_tolerance:
            items.append("Risk tolerance from your plan")
        if snapshot.horizon_years is None:
            items.append("Investment time horizon from your plan")
        items.extend(
            [
                "Whether available cash is included in or separate from the portfolio value you entered",
                "Total net worth across accounts (not just this portfolio)",
                "Monthly income and essential expenses",
                "Retirement and other long-term assets outside this portfolio",
                "Upcoming liabilities and large purchases",
                "Target split between invested assets and liquid cash",
            ]
        )
        return items

    items = []
    if snapshot.monthly_income is None:
        items.append("Monthly after-tax income")
    if snapshot.monthly_expenses is None and snapshot.question_expense_after is None:
        items.append("Monthly essential expenses")
    if not snapshot.monthly_contribution_known and is_monthly_contribution_question(q):
        items.append("Current monthly investment (optional field on How Much Should I Invest?)")
    if not snapshot.job_stability:
        items.append("Job or income stability")
    if "invest enough" in q or "contribut" in q:
        if snapshot.debt_obligations is None:
            items.append("Debt or obligations set aside in your plan")
    if "debt" in q and snapshot.debt_interest_rate_pct is None and snapshot.debt_obligations:
        items.append("Interest rates on outstanding debt")
    if not items:
        return []
    return items


def _investing_enough_assessment(snapshot: FinancialSnapshot) -> str:
    if snapshot.monthly_contribution_known and snapshot.monthly_contribution == 0:
        contrib = "Your current stated monthly investment is **$0**."
    elif snapshot.monthly_contribution is not None and snapshot.monthly_contribution > 0:
        contrib = f"Your stated current monthly investment is **{_money(snapshot.monthly_contribution)}**."
    elif not snapshot.monthly_contribution_known:
        contrib = "Your current monthly investment was left blank (unknown)."
    else:
        contrib = "Your current monthly investment could not be read from your plan."

    missing_income_exp = snapshot.monthly_income is None and snapshot.monthly_expenses is None
    if missing_income_exp:
        base = (
            "AMI cannot yet determine whether you are investing enough because "
            f"{contrib.rstrip('.').lower()} and monthly income and expenses are not available."
        )
    elif snapshot.monthly_income is None or snapshot.monthly_expenses is None:
        base = (
            f"{contrib} Without both monthly income and expenses, AMI cannot compare your contribution "
            "to your monthly surplus."
        )
    else:
        surplus = snapshot.monthly_income - snapshot.monthly_expenses
        if surplus <= 0:
            base = (
                f"{contrib} Your stated income and expenses show no positive monthly surplus, "
                "so additional investing may need to come from existing cash rather than paycheck flow."
            )
        elif snapshot.monthly_contribution is not None and snapshot.monthly_contribution > surplus:
            base = (
                f"{contrib} That exceeds your stated monthly surplus "
                f"({_money(surplus)}), so it may not be sustainable without drawing down cash."
            )
        elif snapshot.monthly_contribution is not None and snapshot.monthly_contribution == 0:
            base = (
                f"{contrib} You may still deploy lump-sum cash up to your "
                f"potentially investable amount"
                + (f" (**{_money(snapshot.investable_amount)}**)" if snapshot.investable_amount else "")
                + ", but AMI cannot judge monthly pace without a non-zero contribution or income/expense data."
            )
        else:
            base = (
                f"{contrib} Based on your stated surplus ({_money(surplus)}), "
                "your contribution appears sustainable relative to income and expenses, "
                "subject to emergency fund and near-term cash needs."
            )
    if snapshot.investable_amount is not None and snapshot.investable_amount > 0:
        base += (
            f" Your plan shows about **{_money(snapshot.investable_amount)}** potentially investable "
            "after reserves."
        )
    return base


def _invested_amount_assessment(snapshot: FinancialSnapshot) -> str:
    pv = snapshot.portfolio_value
    target = snapshot.long_term_suggested
    investable = snapshot.investable_amount

    if pv is None:
        return (
            "AMI cannot judge whether your **invested amount** is appropriate without a "
            "current **portfolio value**. Set portfolio value in the sidebar or complete your holdings."
        )

    parts: list[str] = [
        f"Your current portfolio is approximately **{_money(pv)}**.",
    ]
    if investable is not None:
        parts.append(
            f"Potentially investable cash after reserves (from your plan): **{_money(investable)}**."
        )
    if target is not None:
        parts.append(
            f"Separately, based on the cash-planning inputs you entered, about **{_money(target)}** "
            "of your available cash could be allocated toward long-term investing after preserving "
            "emergency and near-term reserves."
        )
        diff = abs(float(pv) - float(target))
        parts.append(
            f"The difference between current portfolio value and suggested long-term deployment "
            f"from available cash is **{_money(diff)}**."
        )
        parts.append(
            "These figures are **not direct substitutes**, so AMI cannot conclude that you are "
            "overinvested merely because portfolio value exceeds the suggested long-term deployment amount."
        )
    elif investable is not None:
        parts.append(
            "Without a long-term deployment target from your plan, AMI can only compare portfolio value "
            "to investable cash after reserves — not whether the invested total is appropriate on its own."
        )

    return " ".join(parts)


def build_assessment(
    *,
    question: str,
    snapshot: FinancialSnapshot,
    findings: list[ReasoningFinding],
) -> str:
    q = question.lower()
    if is_invested_amount_question(q):
        return _invested_amount_assessment(snapshot)
    if is_monthly_contribution_question(q) or ("investing enough" in q and "invested" not in q):
        return _investing_enough_assessment(snapshot)
    if "lost my job" in q or "lose my job" in q:
        for f in findings:
            if f.rule_id == "cash_job_loss":
                return f.suggested_action or f.observation
    if snapshot.question_expense_before and snapshot.question_expense_after:
        return (
            f"Your question describes monthly expenses changing from "
            f"**{_money(snapshot.question_expense_before)}** to "
            f"**{_money(snapshot.question_expense_after)}** — "
            "reserve targets and new investing should be re-sized to the higher level first."
        )
    if findings:
        first = findings[0]
        if first.rule_id == "alloc_baseline_context" and len(findings) > 1:
            first = findings[1]
        if first.observation and first.rule_id != "alloc_baseline_context":
            sentence = first.observation.strip()
            if sentence:
                return sentence.split(".")[0] + ("." if not sentence.endswith(".") else "")
    if build_facts_used(snapshot):
        if is_invested_amount_question(q):
            return _invested_amount_assessment(snapshot)
        return (
            "AMI reviewed your saved plan inputs below. "
            "Add any missing income and expense details for a sharper answer."
        )
    return (
        "AMI needs a few more financial inputs before it can give a specific recommendation. "
        "See **Information Needed** below."
    )


def resolve_confidence(
    snapshot: FinancialSnapshot,
    information_needed: list[str],
) -> tuple[str, int, str]:
    missing = len(information_needed)
    if missing >= 4:
        return "low", 55, _confidence_rationale(snapshot, information_needed)
    if missing >= 2:
        return "medium", 65, _confidence_rationale(snapshot, information_needed)
    if missing == 1:
        return "medium", 72, _confidence_rationale(snapshot, information_needed)
    return "medium", 78, "Key plan inputs and cash-flow fields are available."


def _confidence_rationale(snapshot: FinancialSnapshot, information_needed: list[str]) -> str:
    parts: list[str] = []
    if snapshot.monthly_income is None:
        parts.append("monthly income")
    if snapshot.monthly_expenses is None and snapshot.question_expense_after is None:
        parts.append("monthly expenses")
    if not snapshot.job_stability:
        parts.append("job stability")
    if not snapshot.monthly_contribution_known:
        parts.append("monthly investment from your plan")
    if not parts and information_needed:
        parts = [information_needed[0].lower()]
    if parts:
        return "Confidence is limited because " + ", ".join(parts) + " " + (
            "was" if len(parts) == 1 else "were"
        ) + " not available."
    return "Confidence reflects the completeness of your saved plan and cash-flow inputs."


def build_suggested_next_steps(
    snapshot: FinancialSnapshot,
    findings: list[ReasoningFinding],
    information_needed: list[str],
) -> str:
    steps: list[str] = []
    if information_needed:
        steps.append(
            "Enter **monthly income** and **monthly essential expenses** on "
            "**How Much Should I Invest?** AMI will then estimate your monthly surplus, "
            "compare it to your contribution, and check whether investing more would "
            "pull emergency reserves below your target."
        )
    for f in findings:
        if f.rule_id == "alloc_baseline_context":
            continue
        if f.suggested_action and f.suggested_action not in steps:
            steps.append(f.suggested_action)
    if not steps:
        steps.append("Review your plan reserves, then adjust monthly contributions or lump-sum investing.")
    return "\n".join(f"{i}. {s}" for i, s in enumerate(steps[:4], 1))


def build_observations(findings: list[ReasoningFinding]) -> list[str]:
    out: list[str] = []
    for f in findings:
        if f.rule_id == "alloc_baseline_context":
            continue
        if f.observation:
            out.append(f.observation)
        if f.concern:
            out.append(f.concern)
    return out


def build_trade_offs(findings: list[ReasoningFinding]) -> list[str]:
    return [f.trade_off for f in findings if f.trade_off and f.rule_id != "alloc_baseline_context"]


def finalize_decision_support_response(
    module_id: str,
    snapshot: FinancialSnapshot,
    question: str,
    findings: list[ReasoningFinding],
) -> DecisionSupportResponse:
    facts = build_facts_used(snapshot)
    information_needed = build_information_needed(snapshot, question)
    assessment = build_assessment(question=question, snapshot=snapshot, findings=findings)
    confidence_label, confidence_pct, confidence_note = resolve_confidence(snapshot, information_needed)
    observations = build_observations(findings)
    trade_offs = build_trade_offs(findings)
    next_steps = build_suggested_next_steps(snapshot, findings, information_needed)

    info_block = ""
    if information_needed:
        info_block = "To refine this answer, add:\n" + "\n".join(f"- {x}" for x in information_needed)

    return DecisionSupportResponse(
        module_id=module_id,
        question=question,
        facts=facts,
        observations=observations,
        concerns=[],
        suggested_actions=[next_steps] if next_steps else [],
        trade_offs=trade_offs,
        confidence=confidence_label,  # type: ignore[arg-type]
        limitations=[confidence_note] if confidence_note else [],
        findings=findings,
        applied_rule_ids=tuple(f.rule_id for f in findings),
        assessment=assessment,
        information_needed=information_needed,
        confidence_pct=confidence_pct,
        confidence_note=confidence_note,
        information_needed_markdown=info_block,
    )


def user_visible_markdown(response: DecisionSupportResponse) -> str:
    """Concatenated user-facing text for tests (no internal tokens)."""
    parts = [
        response.assessment,
        "\n".join(response.facts),
        "\n".join(response.observations),
        "\n".join(response.suggested_actions),
        "\n".join(response.trade_offs),
        response.information_needed_markdown,
        response.confidence_note,
    ]
    return "\n".join(p for p in parts if p)


def render_user_analyst_sections(response: DecisionSupportResponse) -> dict[str, str]:
    disclaimer = (
        "*Educational guidance only — not personal financial advice. "
        "Verify numbers and consult a qualified professional for your situation.*"
    )
    confidence_body = f"**{response.confidence.title()}** — {response.confidence_pct}%\n\n{response.confidence_note}"
    sections: dict[str, str] = {
        "insights_layout": "decision_support",
        "direct_answer": response.assessment,
        "key_variables": "\n".join(response.facts) if response.facts else "- No plan values were available yet.",
        "portfolio_analyst_view": "\n".join(f"- {o}" for o in response.observations)
        if response.observations
        else "- No additional observations.",
        "recommended_actions": response.suggested_actions[0] if response.suggested_actions else "",
        "tradeoffs": "\n".join(f"- {t}" for t in response.trade_offs) if response.trade_offs else "",
        "risk_notes": response.information_needed_markdown,
        "methodology": confidence_body,
        "assumptions": disclaimer,
        "decision_support_nav": "investment_plan",
    }
    return {k: v for k, v in sections.items() if v}
