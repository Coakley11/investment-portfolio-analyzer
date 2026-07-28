"""Phase 3.1 — Macro Outlook rendering (compact + full)."""

from __future__ import annotations

import re

from investment_ami.engines.support.macro_intelligence import MacroIntelligenceBrief


def _rate_bucket(rate_environment: str) -> str:
    r = str(rate_environment or "").strip().lower()
    if "high rate" in r:
        return "high"
    if "rising" in r:
        return "rising"
    if "falling" in r:
        return "falling"
    if "stable" in r:
        return "stable"
    return "unknown"


def _bullet_block(title: str, items: tuple[str, ...]) -> list[str]:
    lines = [title]
    if items:
        lines.extend(f"- {item}" for item in items)
    else:
        lines.append("- —")
    return lines


def hypothetical_scenario_note(
    brief: MacroIntelligenceBrief,
    *,
    macro_intent: str,
    question: str = "",
) -> str:
    """Short UX note when the answer body uses a stress scenario unlike the baseline setting."""
    intent = str(macro_intent or "").strip()
    q = str(question or "").strip().lower()
    baseline_rate = str(brief.scenario.rate_environment or "").strip()
    rate = _rate_bucket(baseline_rate)

    if intent == "macro_rates" and rate in ("stable", "falling"):
        return (
            f"_Your Portfolio Health baseline is **{baseline_rate or 'Stable Rates'}**. "
            "The analysis below applies a **hypothetical interest-rate shock**, not a forecast "
            "that policy or market rates will move on that path from today's setting._"
        )

    if intent == "macro_inflation":
        health_infl = "Moderate Inflation"
        for ev in brief.trace.supporting_evidence:
            if ev.startswith("Inflation setting:"):
                health_infl = ev.split(":", 1)[-1].strip()
                break
        params = brief.scenario.scenario_params
        param_pct = params.get("inflation_pct")
        try:
            param_val = float(param_pct) if param_pct not in (None, "") else None
        except (TypeError, ValueError):
            param_val = None
        q_pct = None
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", q)
        if m and "inflation" in q:
            try:
                q_pct = float(m.group(1))
            except (TypeError, ValueError):
                q_pct = None
        stress_pct = q_pct if q_pct is not None else param_val
        if stress_pct is not None and stress_pct >= 5.0 and "high" not in health_infl.lower():
            return (
                "_The analysis below uses a **hypothetical inflation scenario** "
                f"(~**{stress_pct:g}%**), which may differ from your Portfolio Health "
                f"inflation setting (**{health_infl}**)._"
            )

    if intent == "macro_recession" and str(brief.scenario.economic_regime or "").strip() == "Expansion":
        return (
            "_Your Portfolio Health economic regime is **Expansion**. "
            "The analysis below applies a **hypothetical recession stress scenario**, "
            "not a forecast that a recession has begun._"
        )

    return ""


def render_compact_macro_outlook(
    brief: MacroIntelligenceBrief,
    *,
    beginner: bool,
    macro_intent: str = "",
    question: str = "",
) -> str:
    trace = brief.trace
    if beginner:
        drivers = trace.key_drivers[:2]
        risks = trace.primary_risks[:1]
        opps = trace.opportunities[:1]
    else:
        drivers = trace.key_drivers[:3]
        risks = trace.primary_risks[:2]
        opps = trace.opportunities[:2]

    lines = [
        "**Macro Outlook**",
        f"**Overall Regime:** {trace.economic_regime}",
        *_bullet_block("**Key Drivers:**", drivers),
        *_bullet_block("**Primary Risks:**", risks),
        *_bullet_block("**Opportunities:**", opps),
        f"**Confidence:** {brief.confidence_pct}%",
    ]
    note = hypothetical_scenario_note(brief, macro_intent=macro_intent, question=question)
    if note:
        lines.extend(["", note])
    return "\n".join(lines)


def render_full_macro_outlook(
    brief: MacroIntelligenceBrief,
    *,
    beginner: bool,
    macro_intent: str = "",
    question: str = "",
) -> str:
    """Full strategist dashboard (Phase 3.4); uses same brief as compact header."""
    trace = brief.trace
    sections = [
        render_compact_macro_outlook(
            brief,
            beginner=beginner,
            macro_intent=macro_intent,
            question=question,
        ),
        "",
        "**Supporting evidence**",
        *[f"- {e}" for e in trace.supporting_evidence],
        "",
        "**Primary risks**",
        *[f"- {r}" for r in trace.primary_risks],
        "",
        "**Opportunities**",
        *[f"- {o}" for o in trace.opportunities],
        "",
        "**Recommendation drivers**",
        *[f"- {d}" for d in trace.recommendation_drivers],
        "",
        f"**Conclusion:** {trace.final_macro_conclusion}",
    ]
    if brief.assumption_tensions:
        sections.extend(["", "**Assumption notes**", *[f"- {t}" for t in brief.assumption_tensions]])
    if not beginner and brief.channel_ranks:
        sections.extend(
            [
                "",
                "**Portfolio channel sensitivity (internal rank)**",
                *[f"- {name}: {score:.1f}" for name, score in brief.channel_ranks[:4]],
            ]
        )
    return "\n".join(sections)
