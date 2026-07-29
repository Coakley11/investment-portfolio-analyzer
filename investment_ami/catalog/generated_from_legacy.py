"""Build question catalog entries from legacy ``investment_ami_context`` intents."""

from __future__ import annotations

from investment_ami.models.question import AmiCategory, AmiQuestionDefinition, OutputType, PipelineProfile

# Maps legacy intent id → catalog metadata (no phrase duplication in routing).
_INTENT_SPECS: dict[str, dict[str, object]] = {
    "portfolio_concentration": {
        "title": "Portfolio concentration",
        "category": AmiCategory.PORTFOLIO_ANALYSIS,
        "description": "Judge whether holdings are too concentrated in single names or sleeves.",
        "engines": ("portfolio_analysis", "risk_analysis"),
        "output_type": "diagnostic",
        "profile": "portfolio_only",
        "legacy": "phase2",
        "required": frozenset({"current_weights"}),
        "optional": frozenset({"health_score", "holdings"}),
        "follow_up": ("diversification", "portfolio_risk", "allocation_recommendation"),
    },
    "rebalance_allocation": {
        "title": "Explain allocation",
        "category": AmiCategory.ASSET_ALLOCATION,
        "description": "Interpret current weights, targets, and drift versus goals.",
        "engines": ("portfolio_analysis", "asset_allocation"),
        "output_type": "diagnostic",
        "profile": "portfolio_only",
        "legacy": "phase1",
        "required": frozenset({"current_weights"}),
        "optional": frozenset({"target_weights", "rebalance_drift"}),
        "follow_up": ("allocation_recommendation", "portfolio_risk"),
    },
    "portfolio_risk": {
        "title": "Portfolio risk",
        "category": AmiCategory.PORTFOLIO_ANALYSIS,
        "description": "Identify the dominant risks in the current portfolio mix.",
        "engines": ("portfolio_analysis", "risk_analysis"),
        "output_type": "diagnostic",
        "profile": "portfolio_only",
        "legacy": "phase2",
        "required": frozenset({"current_weights"}),
        "optional": frozenset({"health_score", "volatility", "sharpe_ratio"}),
        "follow_up": ("risk_reduction", "scenario_stress"),
    },
    "sector_exposure": {
        "title": "Sector / tech exposure",
        "category": AmiCategory.STOCK_ANALYSIS,
        "description": "Measure technology or sector concentration in holdings.",
        "engines": ("portfolio_analysis", "diversification"),
        "output_type": "diagnostic",
        "profile": "portfolio_only",
        "legacy": "phase1",
        "required": frozenset({"current_weights"}),
        "optional": frozenset({"tech_exposure"}),
        "follow_up": ("diversification", "scenario_stress"),
    },
    "risk_reduction": {
        "title": "Reduce portfolio risk",
        "category": AmiCategory.RISK_MANAGEMENT,
        "description": "Educational guidance for lowering risk while noting tradeoffs.",
        "engines": ("behavioral_finance", "risk_analysis", "asset_allocation"),
        "output_type": "recommendation",
        "profile": "portfolio_only",
        "legacy": "phase1",
        "required": frozenset(),
        "optional": frozenset({"current_weights", "risk_level", "objective"}),
        "follow_up": ("allocation_recommendation", "diversification"),
    },
    "investment_coach": {
        "title": "Investment education",
        "category": AmiCategory.INVESTMENT_EDUCATION,
        "description": "Plain-language explanations of investing concepts.",
        "engines": ("education",),
        "output_type": "education",
        "profile": "coach",
        "legacy": "phase1",
        "required": frozenset(),
        "optional": frozenset({"experience_mode"}),
        "follow_up": ("portfolio_risk", "diversification"),
    },
    "etf_overlap": {
        "title": "ETF overlap",
        "category": AmiCategory.ETF_ANALYSIS,
        "description": "Compare duplicate exposure across ETFs in the portfolio.",
        "engines": ("diversification",),
        "output_type": "diagnostic",
        "profile": "portfolio_only",
        "legacy": "phase2",
        "required": frozenset({"holdings"}),
        "optional": frozenset({"etf_overlap_pairs", "current_weights"}),
        "follow_up": ("diversification", "allocation_recommendation"),
    },
    "diversification": {
        "title": "Diversification",
        "category": AmiCategory.DIVERSIFICATION,
        "description": "Assess breadth across asset classes and holdings.",
        "engines": ("diversification", "portfolio_analysis"),
        "output_type": "diagnostic",
        "profile": "portfolio_only",
        "legacy": "phase2",
        "required": frozenset({"current_weights"}),
        "optional": frozenset({"asset_class_breakdown"}),
        "follow_up": ("etf_overlap", "allocation_recommendation"),
    },
    "scenario_stress": {
        "title": "Scenario stress",
        "category": AmiCategory.SCENARIO_ANALYSIS,
        "description": "Estimate portfolio impact under hypothetical shocks.",
        "engines": ("scenario_analysis", "risk_analysis"),
        "output_type": "scenario",
        "profile": "full",
        "legacy": "phase2",
        "required": frozenset(),
        "optional": frozenset({"scenario_params", "current_weights", "tech_exposure"}),
        "follow_up": ("risk_reduction", "macro_rates"),
    },
    "valuation": {
        "title": "Valuation",
        "category": AmiCategory.INVESTMENT_RESEARCH,
        "description": "Relate price, P/E, and implied growth to macro and style bands.",
        "engines": ("valuation",),
        "output_type": "diagnostic",
        "profile": "full",
        "legacy": "phase2",
        "required": frozenset(),
        "optional": frozenset({"health_valuation", "macro_summary"}),
        "follow_up": ("allocation_recommendation", "scenario_stress"),
    },
    "macro_rates": {
        "title": "Interest rate scenarios",
        "category": AmiCategory.MACROECONOMICS,
        "description": "Discuss rate shocks and duration-sensitive portfolio effects.",
        "engines": ("macroeconomic", "scenario_analysis"),
        "output_type": "scenario",
        "profile": "macro_only",
        "legacy": "phase2",
        "required": frozenset(),
        "optional": frozenset({"macro_summary", "scenario_params"}),
        "follow_up": ("scenario_stress", "allocation_recommendation"),
    },
    "macro_recession": {
        "title": "Recession scenarios",
        "category": AmiCategory.MACROECONOMICS,
        "description": "Recession probability and defensive positioning tradeoffs.",
        "engines": ("macroeconomic", "scenario_analysis"),
        "output_type": "scenario",
        "profile": "macro_only",
        "legacy": "phase2",
        "required": frozenset(),
        "optional": frozenset({"macro_summary", "health_recession"}),
        "follow_up": ("risk_reduction", "scenario_stress"),
    },
    "macro_inflation": {
        "title": "Inflation scenarios",
        "category": AmiCategory.MACROECONOMICS,
        "description": "Inflation regime effects on real returns and allocation.",
        "engines": ("macroeconomic", "scenario_analysis"),
        "output_type": "scenario",
        "profile": "macro_only",
        "legacy": "phase2",
        "required": frozenset(),
        "optional": frozenset({"macro_summary", "health_inflation"}),
        "follow_up": ("macro_rates", "allocation_recommendation"),
    },
    "allocation_recommendation": {
        "title": "Allocation recommendations",
        "category": AmiCategory.ASSET_ALLOCATION,
        "description": "Suggest allocation adjustments with strengths, weaknesses, and tradeoffs.",
        "engines": ("asset_allocation", "portfolio_analysis"),
        "output_type": "recommendation",
        "profile": "full",
        "legacy": "phase2",
        "required": frozenset({"current_weights"}),
        "optional": frozenset({"target_weights", "objective", "health_score"}),
        "follow_up": ("rebalance_allocation", "diversification"),
    },
    "analytical_synthesis": {
        "title": "Portfolio analytical synthesis",
        "category": AmiCategory.PORTFOLIO_ANALYSIS,
        "description": "Question-conditioned portfolio analysis grounded in computed facts.",
        "engines": ("portfolio_analysis", "risk_analysis", "macro_intelligence"),
        "output_type": "recommendation",
        "profile": "full",
        "legacy": "p4",
        "required": frozenset(),
        "optional": frozenset({"current_weights", "health_score", "macro_assumptions"}),
        "follow_up": ("portfolio_risk", "scenario_stress"),
    },
}


