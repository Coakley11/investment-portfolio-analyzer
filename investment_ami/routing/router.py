"""Route free-text questions to catalog entries (legacy phrase routing)."""

from __future__ import annotations

from typing import Any

from investment_ami.catalog.registry import question_for_intent
from investment_ami.models.routing import RoutedQuestion


def route_instant_question(
    question: str,
    context: dict[str, Any] | None = None,
) -> RoutedQuestion | None:
    q = str(question or "").strip()
    if not q:
        return None
    ctx = dict(context or {})
    try:
        from investment_ami_context import detect_investment_send_intent, intent_supported
    except ImportError:
        return None

    page = str(ctx.get("page") or ctx.get("source_page") or "").strip()
    intent = detect_investment_send_intent(q, page)
    if not intent_supported(intent):
        return None
    definition = question_for_intent(intent)
    if definition is None:
        return None
    return RoutedQuestion(
        intent_id=intent,
        definition=definition,
        question_text=q,
        source_page=page,
    )
