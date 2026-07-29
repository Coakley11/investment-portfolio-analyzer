"""Map legacy solver output to canonical decision response (identity-safe for P1)."""

from __future__ import annotations

from typing import Any

from investment_ami.models.response import AmiDecisionResponse, EvidenceItem
from investment_ami.models.routing import RoutedQuestion


def solver_result_from_legacy(
    routed: RoutedQuestion | None,
    route: Any,
    result: Any,
) -> AmiDecisionResponse:
    """Build ``AmiDecisionResponse`` from legacy route/result without changing solver text."""
    sections = dict(getattr(result, "analyst_sections", None) or {})
    direct = str(sections.get("direct_answer") or getattr(result, "short_answer", "") or "")
    actions = str(sections.get("recommended_actions") or "")
    response = AmiDecisionResponse(
        executive_summary=direct,
        recommendation=actions or direct,
        confidence_level=getattr(result, "confidence_pct", None),
        supporting_evidence=[
            EvidenceItem(label="key_variables", value=str(sections.get("key_variables") or "")),
        ]
        if sections.get("key_variables")
        else [],
        risks=[str(sections.get("risk_notes") or "")] if sections.get("risk_notes") else [],
        alternative_viewpoints=[str(sections.get("tradeoffs") or "")] if sections.get("tradeoffs") else [],
        portfolio_impact=str(sections.get("portfolio_analyst_view") or ""),
        suggested_next_steps=[actions] if actions else [],
        related_question_ids=list(routed.definition.follow_up_question_ids) if routed else [],
        analyst_sections=sections,
        computed=dict(getattr(result, "computed", None) or {}),
        assumptions=list(getattr(result, "assumptions", None) or []),
        intent_id=routed.intent_id if routed else "",
        pipeline_profile=routed.definition.pipeline_profile if routed else "legacy",
    )
    response.computed.setdefault("problem_type", getattr(route, "problem_type", ""))
    response.computed.setdefault("model_name", getattr(route, "model_name", ""))
    return response


def attach_routing_metadata(
    result: Any,
    routed: RoutedQuestion | None,
) -> Any:
    """Non-destructive metadata for diagnostics / future pipeline (P1 pass-through)."""
    if result is None or routed is None:
        return result
    computed = dict(getattr(result, "computed", None) or {})
    if "ami_intent_id" not in computed:
        computed["ami_intent_id"] = routed.intent_id
    if "ami_pipeline_profile" not in computed:
        computed["ami_pipeline_profile"] = routed.definition.pipeline_profile
    if "ami_catalog_version" not in computed:
        computed["ami_catalog_version"] = "p1-legacy-generated"
    if routed is not None:
        computed.setdefault("ami_response_mode", routed.response_mode)
        if routed.question_tag:
            computed.setdefault("ami_question_tag", routed.question_tag)
        if routed.mode_routing:
            computed.setdefault("ami_mode_routing", dict(routed.mode_routing))
    try:
        result.computed = computed
    except AttributeError:
        pass
    return result
