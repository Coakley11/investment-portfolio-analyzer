"""Scenario stress inputs — shared drawdown parsing and portfolio/macro snapshot."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from investment_ami_exposure import resolve_tech_exposure
from investment_ami_instant_solver import _parse_weight_pct, _weight_rows

from investment_ami.engines.support.macro_context import resolve_macro_scenario_context

_DEFENSIVE_TICKERS = frozenset({"BND", "AGG", "TLT", "BIL", "SCHZ", "IEF"})


def parse_scenario_drawdown_pct(
    ctx: dict[str, Any],
    *,
    question: str = "",
    default: float = 20.0,
) -> float:
    """Resolve tech/scenario drawdown % from params or question text (never raises)."""
    params = dict(ctx.get("scenario_params") or {})
    raw = params.get("tech_drawdown_pct")
    parsed = _parse_weight_pct(raw)
    if parsed is not None and 0 < parsed <= 100:
        return parsed
    if isinstance(raw, (int, float)) and 0 < float(raw) <= 100:
        return float(raw)
    q = str(question or ctx.get("question") or "").strip().lower()
    for pattern in (
        r"(?:fall|falls|drop|drops|decline|declines|down)[^\d%]{0,24}(\d+(?:\.\d+)?)\s*%?",
        r"(\d+(?:\.\d+)?)\s*%\s*(?:drop|drawdown|fall|decline)",
        r"tech[^\d%]{0,20}(\d+(?:\.\d+)?)\s*%?",
    ):
        match = re.search(pattern, q, flags=re.IGNORECASE)
        if match:
            try:
                val = float(match.group(1))
                if 0 < val <= 100:
                    return val
            except (TypeError, ValueError):
                continue
    return default


@dataclass(frozen=True)
class ScenarioStressSnapshot:
    tech_drawdown_pct: float
    rate_shock: str
    direct_tech_pct: float
    embedded_tech_pct: float
    total_tech_pct: float
    embedded_holdings: tuple[dict[str, Any], ...]
    bond_defensive_pct: float
    equity_sleeve_pct: float
    illustrative_impact_pct: float


def build_scenario_stress_snapshot(
    context: dict[str, Any],
    *,
    question: str = "",
    default_drawdown_pct: float = 20.0,
) -> ScenarioStressSnapshot:
    """Combine macro context, tech exposure, and weight rows for scenario stress engines."""
    ctx = dict(context or {})
    macro = resolve_macro_scenario_context(ctx)
    tech_dd = parse_scenario_drawdown_pct(ctx, question=question, default=default_drawdown_pct)
    rate_shock = str(
        macro.scenario_params.get("rate_shock") or macro.rate_environment or ""
    ).strip()
    rows = _weight_rows(ctx)
    exposure = resolve_tech_exposure(ctx)
    direct_pct = float(exposure.get("direct_pct") or 0)
    embedded_pct = float(exposure.get("embedded_pct") or 0)
    total_tech_pct = float(exposure.get("total_pct") or direct_pct + embedded_pct)
    embedded_holdings = tuple(
        h for h in (exposure.get("embedded_holdings") or []) if isinstance(h, dict)
    )
    bond_pct = sum(p for t, p in rows if t in _DEFENSIVE_TICKERS)
    equity_pct = max(0.0, 100.0 - bond_pct) if rows else 0.0
    tech_impact = total_tech_pct * (tech_dd / 100.0)
    return ScenarioStressSnapshot(
        tech_drawdown_pct=tech_dd,
        rate_shock=rate_shock,
        direct_tech_pct=direct_pct,
        embedded_tech_pct=embedded_pct,
        total_tech_pct=total_tech_pct,
        embedded_holdings=embedded_holdings,
        bond_defensive_pct=bond_pct,
        equity_sleeve_pct=equity_pct,
        illustrative_impact_pct=tech_impact,
    )
