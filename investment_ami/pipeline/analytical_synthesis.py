"""Phase 4 — analytical synthesis (LLM) from PortfolioAnalysisBrief."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from investment_ami.engines.support.portfolio_analysis_brief import build_portfolio_analysis_brief
from investment_ami.integration.llm_client import ChatCompletionResult, LlmClientError, chat_completion_json
from investment_ami.integration.synthesis_config import SynthesisConfig, analytical_synthesis_config
from investment_ami.pipeline.analytical_placeholder import solve_analytical_synthesis_placeholder
from investment_ami.pipeline.synthesis_prompts import (
    SYNTHESIS_PROMPT_VERSION,
    build_synthesis_input,
    build_system_prompt,
    build_user_prompt,
)
from investment_ami.pipeline.synthesis_validation import validate_synthesis_grounding
from investment_ami.routing.mode_router import ModeRoutingDecision


@dataclass
class AnalyticalSynthesisDiagnostics:
    """Developer-facing trace for prompt iteration."""

    prompt_version: str = SYNTHESIS_PROMPT_VERSION
    synthesis_enabled: bool = False
    flag_source: str = ""
    model: str = ""
    mock_mode: bool = False
    error: str = ""
    system_prompt: str = ""
    user_prompt: str = ""
    structured_inputs: dict[str, Any] = field(default_factory=dict)
    raw_model_response: str = ""
    raw_api_payload: dict[str, Any] = field(default_factory=dict)
    parsed_response: dict[str, Any] = field(default_factory=dict)
    validated_answer_markdown: str = ""
    grounding: dict[str, Any] = field(default_factory=dict)
    timing_ms: dict[str, float] = field(default_factory=dict)
    token_usage: dict[str, Any] = field(default_factory=dict)
    brief_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _beginner(context: dict[str, Any] | None) -> bool:
    try:
        from investment_ami_context import is_beginner_experience

        return is_beginner_experience(dict(context or {}))
    except ImportError:
        return False


def _parse_model_json(content: str) -> dict[str, Any]:
    text = str(content or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {"answer_markdown": text, "citations": [], "uncertainties": [], "alternative_viewpoints": []}


def _compose_answer_markdown(parsed: dict[str, Any]) -> str:
    """Ensure investment thesis is visible even if model only populated the JSON field."""
    answer = str(parsed.get("answer_markdown") or "").strip()
    thesis = str(parsed.get("investment_thesis") or "").strip()
    if not thesis:
        return answer
    low = answer.lower()
    if "## investment thesis" in low:
        return answer
    block = f"## Investment Thesis\n\n{thesis}\n\n"
    return block + answer if answer else block.strip()


def _apply_grounding_footer(answer: str, grounding: dict[str, Any], limitations: list[str]) -> str:
    parts = [answer.strip()]
    if not grounding.get("ok"):
        invalid = grounding.get("invalid_fact_ids") or []
        if invalid:
            parts.append(
                "\n\n---\n*Grounding note: some citations could not be verified against the facts brief "
                f"({', '.join(sorted(set(invalid))[:6])}). Treat numeric claims with caution.*"
            )
    if limitations:
        parts.append("\n\n**Data limitations:** " + " ".join(limitations[:4]))
    return "\n".join(parts).strip()


def synthesize_with_diagnostics(
    question: str,
    context: dict[str, Any] | None,
    decision: ModeRoutingDecision,
    *,
    config: SynthesisConfig | None = None,
) -> tuple[Any, Any, AnalyticalSynthesisDiagnostics]:
    """Build brief, call LLM when enabled, return solver pair + diagnostics."""
    from investment_ami_instant_solver import InvestmentSolverResult, InvestmentSolverRoute

    cfg = config or analytical_synthesis_config()
    diag = AnalyticalSynthesisDiagnostics(
        synthesis_enabled=cfg.enabled,
        flag_source=cfg.flag_source,
        model=cfg.model,
        mock_mode=cfg.mock_mode,
    )
    ctx = dict(context or {})
    q = str(question or "").strip()
    t0 = time.perf_counter()

    t_brief = time.perf_counter()
    brief = build_portfolio_analysis_brief(ctx, question=q)
    diag.brief_version = brief.brief_version
    brief_dict = brief.to_dict()
    diag.timing_ms["brief_ms"] = round((time.perf_counter() - t_brief) * 1000, 1)

    synthesis_input = build_synthesis_input(
        question=q,
        brief_dict=brief_dict,
        question_tag=decision.question_tag,
        experience_mode=str(ctx.get("experience_mode") or ctx.get("experience") or ""),
        source_page=str(ctx.get("page") or ctx.get("source_page") or ""),
        routing_metadata={
            "matched_rules": list(decision.matched_rules),
            "reasons": list(decision.reasons),
            "legacy_intent_hint": decision.legacy_intent_hint,
        },
    )
    diag.structured_inputs = synthesis_input

    if not cfg.enabled:
        diag.timing_ms["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        diag.error = "Analytical synthesis disabled (set INVESTMENT_AMI_ANALYTICAL_SYNTHESIS=1)."
        route, result = solve_analytical_synthesis_placeholder(q, ctx, decision)
        _attach_brief_and_diag(result, brief_dict, diag)
        return route, result, diag

    beginner = _beginner(ctx)
    system_prompt = build_system_prompt(beginner=beginner)
    user_prompt = build_user_prompt(question=q, synthesis_input=synthesis_input)
    diag.system_prompt = system_prompt
    diag.user_prompt = user_prompt

    t_llm = time.perf_counter()
    try:
        completion: ChatCompletionResult = chat_completion_json(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=cfg.model,
            timeout_sec=cfg.timeout_sec,
            temperature=0.28,
            max_tokens=6000,
        )
    except LlmClientError as exc:
        diag.error = str(exc)
        diag.timing_ms["llm_ms"] = round((time.perf_counter() - t_llm) * 1000, 1)
        diag.timing_ms["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        route, result = solve_analytical_synthesis_placeholder(q, ctx, decision)
        result.short_answer = (
            f"Analytical synthesis could not run: {exc}\n\n"
            "Check OPENAI_API_KEY and INVESTMENT_AMI_ANALYTICAL_SYNTHESIS=1."
        )
        _attach_brief_and_diag(result, brief_dict, diag)
        return route, result, diag

    diag.timing_ms["llm_ms"] = round((time.perf_counter() - t_llm) * 1000, 1)
    diag.raw_model_response = completion.content
    diag.raw_api_payload = {
        "model": completion.model,
        "usage": {
            "prompt_tokens": completion.prompt_tokens,
            "completion_tokens": completion.completion_tokens,
            "total_tokens": completion.total_tokens,
        },
    }
    diag.token_usage = dict(diag.raw_api_payload["usage"])

    parsed = _parse_model_json(completion.content)
    diag.parsed_response = parsed
    answer = _compose_answer_markdown(parsed)
    if not answer:
        answer = "The model returned an empty answer. Please retry or refine your question."

    valid_ids = set(brief.facts.keys())
    t_val = time.perf_counter()
    grounding = validate_synthesis_grounding(parsed, valid_fact_ids=valid_ids, answer_markdown=answer)
    diag.grounding = grounding.to_dict()
    diag.timing_ms["validate_ms"] = round((time.perf_counter() - t_val) * 1000, 1)

    validated = _apply_grounding_footer(answer, diag.grounding, list(brief.limitations))
    diag.validated_answer_markdown = validated

    uncertainties = parsed.get("uncertainties") if isinstance(parsed.get("uncertainties"), list) else []
    alternatives = parsed.get("alternative_viewpoints") if isinstance(parsed.get("alternative_viewpoints"), list) else []
    missing_info = parsed.get("missing_information") if isinstance(parsed.get("missing_information"), list) else []
    report_meta = parsed.get("report_meta") if isinstance(parsed.get("report_meta"), dict) else {}
    priority_recs = (
        parsed.get("priority_recommendations") if isinstance(parsed.get("priority_recommendations"), dict) else {}
    )
    self_critique = str(parsed.get("self_critique") or "").strip()

    result = InvestmentSolverResult(
        short_answer=validated,
        math_idea="Analytical synthesis from PortfolioAnalysisBrief (no recomputation of portfolio math).",
        problem_type="analytical_synthesis",
        model_name=f"Analytical synthesis ({completion.model})",
        variables="question, facts brief, fact_index, limitations",
        assumptions=list(brief.limitations[:6]),
        confidence_pct=None,
        computed={
            "ami_response_mode": "analytical_synthesis",
            "ami_question_tag": decision.question_tag,
            "ami_pipeline_step": "analytical_synthesis",
            "ami_pipeline_profile": "analytical_synthesis",
            "portfolio_analysis_brief_version": brief.brief_version,
            "portfolio_analysis_brief": brief_dict,
            "analytical_synthesis_diagnostics": diag.to_dict(),
        },
        analyst_sections={
            "direct_answer": validated,
            "portfolio_analyst_view": str(report_meta.get("overall_assessment") or "").strip(),
            "portfolio_grade": str(report_meta.get("portfolio_grade") or "").strip(),
            "uncertainties": "\n".join(f"- {u}" for u in uncertainties if str(u).strip()),
            "alternative_viewpoints": "\n".join(f"- {a}" for a in alternatives if str(a).strip()),
            "missing_information": "\n".join(f"- {m}" for m in missing_info if str(m).strip()),
            "priority_recommendations": json.dumps(priority_recs, indent=2) if priority_recs else "",
            "self_critique": self_critique,
            "grounding_summary": json.dumps(diag.grounding, indent=2),
        },
    )
    route = InvestmentSolverRoute(
        problem_type="analytical_synthesis",
        model_name=result.model_name,
        model_rationale=f"Synthesized from facts brief v{brief.brief_version}; tag `{decision.question_tag}`.",
    )
    diag.timing_ms["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return route, result, diag


def solve_analytical_synthesis(
    question: str,
    context: dict[str, Any] | None,
    decision: ModeRoutingDecision,
) -> tuple[Any, Any]:
    route, result, _diag = synthesize_with_diagnostics(question, context, decision)
    return route, result


def solve_analytical_synthesis_with_diagnostics(
    question: str,
    context: dict[str, Any] | None,
    decision: ModeRoutingDecision,
) -> tuple[Any, Any, AnalyticalSynthesisDiagnostics]:
    return synthesize_with_diagnostics(question, context, decision)


def _attach_brief_and_diag(result: Any, brief_dict: dict[str, Any], diag: AnalyticalSynthesisDiagnostics) -> None:
    computed = dict(getattr(result, "computed", None) or {})
    computed["portfolio_analysis_brief"] = brief_dict
    computed["portfolio_analysis_brief_version"] = brief_dict.get("brief_version")
    computed["analytical_synthesis_diagnostics"] = diag.to_dict()
    computed["ami_pipeline_step"] = computed.get("ami_pipeline_step") or "analytical_synthesis"
    try:
        result.computed = computed
    except AttributeError:
        pass
