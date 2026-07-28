"""Shared utilities for investment AMI engines."""

from investment_ami.engines.support.macro_context import MacroScenarioContext, resolve_macro_scenario_context
from investment_ami.engines.support.overlap_data import (
    compute_pairwise_overlap_pct,
    resolve_etf_overlap_pairs,
    tickers_mentioned_in_question,
)
from investment_ami.engines.support.presentation import default_educational_risk_notes
from investment_ami.engines.support.scenario_stress_data import (
    ScenarioStressSnapshot,
    build_scenario_stress_snapshot,
    parse_scenario_drawdown_pct,
)
from investment_ami.engines.support.behavioral_finance_content import (
    build_advanced_risk_reduction_lines,
    build_beginner_risk_reduction_lines,
)
from investment_ami.engines.support.education_content import (
    format_advanced_coach_snapshot,
    format_beginner_coach_snapshot,
)

__all__ = (
    "MacroScenarioContext",
    "ScenarioStressSnapshot",
    "build_advanced_risk_reduction_lines",
    "build_beginner_risk_reduction_lines",
    "build_scenario_stress_snapshot",
    "compute_pairwise_overlap_pct",
    "default_educational_risk_notes",
    "format_advanced_coach_snapshot",
    "format_beginner_coach_snapshot",
    "parse_scenario_drawdown_pct",
    "resolve_etf_overlap_pairs",
    "resolve_macro_scenario_context",
    "tickers_mentioned_in_question",
)
