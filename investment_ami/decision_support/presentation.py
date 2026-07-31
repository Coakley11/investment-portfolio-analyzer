"""User-facing decision-support copy (assessment, facts, confidence)."""

from __future__ import annotations

from typing import Any

from investment_ami.decision_support.monthly_contribution_advisor import analyze_monthly_contribution
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


def _join_list_with_and(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _deploy_match_tolerance(reference: float) -> float:
    return max(500.0, 0.005 * abs(reference))


def _invested_amount_plan_verdict(
    snapshot: FinancialSnapshot,
) -> tuple[str, str]:
    """Return (category, short_label) for plan-internal consistency."""
    pv = snapshot.portfolio_value
    target = snapshot.long_term_suggested
    investable = snapshot.investable_amount

    if pv is None:
        return (
            "insufficient",
            "Insufficient information to judge consistency with your entered plan (portfolio value missing).",
        )
    if target is None and investable is None:
        return (
            "insufficient",
            "Insufficient information to judge consistency with your entered plan (deployment targets missing).",
        )

    if target is not None:
        tol = _deploy_match_tolerance(target)
        if abs(float(pv) - float(target)) <= tol:
            return (
                "internally_consistent",
                "Internally consistent with the entered plan, but not enough information to judge overall suitability.",
            )
        if pv > float(target) + tol:
            if investable is not None and pv > float(investable) + tol:
                return (
                    "potentially_aggressive",
                    "Potentially too aggressive relative to the entered plan's suggested long-term deployment and investable cash.",
                )
            return (
                "potentially_aggressive",
                "Potentially above the plan's suggested long-term deployment amount — verify whether extra dollars sit in cash outside this portfolio.",
            )
        return (
            "potentially_conservative",
            "Potentially below the plan's suggested long-term deployment — you may be holding more in reserves or undeployed cash than the long-term slice implies.",
        )

    if investable is not None:
        tol = _deploy_match_tolerance(investable)
        if abs(float(pv) - float(investable)) <= tol:
            return (
                "internally_consistent",
                "Roughly aligned with potentially investable cash after reserves, but overall suitability still depends on income, net worth, and goals.",
            )
    return (
        "insufficient",
        "Insufficient information to judge consistency with the entered plan.",
    )


def _invested_amount_assessment(snapshot: FinancialSnapshot) -> str:
    pv = snapshot.portfolio_value
    target = snapshot.long_term_suggested
    investable = snapshot.investable_amount
    emergency = snapshot.emergency_fund_target
    near_term = snapshot.near_term_cash_needs
    debt = snapshot.debt_obligations or 0.0
    horizon = snapshot.horizon_years
    risk = snapshot.risk_tolerance or "not specified"

    category, conclusion_label = _invested_amount_plan_verdict(snapshot)

    if pv is None:
        return (
            "AMI cannot judge whether your invested amount is appropriate without a current **portfolio value**. "
            "Set portfolio value in the sidebar or complete your holdings, then re-ask this question."
        )

    opening = (
        "Based on the planning inputs available, your **applied portfolio amount** of "
        f"**{_money(pv)}**"
    )
    if target is not None:
        if abs(float(pv) - float(target)) <= _deploy_match_tolerance(target):
            opening += (
                f" is **consistent** with the app's suggested long-term deployment amount of **{_money(target)}**."
            )
        else:
            opening += (
                f" compares to the app's suggested long-term deployment amount of **{_money(target)}** "
                f"(difference about **{_money(abs(float(pv) - float(target)))}**)."
            )
    elif investable is not None:
        opening += (
            f" compares to about **{_money(investable)}** potentially investable after reserves in your plan."
        )
    else:
        opening += "."

    parts: list[str] = [opening]

    reserve_bits: list[str] = []
    if emergency:
        reserve_bits.append(f"**{_money(emergency)}** for emergencies")
    if near_term:
        reserve_bits.append(f"**{_money(near_term)}** for near-term needs")
    if debt:
        reserve_bits.append(f"**{_money(debt)}** reserved for debt")
    if reserve_bits:
        parts.append(
            "You have separately reserved "
            + " and ".join(reserve_bits)
            + ", which reduces the risk of having to sell investments for foreseeable expenses."
        )

    if category == "internally_consistent" and horizon:
        parts.append(
            f"On the information currently available, the amount appears **internally consistent** "
            f"with your cash plan, **{horizon}-year** horizon, and **{risk}** risk tolerance."
        )
    elif horizon:
        parts.append(
            f"Given your **{horizon}-year** horizon and **{risk}** risk tolerance, "
            "compare reserves and deployment targets before changing the invested amount."
        )

    parts.append(f"**Conclusion (plan consistency):** {conclusion_label}")

    parts.append(
        "AMI **cannot** determine whether it is appropriate relative to your **full financial situation** "
        "until **monthly income**, **essential expenses**, **job stability**, **total net worth**, and "
        "**outside retirement assets** are included."
    )

    return " ".join(parts)


def build_invested_amount_observations(snapshot: FinancialSnapshot) -> list[str]:
    """Plan-derived observations; never empty when meaningful plan facts exist."""
    facts = snapshot.to_facts_dict()
    if not facts:
        return []

    out: list[str] = []
    pv = snapshot.portfolio_value
    target = snapshot.long_term_suggested
    total = snapshot.total_available_cash
    investable = snapshot.investable_amount
    emergency = snapshot.emergency_fund_target or 0.0
    near_term = snapshot.near_term_cash_needs or 0.0
    debt = snapshot.debt_obligations or 0.0
    expenses = snapshot.planned_large_expenses or 0.0
    horizon = snapshot.horizon_years
    risk = snapshot.risk_tolerance

    if pv is not None and target is not None:
        tol = _deploy_match_tolerance(target)
        if abs(float(pv) - float(target)) <= tol:
            out.append(
                "Applied portfolio value **exactly matches** (within rounding) the recommended long-term deployment amount."
            )
        else:
            out.append(
                f"Applied portfolio value **{_money(pv)}** differs from the recommended long-term amount "
                f"**{_money(target)}** by about **{_money(abs(float(pv) - float(target)))}**."
            )

    if total is not None and target is not None:
        not_long_term = float(total) - float(target)
        if not_long_term > 0:
            out.append(
                f"About **{_money(not_long_term)}** of the original **{_money(total)}** is **not** assigned to long-term deployment."
            )
            earmarked: list[str] = []
            if emergency > 0:
                earmarked.append(f"**{_money(emergency)}** for emergencies")
            if near_term > 0:
                earmarked.append(f"**{_money(near_term)}** for near-term needs")
            if debt > 0:
                earmarked.append(f"**{_money(debt)}** for debt reserves")
            if expenses > 0:
                earmarked.append(f"**{_money(expenses)}** for planned large expenses")
            if earmarked:
                out.append(
                    "Of that protected/non-deployed long-term amount, "
                    + ", ".join(earmarked)
                    + "."
                )
            labeled_reserve = emergency + near_term + debt + expenses
            remainder = not_long_term - labeled_reserve
            if remainder > 500 and investable is not None and target is not None:
                out.append(
                    f"Roughly **{_money(remainder)}** remains outside the long-term deployment slice "
                    "(for example shorter-term investable cash or unallocated liquidity)."
                )

    if total is not None and investable is not None and investable < total - 500:
        out.append(
            "The plan therefore **preserves liquidity** rather than investing all available cash."
        )

    if horizon:
        out.append(
            f"A **{horizon}-year** horizon supports long-term market exposure."
        )
    if risk:
        out.append(
            f"**{risk.title()}** risk tolerance argues against treating all remaining cash as aggressive-growth capital."
        )

    if snapshot.monthly_income is None or snapshot.monthly_expenses is None:
        out.append(
            "The conclusion is **provisional** because monthly cash flow and total net worth are unknown."
        )

    return out


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

    if is_monthly_contribution_question(q):
        items = []
        if snapshot.monthly_income is None:
            items.append("Monthly after-tax income")
        if snapshot.monthly_expenses is None and snapshot.question_expense_after is None:
            items.append("Monthly essential expenses")
        if not snapshot.monthly_contribution_known:
            items.append("Current monthly contribution (optional field on How Much Should I Invest?)")
        if not snapshot.job_stability:
            items.append("Job or income stability")
        items.extend(
            [
                "Employer retirement match (if any)",
                "Retirement and other long-term goals",
                "Expected large future expenses",
                "Debt or obligations set aside in your plan",
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


def _monthly_contribution_assessment(snapshot: FinancialSnapshot, question: str) -> str:
    return analyze_monthly_contribution(snapshot, question=question).assessment


def build_assessment(
    *,
    question: str,
    snapshot: FinancialSnapshot,
    findings: list[ReasoningFinding],
) -> str:
    q = question.lower()
    if is_monthly_contribution_question(q):
        return _monthly_contribution_assessment(snapshot, question)
    if is_invested_amount_question(q):
        return _invested_amount_assessment(snapshot)
    if "investing enough" in q and "invested" not in q:
        return _monthly_contribution_assessment(snapshot, question)
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
    *,
    question: str = "",
) -> tuple[str, int, str]:
    q = question.lower()
    if is_monthly_contribution_question(q):
        return _resolve_confidence_monthly_contribution(snapshot, information_needed)
    if is_invested_amount_question(q):
        return _resolve_confidence_invested_amount(snapshot, information_needed)
    missing = len(information_needed)
    if missing >= 4:
        return "low", 55, _confidence_rationale(snapshot, information_needed)
    if missing >= 2:
        return "medium", 65, _confidence_rationale(snapshot, information_needed)
    if missing == 1:
        return "medium", 72, _confidence_rationale(snapshot, information_needed)
    return "medium", 78, "Key plan inputs and cash-flow fields are available."


def _resolve_confidence_invested_amount(
    snapshot: FinancialSnapshot,
    information_needed: list[str],
) -> tuple[str, int, str]:
    has_plan = bool(snapshot.portfolio_value is not None and snapshot.to_facts_dict())
    life_gaps = sum(
        1
        for flag in (
            snapshot.monthly_income is None,
            snapshot.monthly_expenses is None,
            not snapshot.job_stability,
        )
        if flag
    )
    pct = 65 if has_plan else 50
    note_parts = [
        "Confidence is **moderate** regarding consistency with the **entered plan** "
        f"(about **{pct}%**) when portfolio value and deployment targets are present."
    ]
    if life_gaps >= 2:
        note_parts.append(
            "Confidence is **low** regarding suitability relative to your **complete financial life** "
            "because income, expenses, and/or job stability are still missing."
        )
    elif information_needed:
        note_parts.append(
            "Confidence is **low** for overall suitability until net worth, outside retirement assets, "
            "and monthly cash flow are included."
        )
    return "medium", pct, " ".join(note_parts)


def _monthly_contribution_optional_refinements(
    snapshot: FinancialSnapshot,
    information_needed: list[str],
) -> list[str]:
    labels: list[str] = []
    if not snapshot.job_stability and any("job" in item.lower() for item in information_needed):
        labels.append("job stability")
    if any("employer" in item.lower() for item in information_needed):
        labels.append("employer match")
    if any("retirement" in item.lower() and "goal" in item.lower() for item in information_needed):
        labels.append("retirement goals")
    return labels


def _resolve_confidence_monthly_contribution(
    snapshot: FinancialSnapshot,
    information_needed: list[str],
) -> tuple[str, int, str]:
    has_plan = bool(snapshot.to_facts_dict())
    has_cashflow = snapshot.monthly_income is not None and snapshot.monthly_expenses is not None
    pct = 68 if has_cashflow and has_plan else (62 if has_plan else 50)
    parts = [
        "Confidence is **moderate** regarding alignment with your **entered plan** "
        f"(about **{pct if has_plan else 50}%**)."
    ]
    if not has_cashflow:
        parts.append(
            "Confidence is **low** regarding the **exact recommended monthly contribution** until "
            "monthly after-tax income and essential expenses are available."
        )
    elif information_needed:
        optional = _monthly_contribution_optional_refinements(snapshot, information_needed)
        if optional:
            parts.append(
                "Confidence may increase after " + _join_list_with_and(optional) + " are included."
            )
    return "medium", pct, " ".join(parts)


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
    q = (snapshot.question or "").lower()
    missing_cashflow = snapshot.monthly_income is None or (
        snapshot.monthly_expenses is None and snapshot.question_expense_after is None
    )
    if missing_cashflow:
        steps.append(
            "Enter **monthly income** and **monthly essential expenses** on "
            "**How Much Should I Invest?** AMI will then estimate your monthly surplus, "
            "compare it to your contribution, and check whether investing more would "
            "pull emergency reserves below your target."
        )
    elif is_monthly_contribution_question(q):
        steps.extend(
            [
                "Review whether the recommended monthly contribution is comfortable over several months.",
                "Increase contributions **gradually** if your remaining monthly cushion proves sustainable.",
                "Revisit the recommendation after major income or expense changes.",
            ]
        )
    elif information_needed:
        steps.append(
            "Add the missing plan or cash-flow inputs listed under **Information Needed**, "
            "then re-ask this question for a sharper answer."
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
    confidence_label, confidence_pct, confidence_note = resolve_confidence(
        snapshot, information_needed, question=question
    )
    observations = build_observations(findings)
    monthly_section = ""
    if is_monthly_contribution_question(question):
        advice = analyze_monthly_contribution(snapshot, question=question)
        if advice.observations:
            observations = advice.observations
        if advice.trade_offs:
            trade_offs = advice.trade_offs
        else:
            trade_offs = build_trade_offs(findings)
        monthly_section = advice.suggested_monthly_section
    elif is_invested_amount_question(question):
        plan_obs = build_invested_amount_observations(snapshot)
        if plan_obs:
            observations = plan_obs
        trade_offs = build_trade_offs(findings)
    else:
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
        monthly_contribution_recommendation=monthly_section,
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
        "monthly_contribution_recommendation": response.monthly_contribution_recommendation,
        "recommended_actions": response.suggested_actions[0] if response.suggested_actions else "",
        "tradeoffs": "\n".join(f"- {t}" for t in response.trade_offs) if response.trade_offs else "",
        "risk_notes": response.information_needed_markdown,
        "methodology": confidence_body,
        "assumptions": disclaimer,
        "decision_support_nav": "investment_plan",
    }
    return {k: v for k, v in sections.items() if v}
