"""Response-mode routing: deterministic engines vs analytical synthesis (P4 pipeline)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

ResponseMode = Literal["deterministic", "analytical_synthesis"]

MODE_ROUTER_VERSION = "p5-intent-v1"


@dataclass(frozen=True)
class ModeRoutingDecision:
    """Why a question was routed to deterministic solvers or analytical synthesis."""

    response_mode: ResponseMode
    question_tag: str
    deterministic_intent: str
    legacy_intent_hint: str
    matched_rules: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    router_version: str = MODE_ROUTER_VERSION
    intent_classification: dict[str, Any] = field(default_factory=dict)

    @property
    def effective_intent_id(self) -> str:
        if self.response_mode == "analytical_synthesis":
            return "analytical_synthesis"
        return self.deterministic_intent


def mode_routing_diagnostics_dict(decision: ModeRoutingDecision) -> dict[str, Any]:
    """JSON-friendly routing trace for submit diagnostics and dev panels."""
    return {
        "router_version": decision.router_version,
        "response_mode": decision.response_mode,
        "question_tag": decision.question_tag,
        "effective_intent_id": decision.effective_intent_id,
        "deterministic_intent": decision.deterministic_intent,
        "legacy_intent_hint": decision.legacy_intent_hint,
        "matched_rules": list(decision.matched_rules),
        "reasons": list(decision.reasons),
        "intent_classification": dict(decision.intent_classification or {}),
    }


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _has_portfolio_context(ctx: dict[str, Any] | None) -> bool:
    c = dict(ctx or {})
    weights = c.get("current_weights")
    if isinstance(weights, dict) and any(str(k).strip() for k in weights):
        return True
    holdings = c.get("holdings")
    if isinstance(holdings, list) and any(str(h).strip() for h in holdings):
        return True
    return False


def _match_analytical_tag(q: str) -> tuple[str, str] | None:
    """Return (question_tag, rule_id) when the prompt needs tailored analysis."""
    rules: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "critique",
            (
                "critique my portfolio",
                "critique this portfolio",
                "as an institutional portfolio manager",
                "institutional portfolio manager",
                "investment committee",
                " as a cio",
                "chief investment officer",
            ),
        ),
        (
            "ranked_risks",
            (
                "five biggest risk",
                "five largest risk",
                "top five risk",
                "5 biggest risk",
                "biggest risks facing",
                "largest risks facing",
            ),
        ),
        (
            "devils_advocate",
            (
                "argue against",
                "devil's advocate",
                "devils advocate",
                "make the case against",
                "bear case against",
            ),
        ),
        (
            "peer_compare",
            (
                "compare my portfolio",
                "compare this portfolio",
                "university endowment",
                "endowment portfolio",
                "typical endowment",
            ),
        ),
        (
            "goal_horizon",
            (
                "for retirement",
                "managing this portfolio for retirement",
                "over the next 10 years",
                "next ten years",
                "next 10 years",
            ),
        ),
        (
            "philosophy_lens",
            (
                "ray dalio",
                "all-weather",
                "all weather portfolio",
                "boglehead",
                "bogle head",
                "value investing philosophy",
                "think of this portfolio",
                "think of my portfolio",
            ),
        ),
        (
            "improvement",
            (
                "how would you improve",
                "improve this portfolio",
                "improve my portfolio",
            ),
        ),
        (
            "epistemic",
            (
                "what am i wrong about",
                "what am i missing",
                "hidden risk",
            ),
        ),
    )
    for tag, phrases in rules:
        if any(p in q for p in phrases):
            return tag, f"analytical_phrase:{tag}"
    if re.search(r"\btop\s+\d+\s+risk", q):
        return "ranked_risks", "analytical_phrase:ranked_risks_regex"
    return None


def _portfolio_change_framing(q: str) -> bool:
    return any(
        p in q
        for p in (
            "how should",
            "what should i change",
            "what would you change",
            "how would you change",
            "what changes",
            "what changes would you",
            "changes would you make",
            "should my portfolio",
            "adjust my portfolio",
            "change my portfolio",
            "reposition",
            "recommend",
            "would you make",
        )
    )


def _match_deterministic_objective(q: str) -> tuple[str, str] | None:
    """
    Objective portfolio metric questions — always deterministic even when phrasing is open-ended.
    Returns (intent_id, rule_id).
    """
    rules: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "sector_exposure",
            (
                "percentage of my portfolio is technology",
                "percentage of my portfolio is tech",
                "percent of my portfolio is technology",
                "percent of my portfolio is tech",
                "how much of my portfolio is tech",
                "how much of my portfolio is technology",
                "current sector allocation",
                "sector allocation",
                "what is my sector",
            ),
        ),
        (
            "portfolio_concentration",
            (
                "largest holding",
                "biggest holding",
                "top holding",
                "largest position",
                "biggest position",
            ),
        ),
        (
            "portfolio_risk",
            (
                "expected volatility",
                "portfolio volatility",
                "what is my volatility",
                "sharpe ratio",
                "max drawdown",
            ),
        ),
    )
    for intent, phrases in rules:
        if any(p in q for p in phrases):
            return intent, f"deterministic_objective:{intent}"
    if re.search(r"what\s+percentage\s+of\s+my\s+portfolio", q) and any(
        t in q for t in ("tech", "technology", "sector", "equity", "bond", "fixed")
    ):
        return "sector_exposure", "deterministic_objective:sector_exposure_regex"
    return None


def _match_historical_scenario_analytical(q: str) -> tuple[str, str] | None:
    """
    Multi-period crisis / historical performance questions → analytical synthesis.

    Prevents legacy ``macro_inflation`` (substring match on 'inflation' in 'inflationary')
    from routing to the deterministic inflation engine.
    """
    historical_markers = (
        "2008",
        "financial crisis",
        "global financial crisis",
        "gfc",
        "covid",
        "covid-19",
        "coronavirus",
        "pandemic",
        "march 2020",
        "2020 crash",
        "dot-com",
        "dot com",
        "1970s",
        "stagflation",
        "inflationary period",
        "2022 inflation",
        "historical",
        "would have performed",
        "would have done",
        "how would my portfolio have",
        "how my portfolio would",
    )
    portfolio_markers = (
        "portfolio",
        "holdings",
        "allocation",
        "each environment",
        "primary drivers",
        "performance in each",
        "which holdings",
        "analyze how",
    )
    if not any(h in q for h in historical_markers):
        return None
    if not any(p in q for p in portfolio_markers):
        return None
    period_hits = sum(
        1
        for token in (
            "2008",
            "2020",
            "2022",
            "covid",
            "financial crisis",
            "inflationary",
            "gfc",
        )
        if token in q
    )
    if period_hits >= 2 or "each environment" in q or "primary drivers" in q:
        return "historical_scenario", "analytical_phrase:historical_scenario"
    if "would have performed" in q or "would have done" in q:
        return "historical_scenario", "analytical_phrase:historical_scenario"
    return None


def _conditional_macro_analytical(q: str) -> tuple[str, str] | None:
    try:
        from investment_ami_context import _is_inflation_question, _is_recession_question  # noqa: SLF001
    except ImportError:
        return None
    if _is_inflation_question(q) and _portfolio_change_framing(q):
        return "conditional_macro", "analytical:conditional_inflation"
    if _is_inflation_question(q) and any(
        p in q for p in ("elevated for", "remains elevated", "stay elevated", "stays high")
    ) and any(p in q for p in ("change", "make", "adjust", "recommend")):
        return "conditional_macro", "analytical:conditional_inflation_elevated"
    if _is_recession_question(q) and _portfolio_change_framing(q):
        return "conditional_macro", "analytical:conditional_recession"
    return None


def _is_explicit_portfolio_risk(q: str, source_page: str) -> bool:
    explicit = (
        "biggest risk",
        "biggest portfolio risk",
        "main risk",
        "too risky",
        "portfolio risk",
    )
    if any(p in q for p in explicit):
        if any(p in q for p in ("five biggest", "five largest", "top five", "top 5")):
            return False
        return True
    page = str(source_page or "").strip().lower()
    if "health" in page and re.search(r"\brisk\b", q):
        if any(p in q for p in ("five", "top ", "largest", "biggest risks")):
            return False
        return True
    return False


def _is_definitional_coach(q: str) -> bool:
    if not any(
        p in q
        for p in (
            "what is",
            "what does",
            "what are",
            "explain",
            "teach me",
            "help me understand",
        )
    ):
        return False
    analytical_markers = (
        "my portfolio",
        "this portfolio",
        "institutional",
        "critique",
        "argue",
        "endowment",
        "retirement",
        "improve",
    )
    if any(m in q for m in analytical_markers):
        return False
    return True


def _is_open_ended_allocation(q: str) -> bool:
    if _match_analytical_tag(q):
        return True
    return any(
        p in q
        for p in (
            "over the next",
            "10 years",
            "ten years",
            "retirement",
            "institutional",
            "endowment",
        )
    )


def _strong_deterministic_legacy_intent(legacy: str, q: str, source_page: str) -> bool:
    """Legacy intent from phrase lists (not the portfolio_risk default fallback)."""
    if not legacy or legacy == "portfolio_risk":
        return _is_explicit_portfolio_risk(q, source_page)
    if legacy == "investment_coach":
        return _is_definitional_coach(q)
    if legacy == "allocation_recommendation":
        return not _is_open_ended_allocation(q)
    return True


def _is_starter_insight_question(question: str) -> bool:
    try:
        from investment_ami_context import INVESTMENT_AMI_STARTER_QUESTIONS
    except ImportError:
        return False
    return str(question or "").strip() in INVESTMENT_AMI_STARTER_QUESTIONS


def _resolve_analytical_tag(q: str, intent_suggested: str = "") -> tuple[str, str] | None:
    """Phrase tags + macro conditional + intent-suggested tag."""
    historical = _match_historical_scenario_analytical(q)
    if historical:
        return historical
    tag_match = _match_analytical_tag(q)
    if tag_match:
        return tag_match
    cond = _conditional_macro_analytical(q)
    if cond:
        return cond
    if intent_suggested:
        return intent_suggested, f"intent:suggested_tag:{intent_suggested}"
    return None


def _decision_support_priority_intent(q_normalized: str, legacy_intent: str) -> str | None:
    """Decision-support intents that must not fall through to analytical synthesis."""
    try:
        from investment_ami.decision_support.question_topics import (
            is_invested_amount_question,
            is_monthly_contribution_question,
        )
    except ImportError:
        if legacy_intent in ("allocation_advisor", "cash_reserve_advisor"):
            return legacy_intent
        return None
    if is_monthly_contribution_question(q_normalized):
        return "allocation_advisor"
    if is_invested_amount_question(q_normalized):
        return "allocation_advisor"
    if legacy_intent == "cash_reserve_advisor":
        return "cash_reserve_advisor"
    return None


def _analytical_decision(
    *,
    tag: str,
    rule: str,
    reasons: list[str],
    matched: list[str],
    legacy: str,
    deterministic_intent: str,
    intent_dict: dict[str, Any],
) -> ModeRoutingDecision:
    matched = list(matched)
    matched.append(rule)
    matched.append(f"intent:classifier:{intent_dict.get('primary', 'unknown')}")
    return ModeRoutingDecision(
        response_mode="analytical_synthesis",
        question_tag=tag,
        deterministic_intent=deterministic_intent,
        legacy_intent_hint=legacy,
        matched_rules=tuple(matched),
        reasons=tuple(reasons),
        intent_classification=intent_dict,
    )


def route_investment_response_mode(
    question: str,
    context: dict[str, Any] | None = None,
) -> ModeRoutingDecision:
    """
    Classify instant AMI questions into deterministic calculation vs analytical synthesis.

    Intent classifier (reasoning vs quantitative) runs first; phrase rules refine question_tag.
    """
    q = _normalize(question)
    ctx = dict(context or {})
    page = str(ctx.get("page") or ctx.get("source_page") or "").strip()

    try:
        from investment_ami_context import detect_investment_send_intent
    except ImportError:
        legacy = ""
    else:
        legacy = detect_investment_send_intent(question, page)

    from investment_ami.routing.intent_classifier import classify_routing_intent

    intent = classify_routing_intent(
        question,
        q_normalized=q,
        legacy_intent_hint=legacy,
        has_portfolio_context=_has_portfolio_context(ctx),
    )
    intent_dict = intent.to_dict()

    matched: list[str] = []
    reasons: list[str] = []

    ds_intent = _decision_support_priority_intent(q, legacy)
    if ds_intent:
        matched.append(f"decision_support_priority:{ds_intent}")
        reasons.append(
            "Decision-support question (monthly contribution, invested amount, or cash reserve) "
            f"→ deterministic `{ds_intent}` before analytical synthesis."
        )
        return ModeRoutingDecision(
            response_mode="deterministic",
            question_tag="",
            deterministic_intent=ds_intent,
            legacy_intent_hint=legacy,
            matched_rules=tuple(matched),
            reasons=tuple(reasons),
            intent_classification=intent_dict,
        )

    objective = _match_deterministic_objective(q)
    if objective:
        intent_id, rule = objective
        matched.append(rule)
        reasons.append(f"Objective portfolio metric question → deterministic `{intent_id}`.")
        return ModeRoutingDecision(
            response_mode="deterministic",
            question_tag="",
            deterministic_intent=intent_id,
            legacy_intent_hint=legacy,
            matched_rules=tuple(matched),
            reasons=tuple(reasons),
            intent_classification=intent_dict,
        )

    if _is_starter_insight_question(question):
        matched.append("intent:starter_question_deterministic")
        reasons.append("Known starter insight question → fast deterministic path.")
        intent_id = legacy or "portfolio_risk"
        return ModeRoutingDecision(
            response_mode="deterministic",
            question_tag="",
            deterministic_intent=intent_id,
            legacy_intent_hint=legacy,
            matched_rules=tuple(matched),
            reasons=tuple(reasons),
            intent_classification=intent_dict,
        )

    if intent.prefer_synthesis:
        resolved = _resolve_analytical_tag(q, intent.suggested_question_tag)
        if resolved:
            tag, rule = resolved
            reasons.append(intent.rationale or "Intent classifier prefers analytical synthesis.")
            reasons.append(f"Analytical tag `{tag}`.")
            return _analytical_decision(
                tag=tag,
                rule=rule,
                reasons=reasons,
                matched=matched,
                legacy=legacy,
                deterministic_intent=legacy or "portfolio_risk",
                intent_dict=intent_dict,
            )
        if _has_portfolio_context(ctx):
            matched.append("intent:open_ended_synthesis")
            reasons.append(intent.rationale or "Reasoning intent with portfolio context → synthesis.")
            return _analytical_decision(
                tag=intent.suggested_question_tag or "open_ended",
                rule="intent:reasoning_judgment_default",
                reasons=reasons,
                matched=matched,
                legacy=legacy,
                deterministic_intent=legacy or "portfolio_risk",
                intent_dict=intent_dict,
            )

    historical = _match_historical_scenario_analytical(q)
    if historical:
        tag, rule = historical
        reasons.append(
            "Historical / multi-crisis portfolio performance question → analytical synthesis."
        )
        return _analytical_decision(
            tag=tag,
            rule=rule,
            reasons=reasons,
            matched=matched,
            legacy=legacy,
            deterministic_intent=legacy or "scenario_stress",
            intent_dict=intent_dict,
        )

    tag_match = _match_analytical_tag(q)
    if tag_match:
        tag, rule = tag_match
        reasons.append(f"Matched analytical phrase tag `{tag}`.")
        return _analytical_decision(
            tag=tag,
            rule=rule,
            reasons=reasons,
            matched=matched,
            legacy=legacy,
            deterministic_intent=legacy or "portfolio_risk",
            intent_dict=intent_dict,
        )

    cond = _conditional_macro_analytical(q)
    if cond:
        tag, rule = cond
        reasons.append("Conditional macro/portfolio-change question → analytical synthesis.")
        return _analytical_decision(
            tag=tag,
            rule=rule,
            reasons=reasons,
            matched=matched,
            legacy=legacy,
            deterministic_intent=legacy or "macro_inflation",
            intent_dict=intent_dict,
        )

    if legacy and _strong_deterministic_legacy_intent(legacy, q, page):
        if intent.prefer_synthesis and _has_portfolio_context(ctx):
            reasons.append(
                f"Legacy `{legacy}` would be deterministic, but intent classifier overrides → synthesis."
            )
            return _analytical_decision(
                tag=intent.suggested_question_tag or "open_ended",
                rule="intent:override_legacy_deterministic",
                reasons=reasons,
                matched=matched + [f"deterministic_legacy_blocked:{legacy}"],
                legacy=legacy,
                deterministic_intent=legacy,
                intent_dict=intent_dict,
            )
        matched.append(f"deterministic_legacy:{legacy}")
        reasons.append(f"Legacy intent `{legacy}` is a strong deterministic match.")
        return ModeRoutingDecision(
            response_mode="deterministic",
            question_tag="",
            deterministic_intent=legacy,
            legacy_intent_hint=legacy,
            matched_rules=tuple(matched),
            reasons=tuple(reasons),
            intent_classification=intent_dict,
        )

    if legacy == "investment_coach" and not _is_definitional_coach(q):
        matched.append("escalate:misclassified_coach")
        reasons.append("Question matched coach phrases but is not definitional → analytical.")
        return _analytical_decision(
            tag="open_ended",
            rule="escalate:misclassified_coach",
            reasons=reasons,
            matched=matched,
            legacy=legacy,
            deterministic_intent=legacy,
            intent_dict=intent_dict,
        )

    if legacy == "allocation_recommendation" and _is_open_ended_allocation(q):
        matched.append("escalate:open_ended_allocation")
        reasons.append("Open-ended improvement/allocation question → analytical.")
        return _analytical_decision(
            tag="improvement",
            rule="escalate:open_ended_allocation",
            reasons=reasons,
            matched=matched,
            legacy=legacy,
            deterministic_intent=legacy,
            intent_dict=intent_dict,
        )

    if legacy == "portfolio_risk" or not legacy:
        if _is_explicit_portfolio_risk(q, page):
            matched.append("explicit_portfolio_risk")
            reasons.append("Explicit portfolio risk metric question → deterministic.")
            return ModeRoutingDecision(
                response_mode="deterministic",
                question_tag="",
                deterministic_intent="portfolio_risk",
                legacy_intent_hint=legacy or "portfolio_risk",
                matched_rules=tuple(matched),
                reasons=tuple(reasons),
                intent_classification=intent_dict,
            )
        if _has_portfolio_context(ctx):
            matched.append("default:open_ended_with_portfolio")
            reasons.append("Open-ended question with portfolio context → analytical synthesis.")
            return _analytical_decision(
                tag="open_ended",
                rule="default:open_ended_with_portfolio",
                reasons=reasons,
                matched=matched,
                legacy=legacy,
                deterministic_intent="portfolio_risk",
                intent_dict=intent_dict,
            )

    matched.append(f"deterministic_fallback:{legacy or 'portfolio_risk'}")
    reasons.append("No portfolio context; using deterministic fallback.")
    intent_id = legacy or "portfolio_risk"
    return ModeRoutingDecision(
        response_mode="deterministic",
        question_tag="",
        deterministic_intent=intent_id,
        legacy_intent_hint=legacy,
        matched_rules=tuple(matched),
        reasons=tuple(reasons),
        intent_classification=intent_dict,
    )
