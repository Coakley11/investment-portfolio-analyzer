"""Monthly Contribution Advisor — structured decision-support reasoning."""

from __future__ import annotations

from dataclasses import dataclass

from investment_ami.decision_support.models import FinancialSnapshot


def _money(x: float) -> str:
    return f"${x:,.0f}"


def _round_contribution(amount: float) -> float:
    if amount <= 0:
        return 0.0
    if amount < 200:
        return float(round(amount / 25) * 25)
    return float(round(amount / 50) * 50)


def monthly_surplus(snapshot: FinancialSnapshot) -> float | None:
    if snapshot.monthly_income is None or snapshot.monthly_expenses is None:
        return None
    return float(snapshot.monthly_income) - float(snapshot.monthly_expenses)


def _surplus_deploy_fraction(snapshot: FinancialSnapshot) -> float:
    job = str(snapshot.job_stability or "").strip().lower()
    if job in ("stable", "very stable", "high", "secure"):
        return 0.85
    if job in ("unstable", "low", "uncertain"):
        return 0.55
    return 0.75


def _portfolio_matches_deployment_target(snapshot: FinancialSnapshot) -> bool:
    pv = snapshot.portfolio_value
    target = snapshot.long_term_suggested
    if pv is None or target is None:
        return False
    target_f = float(target)
    return abs(float(pv) - target_f) <= max(500.0, 0.01 * target_f)


def _long_term_horizon_observation(snapshot: FinancialSnapshot) -> str | None:
    if not snapshot.long_term_suggested or not snapshot.horizon_years:
        return None
    years = snapshot.horizon_years
    target = float(snapshot.long_term_suggested)
    pv = snapshot.portfolio_value
    if pv is not None and _portfolio_matches_deployment_target(snapshot):
        return (
            f"A **{years}-year** investment horizon supports consistent long-term investing. "
            "Even though your current portfolio already matches your entered long-term deployment target, "
            "ongoing monthly contributions can support future portfolio growth and evolving financial goals."
        )
    if pv is not None and target > float(pv) + max(500.0, 0.01 * target):
        gap = target - float(pv)
        return (
            f"A **{years}-year** horizon and long-term deployment target of **{_money(target)}** "
            f"(portfolio **{_money(pv)}**) imply steady contributions can help close a deployment gap "
            f"of about **{_money(gap)}**."
        )
    return (
        f"A **{years}-year** horizon and long-term deployment target of **{_money(target)}** "
        "support steady contributions alongside ongoing wealth accumulation."
    )


def _format_precise_suggested_section(
    snapshot: FinancialSnapshot,
    *,
    surplus: float,
    contrib: float | None,
    recommended: float,
    deploy_cap: float,
    reason: str,
) -> str:
    income = float(snapshot.monthly_income or 0)
    expenses = float(snapshot.monthly_expenses or 0)
    cushion = max(0.0, surplus - recommended)
    lines = [
        f"**Suggested monthly contribution:** **{_money(recommended)}**",
        "",
        f"- Monthly after-tax income: **{_money(income)}**",
        f"- Monthly essential expenses: **{_money(expenses)}**",
        f"- Estimated monthly surplus: **{_money(surplus)}**",
    ]
    if contrib is not None:
        lines.append(f"- Current contribution: **{_money(contrib)}**")
    else:
        lines.append("- Current contribution: **not entered**")
    lines.extend(
        [
            f"- Suggested contribution: **{_money(recommended)}**",
            f"- Remaining monthly cushion: approximately **{_money(cushion)}**",
            f"- Upper contribution guardrail: approximately **{_money(deploy_cap)}**",
            "",
            f"AMI recommends approximately **{_money(recommended)}** per month because it increases "
            f"long-term investing while preserving roughly **{_money(cushion)}** of monthly flexibility "
            "for irregular expenses, changing cash flow, and unexpected costs.",
        ]
    )
    if reason:
        lines.extend(["", f"**Additional context:** {reason}"])
    return "\n".join(lines)


