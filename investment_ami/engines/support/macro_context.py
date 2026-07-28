"""Shared macro scenario context for AMI engines (P2+)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from investment_ami.engines.support.macro_intelligence import MacroIntelligenceBrief


@dataclass(frozen=True)
class MacroScenarioContext:
    """
    Portfolio + scenario settings for macro-sensitive engines.

    Valuation, scenario stress, and future decision-support modules should prefer
    ``resolve_macro_scenario_context()`` over reading ``scenario_params`` ad hoc.
    """

    scenario_params: dict[str, Any]
    allocation_profile: dict[str, float | int | str]
    weight_rows: tuple[tuple[str, float], ...]
    rate_environment: str
    economic_regime: str
    recession_probability: float | None
    valuation_environment: str

    @property
    def has_portfolio_weights(self) -> bool:
        prof = self.allocation_profile
        total = (
            float(prof.get("equity") or 0)
            + float(prof.get("bonds") or 0)
            + float(prof.get("reit") or 0)
            + float(prof.get("tbills") or 0)
        )
        return total > 0


def resolve_macro_scenario_context(context: dict[str, Any] | None) -> MacroScenarioContext:
    """Build macro context from an AMI instant-solver context dict."""
    ctx = dict(context or {})
    from investment_ami_instant_solver import _weight_rows
    from investment_ami_macro import allocation_profile_from_ctx, _recession_probability_from_ctx

    params = dict(ctx.get("scenario_params") or {})
    profile = allocation_profile_from_ctx(ctx)
    rows = tuple(_weight_rows(ctx))
    rate_env = str(ctx.get("health_rate_env") or params.get("rate_shock") or "").strip()
    regime = str(ctx.get("health_regime") or params.get("economic_regime") or "").strip()
    recession_prob = _recession_probability_from_ctx(ctx)
    valuation_env = str(
        ctx.get("health_valuation") or params.get("valuation_environment") or "Fair Value"
    ).strip() or "Fair Value"

    return MacroScenarioContext(
        scenario_params=params,
        allocation_profile=profile,
        weight_rows=rows,
        rate_environment=rate_env,
        economic_regime=regime,
        recession_probability=recession_prob,
        valuation_environment=valuation_env,
    )


def resolve_macro_intelligence(
    context: dict[str, Any] | None,
    *,
    macro_intent: str,
    question: str = "",
) -> MacroIntelligenceBrief:
    """Build canonical macro intelligence brief for instant macro engines."""
    from investment_ami.engines.support.macro_intelligence import build_macro_intelligence_brief

    return build_macro_intelligence_brief(
        context,
        macro_intent=macro_intent,
        question=question,
    )
