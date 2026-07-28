"""Phase 3.1 — Macro intelligence brief and reasoning trace."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from investment_ami.engines.support.macro_context import MacroScenarioContext, resolve_macro_scenario_context

BRIEF_VERSION = "3.1.0"

_MACRO_INTENTS = frozenset({"macro_rates", "macro_recession", "macro_inflation"})


@dataclass(frozen=True)
class MacroReasoningTrace:
    economic_regime: str
    regime_rationale: str
    supporting_evidence: tuple[str, ...]
    key_drivers: tuple[str, ...]
    primary_risks: tuple[str, ...]
    opportunities: tuple[str, ...]
    recommendation_drivers: tuple[str, ...]
    final_macro_conclusion: str

    def to_computed_dict(self) -> dict[str, Any]:
        return {
            "economic_regime": self.economic_regime,
            "regime_rationale": self.regime_rationale,
            "supporting_evidence": list(self.supporting_evidence),
            "key_drivers": list(self.key_drivers),
            "primary_risks": list(self.primary_risks),
            "opportunities": list(self.opportunities),
            "recommendation_drivers": list(self.recommendation_drivers),
            "final_macro_conclusion": self.final_macro_conclusion,
        }


@dataclass(frozen=True)
class MacroIntelligenceBrief:
    scenario: MacroScenarioContext
    trace: MacroReasoningTrace
    confidence_pct: int
    channel_ranks: tuple[tuple[str, float], ...]
    assumption_tensions: tuple[str, ...]
    brief_version: str = BRIEF_VERSION


def _inflation_label(ctx: dict[str, Any], params: dict[str, Any]) -> str:
    return str(ctx.get("health_inflation") or params.get("inflation") or "Moderate Inflation").strip()


def _rate_label(rate_env: str) -> str:
    r = rate_env.lower()
    if "high rate" in r:
        return "high"
    if "rising" in r:
        return "rising"
    if "falling" in r:
        return "falling"
    if "stable" in r:
        return "stable"
    return "unknown"


def _inflation_bucket(label: str) -> str:
    t = label.lower()
    if "high" in t:
        return "high"
    if "deflation" in t:
        return "deflation"
    if "low" in t:
        return "low"
    return "moderate"


def _channel_ranks(profile: dict[str, float | int | str]) -> tuple[tuple[str, float], ...]:
    bonds = float(profile.get("bonds") or 0)
    long_bonds = float(profile.get("long_duration_bonds") or 0)
    tech = float(profile.get("tech") or 0)
    qqq_spy = float(profile.get("qqq_spy") or 0)
    reit = float(profile.get("reit") or 0)
    tbills = float(profile.get("tbills") or 0)
    dividend = float(profile.get("dividend") or 0)
    equity = float(profile.get("equity") or 0)
    ranks = [
        ("duration", long_bonds * 2.0 + bonds),
        ("growth_discount", tech + qqq_spy),
        ("reit", reit),
        ("defensive", tbills + dividend),
        ("cyclical_equity", max(0.0, equity - dividend * 0.5)),
    ]
    return tuple(sorted(ranks, key=lambda x: x[1], reverse=True))


def _detect_assumption_tensions(
    scenario: MacroScenarioContext,
    inflation_label: str,
) -> tuple[str, ...]:
    tensions: list[str] = []
    regime = str(scenario.economic_regime or "").strip()
    prob = scenario.recession_probability
    if regime == "Expansion" and prob is not None and prob >= 0.45:
        tensions.append("Expansion regime paired with elevated recession probability — assumptions may conflict.")
    if regime == "Recession" and _rate_label(scenario.rate_environment) == "falling":
        tensions.append("Recession regime with falling-rate setting — mixed cyclical signals.")
    if _inflation_bucket(inflation_label) == "high" and _rate_label(scenario.rate_environment) == "falling":
        tensions.append("High inflation assumption with falling rates — verify macro settings in Portfolio Health.")
    return tuple(tensions)


def _regime_confidence_penalty(scenario: MacroScenarioContext, inflation_label: str) -> bool:
    regime = str(scenario.economic_regime or "").strip().lower()
    rate = _rate_label(scenario.rate_environment)
    if "slowdown" in regime and rate == "stable":
        return True
    if regime == "expansion" and rate == "high":
        return True
    if _inflation_bucket(inflation_label) == "high" and rate == "stable":
        return True
    return False


def _score_regime(
    scenario: MacroScenarioContext,
    inflation_label: str,
) -> tuple[str, str]:
    rate = _rate_label(scenario.rate_environment)
    infl = _inflation_bucket(inflation_label)
    regime = str(scenario.economic_regime or "").strip()
    prob = scenario.recession_probability or 0.0

    if regime == "Credit Crisis":
        return (
            "Crisis / Liquidity stress",
            "Credit stress regimes typically tighten liquidity and punish risk assets together.",
        )
    if regime == "Recession" or prob >= 0.50:
        return (
            "Recession stress",
            "Recession settings emphasize earnings risk and defensive positioning tradeoffs.",
        )
    if infl == "high" and rate in ("rising", "high"):
        return (
            "Stagflation stress",
            "High inflation combined with restrictive rates pressures both bonds and real purchasing power.",
        )
    if rate == "high":
        return (
            "Restrictive",
            "Persistently high rates compress duration assets and growth valuations.",
        )
    if rate == "rising" and infl in ("moderate", "low") and regime in ("Expansion", "Slowdown", ""):
        return (
            "Moderately Restrictive",
            "Rates are elevated while inflation is moderating — a restrictive but stabilizing mix.",
        )
    if rate == "falling":
        return (
            "Supportive / Accommodative",
            "Falling rates generally ease financial conditions for bonds and growth assets.",
        )
    if regime == "AI / Tech Boom":
        return (
            "Late-cycle / Slowing",
            "Tech-led expansion can coexist with late-cycle rate and valuation sensitivity.",
        )
    if prob >= 0.40:
        return (
            "Late-cycle / Slowing",
            "Elevated recession probability suggests late-cycle caution even if growth continues.",
        )
    return (
        "Neutral / Mixed",
        "Macro assumptions imply balanced cross-currents without a single dominant stress theme.",
    )


def _drivers_for_regime(regime_label: str, rate: str, infl: str) -> tuple[str, ...]:
    drivers: list[str] = []
    if rate in ("rising", "high"):
        drivers.append("Elevated interest rates")
    elif rate == "falling":
        drivers.append("Easing interest-rate pressure")
    else:
        drivers.append("Stable rate environment")

    if infl == "high":
        drivers.append("Elevated inflation")
    elif infl == "deflation":
        drivers.append("Deflationary pressure")
    elif infl == "low":
        drivers.append("Low inflation")
    else:
        drivers.append("Inflation moderating")

    if regime_label.startswith("Recession") or regime_label.startswith("Late-cycle"):
        drivers.append("Slower growth expectations")
    elif regime_label == "Supportive / Accommodative":
        drivers.append("Supportive financial conditions")
    else:
        drivers.append("Stable employment backdrop")

    return tuple(drivers[:4])


def _risks_for_regime_and_profile(
    regime_label: str,
    profile: dict[str, float | int | str],
    top_channel: str,
) -> tuple[str, ...]:
    risks: list[str] = []
    if regime_label in ("Moderately Restrictive", "Restrictive", "Stagflation stress"):
        risks.append("Higher borrowing costs")
        risks.append("Slower earnings growth")
    elif regime_label == "Recession stress":
        risks.append("Corporate earnings contraction")
        risks.append("Risk-asset drawdowns")
    elif regime_label == "Crisis / Liquidity stress":
        risks.append("Liquidity-driven selloffs")
        risks.append("Credit spread widening")
    else:
        risks.append("Policy surprise risk")
        risks.append("Volatility spikes")

    bonds = float(profile.get("bonds") or 0)
    long_bonds = float(profile.get("long_duration_bonds") or 0)
    growth = float(profile.get("tech") or 0) + float(profile.get("qqq_spy") or 0)
    if (bonds >= 20 or long_bonds >= 5) and top_channel == "duration":
        risks.append("Long-duration bond sleeve sensitivity")
    if growth >= 20 and top_channel == "growth_discount":
        risks.append("Growth valuation compression")
    return tuple(dict.fromkeys(risks))[:4]


def _opportunities_for_regime_and_profile(
    regime_label: str,
    profile: dict[str, float | int | str],
) -> tuple[str, ...]:
    tbills = float(profile.get("tbills") or 0)
    bonds = float(profile.get("bonds") or 0)
    dividend = float(profile.get("dividend") or 0)
    equity = float(profile.get("equity") or 0)

    opps: list[str] = []
    if regime_label in ("Moderately Restrictive", "Restrictive"):
        if bonds + tbills < 35:
            opps.append("Investment-grade bonds")
            opps.append("High-quality equities")
        else:
            opps.append("Maintain diversified quality exposure")
            opps.append("Monitor duration rather than adding bond risk")
    elif regime_label == "Recession stress":
        if tbills + dividend < 30:
            opps.append("Defensive cash and dividend sleeves")
        opps.append("Broad diversification across fund sleeves")
    elif regime_label == "Supportive / Accommodative":
        opps.append("Balanced growth and income sleeves")
        if equity < 50:
            opps.append("Quality equity participation")
    else:
        opps.append("High-quality equities")
        opps.append("Investment-grade bonds")
    return tuple(dict.fromkeys(opps))[:4]


def _recommendation_drivers(macro_intent: str) -> tuple[str, ...]:
    if macro_intent == "macro_rates":
        return (
            "Monitor bond duration and rate-sensitive sleeves",
            "Stress-test an additional rate-rise scenario",
            "Review growth ETF overlap if discount-rate risk is high",
        )
    if macro_intent == "macro_recession":
        return (
            "Review defensive allocation versus growth tilt",
            "Stress-test a recession scenario on current weights",
            "Trim top-weight concentration if recession risk feels high",
        )
    if macro_intent == "macro_inflation":
        return (
            "Review long-duration bond exposure for real-return risk",
            "Frame decisions in real (inflation-adjusted) terms",
            "Consider cash/T-bill role for near-term flexibility",
        )
    return ("Revisit Portfolio Health macro assumptions",)


def _final_conclusion(regime_label: str, macro_intent: str, top_channel: str) -> str:
    focus = {
        "macro_rates": "interest-rate and duration channels",
        "macro_recession": "earnings and defensive positioning",
        "macro_inflation": "purchasing power and real returns",
    }.get(macro_intent, "macro conditions")
    return (
        f"Overall macro view is **{regime_label}**; for your portfolio the dominant sensitivity is "
        f"**{top_channel.replace('_', ' ')}**, so this answer emphasizes **{focus}**."
    )


def _supporting_evidence(
    scenario: MacroScenarioContext,
    inflation_label: str,
) -> tuple[str, ...]:
    bits: list[str] = []
    if scenario.rate_environment:
        bits.append(f"Rate environment: {scenario.rate_environment}")
    if inflation_label:
        bits.append(f"Inflation setting: {inflation_label}")
    if scenario.economic_regime:
        bits.append(f"Economic regime: {scenario.economic_regime}")
    if scenario.recession_probability is not None:
        bits.append(f"Recession probability: {scenario.recession_probability * 100:.0f}%")
    if scenario.valuation_environment:
        bits.append(f"Valuation environment: {scenario.valuation_environment}")
    return tuple(bits)


def _confidence_pct(
    scenario: MacroScenarioContext,
    tensions: tuple[str, ...],
    regime_penalty: bool,
    macro_fields_complete: bool,
) -> int:
    if not scenario.has_portfolio_weights:
        return 55
    score = 72
    if scenario.has_portfolio_weights:
        score += 8
    if tensions:
        score -= 6
    if regime_penalty:
        score -= 4
    if macro_fields_complete:
        score += 2
    return max(45, min(88, score))


def build_macro_intelligence_brief(
    context: dict[str, Any] | None,
    *,
    macro_intent: str,
    question: str = "",
) -> MacroIntelligenceBrief:
    _ = question
    intent = str(macro_intent or "").strip()
    if intent not in _MACRO_INTENTS:
        raise ValueError(f"unsupported macro_intent: {intent}")

    ctx = dict(context or {})
    scenario = resolve_macro_scenario_context(ctx)
    params = scenario.scenario_params
    inflation_label = _inflation_label(ctx, params)
    profile = scenario.allocation_profile

    regime_label, regime_rationale = _score_regime(scenario, inflation_label)
    channels = _channel_ranks(profile)
    top_channel = channels[0][0] if channels else "cyclical_equity"
    rate_bucket = _rate_label(scenario.rate_environment)
    infl_bucket = _inflation_bucket(inflation_label)

    tensions = _detect_assumption_tensions(scenario, inflation_label)
    regime_penalty = _regime_confidence_penalty(scenario, inflation_label)
    macro_complete = bool(scenario.rate_environment and inflation_label and scenario.economic_regime)

    trace = MacroReasoningTrace(
        economic_regime=regime_label,
        regime_rationale=regime_rationale,
        supporting_evidence=_supporting_evidence(scenario, inflation_label),
        key_drivers=_drivers_for_regime(regime_label, rate_bucket, infl_bucket),
        primary_risks=_risks_for_regime_and_profile(regime_label, profile, top_channel),
        opportunities=_opportunities_for_regime_and_profile(regime_label, profile),
        recommendation_drivers=_recommendation_drivers(intent),
        final_macro_conclusion=_final_conclusion(regime_label, intent, top_channel),
    )

    confidence = _confidence_pct(scenario, tensions, regime_penalty, macro_complete)

    return MacroIntelligenceBrief(
        scenario=scenario,
        trace=trace,
        confidence_pct=confidence,
        channel_ranks=channels,
        assumption_tensions=tensions,
    )


def macro_computed_from_brief(brief: MacroIntelligenceBrief, compact_outlook: str) -> dict[str, Any]:
    return {
        "macro_brief_version": brief.brief_version,
        "macro_outlook_regime": brief.trace.economic_regime,
        "macro_outlook_confidence": brief.confidence_pct,
        "macro_outlook_compact": compact_outlook,
        "macro_reasoning_trace": brief.trace.to_computed_dict(),
    }


MACRO_OUTLOOK_SEPARATOR = "\n\n---\n\n"


def enrich_macro_solver_result(
    result: Any,
    brief: MacroIntelligenceBrief,
    *,
    beginner: bool,
    macro_intent: str = "",
    question: str = "",
) -> Any:
    """Prepend compact Outlook and merge brief metadata into a macro solver result."""
    from investment_ami.engines.support.macro_outlook_render import render_compact_macro_outlook

    compact = render_compact_macro_outlook(
        brief,
        beginner=beginner,
        macro_intent=macro_intent,
        question=question,
    )
    short = str(result.short_answer or "")
    if not short.startswith("**Macro Outlook**"):
        short = compact + MACRO_OUTLOOK_SEPARATOR + short

    computed = dict(getattr(result, "computed", None) or {})
    computed.update(macro_computed_from_brief(brief, compact))

    sections = dict(getattr(result, "analyst_sections", None) or {})

    return result.__class__(
        short_answer=short,
        math_idea=getattr(result, "math_idea", ""),
        problem_type=getattr(result, "problem_type", ""),
        model_name=getattr(result, "model_name", ""),
        variables=getattr(result, "variables", ""),
        assumptions=list(getattr(result, "assumptions", None) or []),
        confidence_pct=brief.confidence_pct,
        computed=computed,
        analyst_sections=sections,
    )