@dataclass(frozen=True)
class MonthlyContributionAdvice:
    assessment: str
    suggested_monthly_section: str
    observations: list[str]
    trade_offs: list[str]
    recommended_amount: float | None
    precise_recommendation: bool
    surplus: float | None


def analyze_monthly_contribution(snapshot: FinancialSnapshot, *, question: str = "") -> MonthlyContributionAdvice:
    q = str(question or "").lower()
    surplus = monthly_surplus(snapshot)
    contrib_known = snapshot.monthly_contribution_known
    contrib = snapshot.monthly_contribution if contrib_known else None

    observations: list[str] = []
    trade_offs: list[str] = [
        "Higher monthly contributions accelerate long-term compounding but reduce cash available for surprises "
        "and near-term spending.",
        "Lower or paused contributions preserve liquidity but slow progress toward long-term deployment targets.",
    ]

    if contrib_known and contrib is not None:
        observations.append(
            f"Your plan records a current monthly investment of **{_money(contrib)}**."
            if contrib > 0
            else "Your plan records a current monthly investment of **$0** (entered explicitly, not a recommendation)."
        )
    else:
        observations.append(
            "Current monthly investment is **unknown** — the optional field on How Much Should I Invest? was left blank."
        )

    if snapshot.monthly_income is None or snapshot.monthly_expenses is None:
        observations.append(
            "Monthly **cash-flow** information is incomplete, so AMI cannot compute a precise monthly surplus yet."
        )
    elif surplus is not None:
        observations.append(
            f"Stated monthly surplus after essential expenses is about **{_money(surplus)}** "
            f"(income **{_money(snapshot.monthly_income)}** minus expenses **{_money(snapshot.monthly_expenses)}**)."
        )

    if snapshot.emergency_fund_target:
        observations.append(
            f"Emergency reserve target in your plan is **{_money(snapshot.emergency_fund_target)}** — "
            "liquidity should stay funded before aggressive contribution increases."
        )
    if snapshot.near_term_cash_needs:
        observations.append(
            f"Near-term cash needs of **{_money(snapshot.near_term_cash_needs)}** argue for caution before "
            "raising monthly investing."
        )
    horizon_obs = _long_term_horizon_observation(snapshot)
    if horizon_obs:
        observations.append(horizon_obs)
    if not snapshot.job_stability:
        observations.append("Job stability was not provided — AMI treats surplus deployment more conservatively.")
    elif str(snapshot.job_stability).lower() in ("unstable", "low", "uncertain"):
        observations.append(
            f"Reported job stability (**{snapshot.job_stability}**) favors preserving cash over maximizing contributions."
        )

    framework_lines = [
        "Until income and expenses are entered, use this framework:",
        "- Estimate **monthly surplus** = after-tax income minus essential expenses.",
        "- Keep **emergency** and **near-term** reserves intact before raising contributions.",
        "- Increase contributions **gradually** as surplus grows (for example in steps every few months).",
    ]

    if surplus is None:
        assessment = (
            "AMI **cannot yet recommend a specific monthly contribution** because monthly after-tax income and/or "
            "essential expenses are missing. You can still use your plan reserves and long-term targets below as guardrails."
        )
        suggested = "\n".join(framework_lines)
        return MonthlyContributionAdvice(
            assessment=assessment,
            suggested_monthly_section=suggested,
            observations=observations,
            trade_offs=trade_offs,
            recommended_amount=None,
            precise_recommendation=False,
            surplus=None,
        )

    deploy_frac = _surplus_deploy_fraction(snapshot)
    deploy_cap = _round_contribution(max(0.0, surplus * deploy_frac))

    if surplus <= 0:
        assessment = (
            "Based on your stated income and expenses, there is **no positive monthly surplus** for new investing. "
            "AMI suggests **$0/month** from paycheck flow until expenses fall or income rises; any investing would "
            "need to come from existing cash within your plan's investable amount."
        )
        suggested = (
            f"**Suggested monthly contribution (from paycheck flow):** **$0**\n\n"
            "Reasoning: essential expenses meet or exceed income in your inputs. "
            "Revisit lump-sum deployment only after rebuilding surplus or using already earmarked investable cash."
        )
        if snapshot.investable_amount and snapshot.investable_amount > 0:
            suggested += (
                f"\n\nYour plan shows about **{_money(snapshot.investable_amount)}** potentially investable after reserves "
                "— that is separate from recurring monthly contributions."
            )
        observations.append("No monthly surplus — preserving liquidity should take priority over higher contributions.")
        return MonthlyContributionAdvice(
            assessment=assessment,
            suggested_monthly_section=suggested,
            observations=observations,
            trade_offs=trade_offs,
            recommended_amount=0.0,
            precise_recommendation=True,
            surplus=surplus,
        )

    recommended: float
    reason: str
    if contrib is None:
        recommended = _round_contribution(min(deploy_cap, max(100.0, surplus * 0.5)))
        reason = (
            f"With about **{_money(surplus)}** monthly surplus, a starting contribution near "
            f"**{_money(recommended)}** balances progress with liquidity (about "
            f"{int(deploy_frac * 100)}% of surplus cap given job stability inputs)."
        )
    elif contrib == 0:
        recommended = _round_contribution(min(deploy_cap, max(100.0, surplus * 0.35)))
        reason = (
            f"You entered **$0/month** today; with **{_money(surplus)}** surplus, consider starting near "
            f"**{_money(recommended)}** if reserves are already funded."
        )
    elif contrib > surplus:
        recommended = _round_contribution(surplus * 0.9)
        reason = (
            f"Your stated contribution **{_money(contrib)}** exceeds surplus **{_money(surplus)}** — "
            f"AMI suggests reducing toward **{_money(recommended)}** to avoid draining cash."
        )
        observations.append("Current contribution appears **above** sustainable monthly surplus.")
    elif contrib < deploy_cap * 0.5:
        recommended = _round_contribution(min(deploy_cap, contrib + surplus * 0.15))
        if recommended <= contrib:
            recommended = _round_contribution(min(deploy_cap, contrib + 50))
        reason = (
            f"Contribution **{_money(contrib)}** is well below surplus capacity; a step toward **{_money(recommended)}** "
            "may be reasonable if reserves stay intact."
        )
        observations.append("There appears **room to increase** contributions without exceeding surplus guardrails.")
    else:
        recommended = _round_contribution(contrib)
        reason = (
            f"Contribution **{_money(contrib)}** is in line with surplus **{_money(surplus)}** and reserve context — "
            "maintaining or nudging toward "
            f"**{_money(deploy_cap)}** (upper guardrail) may be appropriate."
        )
        observations.append("Current contribution appears **broadly aligned** with stated surplus and plan reserves.")

    if "increase" in q and recommended <= (contrib or 0):
        recommended = _round_contribution(min(deploy_cap, (contrib or 0) + surplus * 0.1))
        reason = (
            f"You asked about increasing investing; AMI suggests up to **{_money(recommended)}** while keeping "
            f"roughly **{_money(surplus - recommended)}** of surplus for flexibility."
        )

    assessment = (
        f"Based on your entered cash-flow and plan inputs, AMI suggests targeting about **{_money(recommended)}** "
        f"per month toward investments. {reason}"
    )
    if snapshot.monthly_income is None or snapshot.monthly_expenses is None:
        pass  # unreachable
    elif contrib is not None and contrib > 0 and contrib <= surplus and recommended >= contrib:
        assessment += (
            " This is **moderately confident** for plan consistency; refine as income, expenses, or job stability change."
        )

    suggested = _format_precise_suggested_section(
        snapshot,
        surplus=surplus,
        contrib=contrib,
        recommended=recommended,
        deploy_cap=deploy_cap,
        reason=reason,
    )

    return MonthlyContributionAdvice(
        assessment=assessment,
        suggested_monthly_section=suggested,
        observations=observations,
        trade_offs=trade_offs,
        recommended_amount=recommended,
        precise_recommendation=True,
        surplus=surplus,
    )
