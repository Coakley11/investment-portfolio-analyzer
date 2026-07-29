"""Phase 1–3 placeholder for analytical synthesis (no LLM yet)."""

from __future__ import annotations

from typing import Any

from investment_ami.routing.mode_router import ModeRoutingDecision


def solve_analytical_synthesis_placeholder(
    question: str,
    context: dict[str, Any] | None,
    decision: ModeRoutingDecision,
) -> tuple[Any, Any]:
    """
    Return a non-template insight until Phase 4 synthesis is enabled.

    Avoids generic ``portfolio_risk`` / ``investment_coach`` engine output.
    """
    from investment_ami_instant_solver import InvestmentSolverResult, InvestmentSolverRoute

    q = str(question or "").strip()
    tag = str(decision.question_tag or "open_ended").replace("_", " ")
    direct = (
        f"Your question calls for a tailored portfolio analysis ({tag}), not a generic "
        "risk or coaching template. Phase 4 will answer using your portfolio facts brief "
        "and analytical synthesis. Routing is confirmed for this submit."
    )
    result = InvestmentSolverResult(
        short_answer=direct,
        math_idea="Analytical synthesis pipeline (facts brief + question-conditioned reasoning).",
        problem_type="analytical_synthesis",
        model_name="Investment analytical analyst",
        variables="question_tag, response_mode, legacy_intent_hint",
        assumptions=[
            "Instant analytical synthesis is not enabled yet (Phase 4 feature flag).",
            "Portfolio facts brief assembly lands in Phase 2.",
        ],
        confidence_pct=None,
        computed={
            "ami_response_mode": decision.response_mode,
            "ami_question_tag": decision.question_tag,
            "ami_legacy_intent_hint": decision.legacy_intent_hint,
            "ami_routing_diagnostics": {
                "matched_rules": list(decision.matched_rules),
                "reasons": list(decision.reasons),
            },
            "ami_pipeline_step": "analytical_placeholder",
            "ami_pipeline_profile": "analytical_synthesis",
        },
        analyst_sections={
            "direct_answer": direct,
            "question_received": q,
            "routing_summary": "; ".join(decision.reasons) or "analytical_synthesis",
        },
    )
    route = InvestmentSolverRoute(
        problem_type="analytical_synthesis",
        model_name="Investment analytical analyst",
        model_rationale=(
            f"Response mode `{decision.response_mode}` (tag `{decision.question_tag}`); "
            f"legacy hint `{decision.legacy_intent_hint}`."
        ),
    )
    return route, result
