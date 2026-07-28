"""AMI question catalog metadata."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class AmiCategory(str, Enum):
    PORTFOLIO_ANALYSIS = "portfolio_analysis"
    BUY_SELL_DECISIONS = "buy_sell_decisions"
    INVESTMENT_RESEARCH = "investment_research"
    ETF_ANALYSIS = "etf_analysis"
    STOCK_ANALYSIS = "stock_analysis"
    RISK_MANAGEMENT = "risk_management"
    ASSET_ALLOCATION = "asset_allocation"
    DIVERSIFICATION = "diversification"
    MACROECONOMICS = "macroeconomics"
    RETIREMENT_PLANNING = "retirement_planning"
    BEHAVIORAL_FINANCE = "behavioral_finance"
    INVESTMENT_EDUCATION = "investment_education"
    SCENARIO_ANALYSIS = "scenario_analysis"


OutputType = Literal["recommendation", "education", "scenario", "diagnostic"]
PipelineProfile = Literal["legacy", "full", "portfolio_only", "macro_only", "coach"]


@dataclass(frozen=True)
class AmiQuestionDefinition:
    id: str
    title: str
    category: AmiCategory
    description: str
    example_phrases: tuple[str, ...]
    starter_questions: tuple[str, ...]
    required_context_keys: frozenset[str]
    optional_context_keys: frozenset[str]
    recommended_engines: tuple[str, ...]
    output_type: OutputType
    follow_up_question_ids: tuple[str, ...]
    pipeline_profile: PipelineProfile
    legacy_solver: str
