"""Route free-text questions to catalog entries (legacy phrase routing)."""

from __future__ import annotations

from typing import Any

from investment_ami.catalog.registry import question_for_intent
from investment_ami.models.routing import RoutedQuestion
from investment_ami.routing.mode_router import mode_routing_diagnostics_dict, route_investment_response_mode


def route_instant_question(
    question: str,
    context: dict[str, Any] | None = None,
) -> RoutedQuestion | None:
    q = str(question or "").strip()
    if not q:
        return None
    ctx = dict(context or {})
    try:
        from investment_ami_context import intent_supported
    except ImportError:
        return None

    page = str(ctx.get("page") or ctx.get("source_page") or "").strip()
    mode = route_investment_response_mode(q, ctx)
    intent = mode.effective_intent_id
    if not intent_supported(intent):
        return None
    definition = question_for_intent(intent)
    if definition is None:
        return None
    routing_diag = mode_routing_diagnostics_dict(mode)
    return RoutedQuestion(
        intent_id=intent,
        definition=definition,
        question_text=q,
        source_page=page,
        response_mode=mode.response_mode,
        question_tag=mode.question_tag,
        mode_routing=routing_diag,
    )
