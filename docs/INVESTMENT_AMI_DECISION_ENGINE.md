# Investment AMI decision engine (P1)

Orchestration lives in the ``investment_ami`` package. Legacy solvers and phrase routing in ``investment_ami_context.py`` are unchanged.

## P1 flow

```
solve_instant_investment_insight()
  → investment_ami.integration.instant_solver_facade.solve_instant_insight()
      → routing.router.route_instant_question()  # catalog + legacy detect
      → investment_ami_instant_solver._solve_instant_investment_insight_core()
      → assembly.legacy_adapter.attach_routing_metadata()  # computed keys only
```

## Modules

| Path | Role |
|------|------|
| ``investment_ami/models/`` | ``AmiQuestionDefinition``, ``RoutedQuestion``, ``AmiDecisionResponse`` |
| ``investment_ami/catalog/`` | Registry generated from legacy intents |
| ``investment_ami/routing/router.py`` | Wraps ``detect_investment_send_intent`` |
| ``investment_ami/integration/instant_solver_facade.py`` | Public orchestration entry |
| ``investment_ami/assembly/legacy_adapter.py`` | Legacy ↔ canonical mapping (P1 metadata only) |

## Backward compatibility

- All existing imports from ``investment_ami_instant_solver`` and ``investment_ami_context`` remain valid.
- Solver bodies stay in ``investment_ami_instant_solver.py``, ``investment_ami_phase2_solvers.py``, etc.
- P2+ adds pipeline steps and engines without rewriting phrase lists.

## P2 — Instant engines (complete)

Portfolio family: **DiversificationEngine**, **PortfolioConcentrationEngine**, **PortfolioRiskEngine**, **AssetAllocationEngine**. Specialized: **EtfOverlapEngine**, **MacroeconomicEngine**, **ValuationEngine**, **ScenarioStressEngine**, **EducationEngine**, **BehavioralFinanceEngine**.

Post-P2 architecture review: ``docs/INVESTMENT_AMI_ENGINE_ARCHITECTURE_REVIEW.md``.

```
solve_instant_insight()
  → route_instant_question()
  → _solve_instant_investment_insight_core()
      → solve_phase2_or_structured()
          → investment_ami.pipeline.instant.run_instant_engine("diversification", ...)
              → investment_ami.engines.diversification.DiversificationEngine
  → attach_routing_metadata() + ami_engine_id on computed
```

| Path | Role |
|------|------|
| ``investment_ami/engines/diversification.py`` | Diversification family |
| ``investment_ami/engines/portfolio_concentration.py`` | Portfolio concentration / ``portfolio_analysis`` catalog engine |
| ``investment_ami/engines/portfolio_risk.py`` | Portfolio risk / ``risk_analysis`` catalog engine |
| ``investment_ami/engines/asset_allocation.py`` | Allocation recommendation / ``asset_allocation`` catalog engine |
| ``investment_ami/engines/etf_overlap.py`` | ETF overlap instant engine |
| ``investment_ami/engines/macroeconomic.py`` | Macro scenario engine (rates / recession / inflation) |
| ``investment_ami/engines/valuation.py`` | Security valuation instant engine |
| ``investment_ami/engines/scenario_stress.py`` | Portfolio scenario / tech shock engine |
| ``investment_ami/engines/education.py`` | Investment education / coach engine |
| ``investment_ami/engines/behavioral_finance.py`` | Behavioral finance / risk-reduction engine |
| ``investment_ami/engines/support/scenario_stress_data.py`` | Drawdown parsing + ``ScenarioStressSnapshot`` |
| ``investment_ami/engines/support/education_content.py`` | Shared coach copy (definitions unchanged) |
| ``investment_ami/engines/support/behavioral_finance_content.py`` | Shared risk-reduction coaching copy |
| ``investment_ami/engines/support/macro_context.py`` | ``MacroScenarioContext`` + ``resolve_macro_scenario_context()`` |
| ``investment_ami/engines/support/valuation_helpers.py`` | Re-exports for ``resolve_valuation_context`` and related helpers |
| ``investment_ami/engines/support/overlap_data.py`` | Overlap pair resolution (``etf_holdings`` → market data provider) |
| ``investment_ami/engines/support/presentation.py`` | Shared educational risk disclaimers |
| ``investment_ami/pipeline/instant.py`` | Engine registry and ``run_instant_engine`` |
| ``investment_ami_phase2_solvers.diversification_answer`` | Thin backward-compatible wrapper |

Additional engines should follow the same pattern: implement engine → register → phase-2 wrapper delegates.
