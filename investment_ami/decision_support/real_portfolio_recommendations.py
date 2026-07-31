"""Structured recommendation models for the real portfolio advisor (Phase C)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

RecommendationUrgency = Literal["low", "medium", "high"]
RecommendationStatus = Literal[
    "action_recommended",
    "information_needed",
    "hold",
    "insufficient_data",
]
ConfidenceLevel = Literal["low", "medium", "high"]

ActionType = Literal[
    "hold_current_course",
    "no_urgent_change",
    "refresh_market_data",
    "add_missing_cost_basis",
    "define_target_allocation",
    "direct_new_contributions",
    "rebalance_with_new_money",
    "review_material_single_security",
    "review_asset_class_overweight",
    "preserve_liquidity",
    "reduce_contribution_temporarily",
    "seek_tax_guidance_before_sale",
    "insufficient_data",
]


@dataclass(frozen=True)
class RealPortfolioRecommendation:
    code: str
    priority: int
    action_type: ActionType
    title: str
    rationale_code: str
    evidence: dict[str, Any] = field(default_factory=dict)
    conditions: tuple[str, ...] = ()
    caution_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class RecommendationRuleResult:
    code: str
    priority: int
    action_type: ActionType
    rationale_code: str
    evidence: dict[str, Any] = field(default_factory=dict)
    conditions: tuple[str, ...] = ()
    caution_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class RealPortfolioRecommendationSet:
    primary_action: ActionType
    recommendations: tuple[RealPortfolioRecommendation, ...]
    urgency: RecommendationUrgency
    recommendation_status: RecommendationStatus
    confidence_level: ConfidenceLevel
    confidence_score: int
    supporting_facts: tuple[str, ...]
    tradeoffs: tuple[str, ...]
    information_needed: tuple[str, ...]
    data_quality_flags: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    contribution_placement: dict[str, Any] | None = None
