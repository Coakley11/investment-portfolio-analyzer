# Investment AMI — Decision Support (Phase 1)

Extensible **rule-based** reasoning for personal finance questions (not portfolio ticker analysis).

## Layout

| Layer | Module | Role |
|-------|--------|------|
| Input | `decision_support/snapshot.py` | Build `FinancialSnapshot` from AMI submit context + plan |
| Analysis | `decision_support/analysis.py` | Run matched rules → `ReasoningFinding` list |
| Rules | `decision_support/rules/builtin.py` | Registered rules; add new classes + `register()` |
| Response | `decision_support/analysis.py` | Aggregate findings → `DecisionSupportResponse` |
| Explanation | `decision_support/explanation.py` | Markdown sections (facts, observations, actions, …) |
| Orchestration | `decision_support/pipeline.py` | `run_decision_support_module()` |
| Engines | `engines/allocation_advisor.py`, `engines/cash_reserve_advisor.py` | Instant AMI entry points |

## Intents

- `allocation_advisor` — how much to invest, contributions, DCA vs lump sum, debt vs invest, strategy critique
- `cash_reserve_advisor` — emergency fund, liquidity, job loss, expense/income shifts, major purchases

Phrase routing: `investment_ami_context.detect_investment_send_intent`.

## Adding a rule

1. Subclass pattern in `rules/builtin.py` (or new module imported at startup).
2. Implement `matches()` + `analyze()` → `ReasoningFinding`.
3. `GLOBAL_RULE_REGISTRY.register(rule)`.

Framework version: `decision_support/explanation.py` → `DECISION_SUPPORT_VERSION` (`ds-v1`).