def _starters_for_intent(intent_id: str, starters: tuple[str, ...]) -> tuple[str, ...]:
    from investment_ami_context import detect_investment_send_intent

    matched = [s for s in starters if detect_investment_send_intent(s, "") == intent_id]
    return tuple(matched)


def build_legacy_question_catalog() -> dict[str, AmiQuestionDefinition]:
    import investment_ami_context as legacy

    starters = legacy.INVESTMENT_AMI_STARTER_QUESTIONS
    catalog: dict[str, AmiQuestionDefinition] = {}
    for intent_id in sorted(legacy._INVESTMENT_SOLVER_INTENTS):  # noqa: SLF001
        spec = _INTENT_SPECS.get(intent_id)
        if not spec:
            spec = {
                "title": intent_id.replace("_", " ").title(),
                "category": AmiCategory.PORTFOLIO_ANALYSIS,
                "description": f"Legacy intent `{intent_id}`.",
                "engines": ("portfolio_analysis",),
                "output_type": "diagnostic",
                "profile": "legacy",
                "legacy": "phase1",
                "required": frozenset(),
                "optional": frozenset(),
                "follow_up": (),
            }
        intent_starters = _starters_for_intent(intent_id, starters)
        catalog[intent_id] = AmiQuestionDefinition(
            id=intent_id,
            title=str(spec["title"]),
            category=spec["category"],  # type: ignore[arg-type]
            description=str(spec["description"]),
            example_phrases=(),
            starter_questions=intent_starters,
            required_context_keys=spec["required"],  # type: ignore[arg-type]
            optional_context_keys=spec["optional"],  # type: ignore[arg-type]
            recommended_engines=tuple(str(e) for e in spec["engines"]),  # type: ignore[arg-type]
            output_type=spec["output_type"],  # type: ignore[arg-type]
            follow_up_question_ids=tuple(str(x) for x in spec["follow_up"]),  # type: ignore[arg-type]
            pipeline_profile=spec["profile"],  # type: ignore[arg-type]
            legacy_solver=str(spec["legacy"]),
        )
    return catalog
