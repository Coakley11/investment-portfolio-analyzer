"""Format decision-support responses for AMI instant answers."""

from __future__ import annotations

from investment_ami.decision_support.models import DecisionSupportResponse

DECISION_SUPPORT_VERSION = "ds-v1"


def format_decision_support_markdown(response: DecisionSupportResponse) -> str:
    title = {
        "allocation_advisor": "Investment Allocation Advisor",
        "cash_reserve_advisor": "Cash Reserve Analysis",
    }.get(response.module_id, "Decision support")

    lines = [
        f"### {title}",
        "",
        f"*Educational guidance — not personal financial advice. (Framework `{DECISION_SUPPORT_VERSION}`)*",
        "",
        "#### Facts from your data",
    ]
    if response.facts:
        lines.extend(f"- {f}" for f in response.facts)
    else:
        lines.append("- _(Add plan inputs in How Much Should I Invest for richer facts.)_")

    lines.append("")
    lines.append("#### AMI observations")
    if response.observations:
        lines.extend(f"- {o}" for o in response.observations)
    else:
        lines.append("- _(No specific observations.)_")

    if response.concerns:
        lines.append("")
        lines.append("#### Possible concerns")
        lines.extend(f"- {c}" for c in response.concerns)

    lines.append("")
    lines.append("#### Suggested actions")
    if response.suggested_actions:
        for i, a in enumerate(response.suggested_actions, 1):
            lines.append(f"{i}. {a}")
    else:
        lines.append("- Refine your question or add financial inputs for targeted guidance.")

    if response.trade_offs:
        lines.append("")
        lines.append("#### Trade-offs")
        lines.extend(f"- {t}" for t in response.trade_offs)

    lines.append("")
    lines.append(f"**Confidence:** {response.confidence} _(placeholder scoring — refine in later phases)_")

    if response.limitations:
        lines.append("")
        lines.append("#### Data limitations")
        lines.extend(f"- {x}" for x in response.limitations)

    return "\n".join(lines)
