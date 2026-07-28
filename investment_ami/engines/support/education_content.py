"""Shared educational copy for investment coach / education engines (wording frozen)."""

from __future__ import annotations

BEGINNER_PORTFOLIO_CONCEPT_BULLETS: tuple[str, ...] = (
    "- **Diversification** = not betting everything on one outcome.",
    "- **Allocation** = how much goes to stocks, bonds, and other assets.",
    "- **Rebalancing** = resetting mix when markets push weights off-plan.",
)

BEGINNER_COACH_TAIL = (
    "Ask a specific question (concentration, tech exposure, rebalance) for a tailored read on your holdings."
)

ADVANCED_COACH_FRAMEWORK_SUFFIX = (
    "Use Portfolio Health metrics, then stress single-factor tilts (tech, top weight, rate sensitivity)."
)


def format_beginner_coach_snapshot(objective_label: str) -> str:
    """Portfolio coaching snapshot — beginner experience mode."""
    obj = str(objective_label or "").strip() or "your goal"
    body = "\n".join(BEGINNER_PORTFOLIO_CONCEPT_BULLETS)
    return f"**Portfolio coaching snapshot** for **{obj}**:\n{body}\n{BEGINNER_COACH_TAIL}"


def format_advanced_coach_snapshot(objective_label: str) -> str:
    """Portfolio coaching snapshot — advanced experience mode."""
    obj = str(objective_label or "").strip() or "your goal"
    return (
        f"Objective **{obj}** — framework: expected return vs volatility vs concentration vs correlation. "
        f"{ADVANCED_COACH_FRAMEWORK_SUFFIX}"
    )
