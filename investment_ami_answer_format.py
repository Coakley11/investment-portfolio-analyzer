"""Structured Investment AMI analyst answer sections (Phase 2)."""

from __future__ import annotations

from typing import Any

SECTION_ORDER: tuple[tuple[str, str], ...] = (
    ("direct_answer", "Direct Answer"),
    ("portfolio_analyst_view", "Portfolio Analyst View"),
    ("key_variables", "Key Variables"),
    ("tradeoffs", "Tradeoffs"),
    ("what_if_scenarios", "What-If Scenarios"),
    ("recommended_actions", "Recommended Actions"),
    ("risk_notes", "Risk Notes"),
)

_BEGINNER_SECTION_ORDER: tuple[tuple[str, str], ...] = (
    ("direct_answer", "Direct Answer"),
    ("portfolio_analyst_view", "What This Means"),
    ("key_variables", "Key Numbers"),
    ("tradeoffs", "Tradeoffs"),
    ("recommended_actions", "What You Could Do"),
    ("risk_notes", "Important Notes"),
)


def build_analyst_sections(
    *,
    direct_answer: str,
    portfolio_analyst_view: str = "",
    key_variables: str = "",
    tradeoffs: str = "",
    what_if_scenarios: str = "",
    recommended_actions: str = "",
    risk_notes: str = "",
    beginner: bool = False,
) -> dict[str, str]:
    """Build non-empty analyst sections dict."""
    raw = {
        "direct_answer": str(direct_answer or "").strip(),
        "portfolio_analyst_view": str(portfolio_analyst_view or "").strip(),
        "key_variables": str(key_variables or "").strip(),
        "tradeoffs": str(tradeoffs or "").strip(),
        "what_if_scenarios": str(what_if_scenarios or "").strip(),
        "recommended_actions": str(recommended_actions or "").strip(),
        "risk_notes": str(risk_notes or "").strip(),
    }
    if beginner:
        raw.pop("what_if_scenarios", None)
    return {k: v for k, v in raw.items() if v}


def render_analyst_sections_markdown(
    sections: dict[str, Any] | None,
    *,
    beginner: bool = False,
) -> str:
    """Render analyst sections as markdown for insight cards / AMI."""
    if not isinstance(sections, dict) or not sections:
        return ""
    order = _BEGINNER_SECTION_ORDER if beginner else SECTION_ORDER
    parts: list[str] = []
    for key, label in order:
        body = str(sections.get(key) or "").strip()
        if body:
            parts.append(f"**{label}**\n\n{body}")
    return "\n\n".join(parts)


def direct_answer_from_sections(sections: dict[str, str]) -> str:
    return str(sections.get("direct_answer") or "").strip()
