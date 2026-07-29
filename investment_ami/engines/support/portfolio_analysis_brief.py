"""
Portfolio analysis brief — canonical fact layer for analytical synthesis.

Phase 3: concise, high-trust facts with measurement context, derived summaries,
provenance, and explicit limitations (80/20 — quality over field count).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from investment_ami.engines.support.portfolio_brief_helpers import (
    MAX_HOLDINGS_IN_BRIEF,
    InferenceClass,
    build_data_quality,
    classify_portfolio_archetype,
    concentration_summary,
    overlap_summary,
    scenario_summary,
    sector_allocation_summary,
    sleeve_profile_summary,
)

BRIEF_VERSION = "2.1.0"
BRIEF_SCHEMA_VERSION = "2.1"
DOMAIN_ID = "investment"

REQUIRED_SECTION_KEYS = (
    "measurement",
    "data_quality",
    "holdings",
    "concentration",
    "allocation",
    "sector",
    "overlap",
    "risk",
    "diversification",
    "scenario",
    "rebalance",
    "health_and_performance",
    "macro",
    "assumptions",
)


@dataclass(frozen=True)
class FactDescriptor:
    """Provenance for one citeable fact in the brief."""

    fact_id: str
    label: str
    unit: str
    source_engine: str
    source_path: str
    inference_class: InferenceClass = "computed"
    description: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "fact_id": self.fact_id,
            "label": self.label,
            "unit": self.unit,
            "source_engine": self.source_engine,
            "source_path": self.source_path,
            "inference_class": self.inference_class,
            "description": self.description,
        }


@dataclass
class PortfolioAnalysisBrief:
    """Analyst pre-memo workbook — facts, summaries, limitations."""

    brief_version: str = BRIEF_VERSION
    brief_schema_version: str = BRIEF_SCHEMA_VERSION
    domain_id: str = DOMAIN_ID
    generated_at_utc: str = ""
    question_context: str = ""
    portfolio_label: str = ""
    holdings_fingerprint: str = ""
    experience_mode: str = ""
    source_page: str = ""
    facts: dict[str, Any] = field(default_factory=dict)
    sections: dict[str, Any] = field(default_factory=dict)
    fact_index: dict[str, FactDescriptor] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    assembly_trace: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "brief_version": self.brief_version,
            "brief_schema_version": self.brief_schema_version,
            "domain_id": self.domain_id,
            "generated_at_utc": self.generated_at_utc,
            "question_context": self.question_context,
            "portfolio_label": self.portfolio_label,
            "holdings_fingerprint": self.holdings_fingerprint,
            "experience_mode": self.experience_mode,
            "source_page": self.source_page,
            "facts": dict(self.facts),
            "sections": dict(self.sections),
            "fact_index": {k: v.to_dict() for k, v in self.fact_index.items()},
            "limitations": list(self.limitations),
            "assembly_trace": list(self.assembly_trace),
        }

    def to_envelope_dict(self) -> dict[str, Any]:
        return {
            "domain_id": self.domain_id,
            "brief_version": self.brief_version,
            "brief_schema_version": self.brief_schema_version,
            "generated_at_utc": self.generated_at_utc,
            "facts": dict(self.facts),
            "fact_index": {k: v.to_dict() for k, v in self.fact_index.items()},
            "limitations": list(self.limitations),
            "trace": list(self.assembly_trace),
            "sections": dict(self.sections),
        }


def validate_brief_invariants(brief: PortfolioAnalysisBrief) -> list[str]:
    """Phase 3.1 — structural checks for tests and diagnostics."""
    errors: list[str] = []
    for fid in brief.facts:
        if fid not in brief.fact_index:
            errors.append(f"facts[{fid!r}] missing from fact_index")
    for fid in brief.fact_index:
        if fid not in brief.facts:
            errors.append(f"fact_index[{fid!r}] missing from facts")
    for key in REQUIRED_SECTION_KEYS:
        if key not in brief.sections:
            errors.append(f"sections missing required key {key!r}")
    if brief.brief_schema_version != BRIEF_SCHEMA_VERSION:
        errors.append(f"unexpected brief_schema_version {brief.brief_schema_version!r}")
    return errors


def _register_fact(
    brief: PortfolioAnalysisBrief,
    fact_id: str,
    value: Any,
    *,
    label: str,
    unit: str,
    source_engine: str,
    source_path: str,
    inference_class: InferenceClass = "computed",
    description: str = "",
) -> None:
    brief.facts[fact_id] = value
    brief.fact_index[fact_id] = FactDescriptor(
        fact_id=fact_id,
        label=label,
        unit=unit,
        source_engine=source_engine,
        source_path=source_path,
        inference_class=inference_class,
        description=description,
    )


def _measurement_block(ctx: dict[str, Any], generated_at: str) -> dict[str, Any]:
    hist_note = str(ctx.get("context_note_historical") or "").strip()
    fwd_note = str(ctx.get("context_note_forward") or "").strip()
    start = str(ctx.get("analysis_start_date") or ctx.get("analysis_start") or "").strip()
    end = str(ctx.get("analysis_end_date") or ctx.get("analysis_end") or "").strip()
    rf = ctx.get("risk_free_pct")
    rf_text = f"{rf}%" if rf not in (None, "") else ""
    return {
        "as_of_utc": generated_at,
        "historical_metrics_window": {"start": start or None, "end": end or None},
        "risk_free_rate_pct": rf_text or None,
        "historical_metrics_label": hist_note or "Historical return/volatility/Sharpe when present.",
        "forward_macro_label": fwd_note or "Macro and Health assumptions affect forward-style reasoning only.",
    }


def _macro_brief_section(brief_obj: Any) -> dict[str, Any]:
    trace = brief_obj.trace
    scenario = brief_obj.scenario
    return {
        "brief_version": brief_obj.brief_version,
        "confidence_pct": brief_obj.confidence_pct,
        "assumption_tensions": list(brief_obj.assumption_tensions),
        "channel_ranks": list(brief_obj.channel_ranks),
        "scenario": {
            "rate_environment": scenario.rate_environment,
            "economic_regime": scenario.economic_regime,
            "recession_probability": scenario.recession_probability,
            "valuation_environment": scenario.valuation_environment,
            "allocation_profile": dict(scenario.allocation_profile),
            "has_portfolio_weights": scenario.has_portfolio_weights,
        },
        "reasoning_trace": trace.to_computed_dict(),
    }


def build_portfolio_analysis_brief(
    context: dict[str, Any] | None,
    *,
    question: str = "",
) -> PortfolioAnalysisBrief:
    """Assemble a concise, high-trust portfolio facts brief."""
    ctx = dict(context or {})
    generated_at = datetime.now(timezone.utc).isoformat()
    brief = PortfolioAnalysisBrief(
        generated_at_utc=generated_at,
        question_context=str(question or "").strip(),
        source_page=str(ctx.get("page") or ctx.get("source_page") or "").strip(),
        experience_mode=str(ctx.get("experience_mode") or ctx.get("experience") or "").strip(),
        holdings_fingerprint=str(ctx.get("holdings_fingerprint") or "").strip(),
    )
    trace = brief.assembly_trace

    from investment_ami_instant_solver import _portfolio_label, _weight_rows

    all_rows = _weight_rows(ctx)
    truncated = len(all_rows) > MAX_HOLDINGS_IN_BRIEF
    rows = all_rows[:MAX_HOLDINGS_IN_BRIEF]
    brief.portfolio_label = _portfolio_label(ctx)
    weight_list = [{"ticker": t, "weight_pct": round(p, 2)} for t, p in rows]
    trace.append("holdings:weight_rows")

    measurement = _measurement_block(ctx, generated_at)
    _register_fact(
        brief,
        "measurement.context",
        measurement,
        label="Measurement and as-of context",
        unit="mixed",
        source_engine="portfolio_analysis_brief",
        source_path="measurement.context",
        inference_class="assumption",
    )
    trace.append("block:measurement")
    if not measurement["historical_metrics_window"]["start"]:
        brief.limitations.append(
            "Historical performance window (analysis start/end dates) not in context — "
            "return/volatility/Sharpe are unlabeled if present."
        )

    _register_fact(
        brief,
        "holdings.position_count",
        len(all_rows),
        label="Number of weighted positions",
        unit="count",
        source_engine="applied_math_context",
        source_path="current_weights",
        inference_class="measured",
    )
    _register_fact(
        brief,
        "holdings.weights",
        weight_list,
        label="Portfolio weights by ticker (top positions)",
        unit="percent",
        source_engine="applied_math_context",
        source_path="current_weights",
        inference_class="measured",
        description=f"Up to {MAX_HOLDINGS_IN_BRIEF} lines; see data_quality if truncated.",
    )
    if truncated:
        brief.limitations.append(
            f"Holdings list truncated to {MAX_HOLDINGS_IN_BRIEF} of {len(all_rows)} positions in the brief."
        )

    if rows:
        top_t, top_p = rows[0]
        _register_fact(
            brief,
            "holdings.largest_weight_ticker",
            top_t,
            label="Largest holding ticker",
            unit="ticker",
            source_engine="portfolio_concentration",
            source_path="assess_portfolio_concentration.top_ticker",
            inference_class="computed",
        )
        _register_fact(
            brief,
            "holdings.largest_weight_pct",
            round(top_p, 2),
            label="Largest holding weight",
            unit="percent",
            source_engine="portfolio_concentration",
            source_path="assess_portfolio_concentration.top_pct",
            inference_class="computed",
        )
    else:
        brief.limitations.append("No portfolio weights in context — concentration and risk metrics are unavailable.")

    if str(ctx.get("portfolio_value") or "").strip():
        _register_fact(
            brief,
            "portfolio.notional_value",
            str(ctx.get("portfolio_value")).strip(),
            label="Sidebar portfolio value",
            unit="usd",
            source_engine="applied_math_context",
            source_path="portfolio_value",
            inference_class="measured",
        )

    from investment_ami.engines.portfolio_concentration import assess_portfolio_concentration

    conc = assess_portfolio_concentration(ctx)
    trace.append("engine:portfolio_concentration")
    conc_summary_obj: dict[str, Any] | None = None
    if not conc.empty:
        _register_fact(
            brief,
            "concentration.top3_weight_pct",
            round(conc.top3_pct, 2),
            label="Top-three holdings combined weight",
            unit="percent",
            source_engine="portfolio_concentration",
            source_path="assess_portfolio_concentration.top3_pct",
            inference_class="computed",
        )
        _register_fact(
            brief,
            "concentration.flag",
            conc.flag,
            label="Concentration severity flag",
            unit="category",
            source_engine="portfolio_concentration",
            source_path="assess_portfolio_concentration.flag",
            inference_class="computed",
        )
        conc_summary_obj = concentration_summary(
            top_ticker=conc.top_ticker,
            top_pct=conc.top_pct,
            top3_pct=conc.top3_pct,
            flag=conc.flag,
        )
        _register_fact(
            brief,
            "concentration.summary",
            conc_summary_obj,
            label="Concentration narrative summary",
            unit="text",
            source_engine="portfolio_concentration",
            source_path="concentration_summary",
            inference_class="computed",
        )

    sleeves = sleeve_profile_summary(ctx)
    _register_fact(
        brief,
        "allocation.sleeve_summary",
        sleeves,
        label="Equity/bond/defensive sleeve summary",
        unit="percent",
        source_engine="investment_ami_macro",
        source_path="allocation_profile_from_ctx",
        inference_class="computed",
    )
    trace.append("derived:sleeve_summary")

    breakdown = ctx.get("asset_class_breakdown")
    asset_class_count = len(breakdown) if isinstance(breakdown, dict) else 0
    tech = ctx.get("tech_exposure")
    if not isinstance(tech, dict) or tech.get("total_pct") is None:
        from investment_ami_exposure import resolve_tech_exposure

        tech = resolve_tech_exposure(ctx)
    sector_obj, sector_limits = sector_allocation_summary(ctx, tech_exposure=tech if isinstance(tech, dict) else None)
    brief.limitations.extend(sector_limits)
    if sector_obj:
        _register_fact(
            brief,
            "sector.allocation_summary",
            sector_obj,
            label="Asset-class and technology allocation summary",
            unit="mixed",
            source_engine="portfolio_analysis_brief",
            source_path="sector_allocation_summary",
            inference_class="computed",
        )
        trace.append("derived:sector_summary")

    overlap_pairs_raw = ctx.get("etf_overlap_pairs")
    overlap_pairs = overlap_pairs_raw if isinstance(overlap_pairs_raw, list) else []
    overlap_sum = overlap_summary(overlap_pairs)
    if overlap_sum:
        _register_fact(
            brief,
            "overlap.summary",
            overlap_sum,
            label="ETF overlap summary",
            unit="percent",
            source_engine="portfolio_analysis_brief",
            source_path="overlap_summary",
            inference_class="computed",
        )
        _register_fact(
            brief,
            "overlap.etf_pairs",
            overlap_pairs[:6],
            label="Top ETF overlap pairs (detail)",
            unit="percent",
            source_engine="applied_math_context",
            source_path="etf_overlap_pairs",
            inference_class="measured",
        )
        trace.append("context:etf_overlap")
    elif len(all_rows) >= 2:
        brief.limitations.append("ETF overlap pairs not computed — overlap narrative may be incomplete.")

    from investment_ami.engines.portfolio_risk import assess_portfolio_risk

    risk = assess_portfolio_risk(ctx)
    trace.append("engine:portfolio_risk")
    if risk.tech_proxy_pct:
        _register_fact(
            brief,
            "risk.tech_exposure_total_pct",
            round(risk.tech_proxy_pct, 2),
            label="Technology exposure (total)",
            unit="percent",
            source_engine="portfolio_risk",
            source_path="assess_portfolio_risk.tech_proxy_pct",
            inference_class="computed",
        )
    for key, val, label, path in (
        ("risk.level", risk.risk_level, "Health risk level label", "risk_level"),
        ("risk.volatility_historical", risk.volatility, "Historical volatility", "volatility"),
        ("risk.max_drawdown_historical", risk.max_drawdown, "Historical max drawdown", "max_drawdown"),
    ):
        if val:
            _register_fact(
                brief,
                key,
                val,
                label=label,
                unit="text" if key == "risk.level" else "percent",
                source_engine="applied_math_context",
                source_path=path,
                inference_class="measured",
            )
    if rows and not risk.volatility:
        brief.limitations.append("Historical volatility/Sharpe not in context — run Portfolio Health analyze for performance metrics.")

    from investment_ami.engines.diversification import assess_diversification

    div = assess_diversification(ctx)
    trace.append("engine:diversification")
    if not div.empty:
        _register_fact(
            brief,
            "diversification.judgment",
            div.judgment,
            label="Diversification judgment",
            unit="text",
            source_engine="diversification",
            source_path="assess_diversification.judgment",
            inference_class="computed",
        )
    elif rows and not isinstance(breakdown, dict):
        brief.limitations.append("Asset-class breakdown missing — diversification uses weight proxy only.")

    scen_obj, scen_limits = scenario_summary(ctx, question=question)
    brief.limitations.extend(scen_limits)
    if scen_obj:
        _register_fact(
            brief,
            "scenario.summary",
            scen_obj,
            label="Standard illustrative scenario shocks",
            unit="mixed",
            source_engine="scenario_stress_data",
            source_path="scenario_summary",
            inference_class="estimated",
            description="Educational stress illustrations, not forecasts.",
        )
        trace.append("derived:scenario_summary")

    archetype = classify_portfolio_archetype(
        all_rows,
        asset_class_count=asset_class_count,
        overlap_pair_count=len(overlap_pairs),
        top_weight_pct=conc.top_pct if not conc.empty else (rows[0][1] if rows else 0.0),
    )
    _register_fact(
        brief,
        "portfolio.archetype",
        archetype,
        label="Portfolio structure archetype",
        unit="category",
        source_engine="portfolio_brief_helpers",
        source_path="classify_portfolio_archetype",
        inference_class="computed",
    )

    rebalance_section: dict[str, Any] = {}
    target = ctx.get("target_weights")
    drift = ctx.get("rebalance_drift")
    has_targets = isinstance(target, dict) and bool(target)
    if has_targets:
        rebalance_section["target_weights"] = dict(target)
        _register_fact(
            brief,
            "rebalance.target_weights",
            dict(target),
            label="Target allocation weights",
            unit="percent",
            source_engine="applied_math_context",
            source_path="target_weights",
            inference_class="measured",
        )
    if isinstance(drift, dict) and drift:
        rebalance_section["drift_vs_target"] = dict(drift)
        _register_fact(
            brief,
            "rebalance.drift_vs_target",
            dict(drift),
            label="Drift versus target",
            unit="percentage_points",
            source_engine="applied_math_context",
            source_path="rebalance_drift",
            inference_class="measured",
        )
    if rebalance_section:
        trace.append("context:rebalance")

    health_section: dict[str, Any] = {}
    has_performance = False
    score = ctx.get("health_score")
    if score is not None and score != "":
        health_section["health_score"] = score
        _register_fact(
            brief,
            "health.score",
            score,
            label="Portfolio Health score",
            unit="score",
            source_engine="applied_math_context",
            source_path="health_score",
            inference_class="measured",
        )
    for ctx_key, fact_id, label in (
        ("expected_return", "performance.expected_return_historical", "Historical expected return"),
        ("sharpe_ratio", "performance.sharpe_historical", "Historical Sharpe ratio"),
    ):
        val = ctx.get(ctx_key)
        if val not in (None, ""):
            has_performance = True
            health_section[ctx_key] = val
            _register_fact(
                brief,
                fact_id,
                val,
                label=label,
                unit="mixed",
                source_engine="applied_math_context",
                source_path=ctx_key,
                inference_class="measured",
            )

    macro_section: dict[str, Any] = {}
    has_macro_brief = False
    try:
        from investment_ami.engines.support.macro_intelligence import build_macro_intelligence_brief

        macro_brief = build_macro_intelligence_brief(ctx, macro_intent="macro_inflation", question=question)
        has_macro_brief = True
        macro_section["intelligence_brief"] = _macro_brief_section(macro_brief)
        scenario = macro_brief.scenario
        _register_fact(
            brief,
            "macro.regime",
            macro_brief.trace.economic_regime,
            label="Macro economic regime",
            unit="text",
            source_engine="macro_intelligence",
            source_path="trace.economic_regime",
            inference_class="computed",
        )
        if scenario.rate_environment:
            _register_fact(
                brief,
                "macro.rate_environment",
                scenario.rate_environment,
                label="Rate environment assumption",
                unit="text",
                source_engine="macro_intelligence",
                source_path="scenario.rate_environment",
                inference_class="assumption",
            )
        if scenario.recession_probability is not None:
            _register_fact(
                brief,
                "macro.recession_probability",
                round(float(scenario.recession_probability) * 100, 1),
                label="Recession probability (assumption)",
                unit="percent",
                source_engine="macro_intelligence",
                source_path="scenario.recession_probability",
                inference_class="assumption",
            )
        if scenario.valuation_environment:
            _register_fact(
                brief,
                "macro.valuation_environment",
                scenario.valuation_environment,
                label="Valuation environment assumption",
                unit="text",
                source_engine="macro_intelligence",
                source_path="scenario.valuation_environment",
                inference_class="assumption",
            )
        if macro_brief.assumption_tensions:
            _register_fact(
                brief,
                "macro.assumption_tensions",
                list(macro_brief.assumption_tensions),
                label="Macro assumption tensions",
                unit="text",
                source_engine="macro_intelligence",
                source_path="assumption_tensions",
                inference_class="assumption",
            )
        brief.limitations.append(
            "Macro regime narrative uses baseline inflation macro lens for desk context — not question-specific shock."
        )
        trace.append("engine:macro_intelligence_brief")
    except Exception as exc:
        brief.limitations.append(f"Macro intelligence brief unavailable: {exc}")
        summary = ctx.get("macro_summary") or ctx.get("macro_outlook")
        if summary:
            macro_section["summary_fallback"] = summary

    assumptions: list[str] = []
    for key in ("health_inflation", "health_rate_env", "health_recession", "health_valuation", "health_regime"):
        val = ctx.get(key)
        if val not in (None, ""):
            assumptions.append(f"{key}={val}")
    if assumptions:
        _register_fact(
            brief,
            "assumptions.health_and_macro",
            assumptions,
            label="Portfolio Health / macro assumption labels",
            unit="text",
            source_engine="applied_math_context",
            source_path="health_assumptions",
            inference_class="assumption",
        )

    dq = build_data_quality(
        rows=all_rows,
        has_performance=has_performance,
        has_overlap=bool(overlap_sum),
        has_targets=has_targets,
        has_macro_brief=has_macro_brief,
        has_asset_classes=bool(asset_class_count),
        weight_rows_truncated=truncated,
    )
    _register_fact(
        brief,
        "data_quality.completeness",
        dq,
        label="Data completeness and quality tier",
        unit="mixed",
        source_engine="portfolio_brief_helpers",
        source_path="build_data_quality",
        inference_class="computed",
    )
    trace.append("block:data_quality")

    brief.sections = {
        "measurement": measurement,
        "data_quality": dq,
        "holdings": {
            "label": brief.portfolio_label,
            "weights": weight_list,
            "position_count": len(all_rows),
            "truncated": truncated,
        },
        "concentration": conc_summary_obj,
        "allocation": sleeves,
        "sector": sector_obj or None,
        "overlap": overlap_sum,
        "risk": {
            "risk_level": risk.risk_level or None,
            "volatility_historical": risk.volatility or None,
            "max_drawdown_historical": risk.max_drawdown or None,
            "tech_exposure_total_pct": round(risk.tech_proxy_pct, 2) if risk.tech_proxy_pct else None,
        },
        "diversification": {"judgment": div.judgment if not div.empty else None},
        "scenario": scen_obj or None,
        "rebalance": rebalance_section or None,
        "health_and_performance": health_section or None,
        "macro": macro_section or None,
        "assumptions": assumptions or None,
    }

    return brief
