"""Canonical analytical AMI benchmark questions for evaluation (Phase 4+)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Shared evaluation portfolio — diagnosable 55/45 equity/bond with health + macro context.
IPA_BENCH_EVAL_CONTEXT: dict[str, Any] = {
    "page": "Portfolio Health",
    "holdings_fingerprint": "eval-bench-v1",
    "current_weights": {"VOO": 55.0, "BND": 45.0},
    "asset_class_breakdown": {"Equity": 55.0, "Bond": 45.0},
    "health_score": 74.0,
    "volatility": "11.2%",
    "expected_return": "7.8%",
    "sharpe_ratio": "0.62",
    "max_drawdown": "-18.5%",
    "analysis_start_date": "2020-01-01",
    "analysis_end_date": "2025-12-31",
    "risk_free_pct": 3.5,
    "health_rate_env": "Stable Rates",
    "health_inflation": "Moderate Inflation",
    "health_regime": "Expansion",
    "health_valuation": "Fair Value",
    "scenario_params": {"rate_shock": "Stable Rates"},
    "etf_overlap_pairs": [{"pair": "VOO/VTI", "overlap_pct": 99.0}],
    "experience_mode": "Advanced Mode",
}


@dataclass(frozen=True)
class AnalyticalBenchmark:
    benchmark_id: str
    question: str
    expected_question_tag: str
    notes: str = ""


ANALYTICAL_BENCHMARKS: tuple[AnalyticalBenchmark, ...] = (
    AnalyticalBenchmark(
        "B1",
        "Critique my portfolio as an institutional portfolio manager.",
        "critique",
    ),
    AnalyticalBenchmark(
        "B2",
        "What are the five biggest risks facing my portfolio?",
        "ranked_risks",
    ),
    AnalyticalBenchmark(
        "B3",
        "Argue against my portfolio.",
        "devils_advocate",
    ),
    AnalyticalBenchmark(
        "B4",
        "What would Ray Dalio think of this portfolio?",
        "philosophy_lens",
    ),
    AnalyticalBenchmark(
        "B5",
        "Compare my portfolio to a university endowment.",
        "peer_compare",
    ),
    AnalyticalBenchmark(
        "B6",
        "If inflation remains elevated for five years, what changes would you make?",
        "conditional_macro",
    ),
)
