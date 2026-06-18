# Investment AMI Phase 2 Plan

**Status:** Phase 2a started (`investment-ami-v2-phase2a`)  
**Prerequisite:** Phase 1 milestone verified (canonical insight, immediate render, UX fixes)

---

## Identity

| App | Role |
|-----|------|
| Baseball | Quantitative optimizer — rankings, projections, optimization |
| **Investment** | Analyst + educator + scenario planner |
| Music | Coach / teacher — explanation-first |

---

## Answer structure (all Phase 2+ families)

| Section | Purpose |
|---------|---------|
| **Direct Answer** | One clear takeaway |
| **Portfolio Analyst View** | Interpretation in analyst voice |
| **Key Variables** | Holdings, weights, metrics used |
| **Tradeoffs** | Competing considerations |
| **What-If Scenarios** | Static shock / sensitivity (Advanced; simplified in Beginner) |
| **Recommended Actions** | Actionable next steps (educational, not advice) |
| **Risk Notes** | Assumptions + disclaimer |

Beginner mode: simpler labels, fewer metrics, shorter scenarios.

---

## Phase 2 rollout

### Phase 2a (current) — Structure + first new families

- [x] `investment_ami_answer_format.py` — section builder + markdown render
- [x] Structured depth for concentration + portfolio risk
- [x] New families: `etf_overlap`, `diversification`, `scenario_stress`
- [x] Context enrichment: `etf_overlap_pairs`, `asset_class_breakdown`, `scenario_params`
- [x] On-page + AMI canonical render of `analyst_sections`
- [x] Fix scenario_stress crash (`health_valuation` was wrongly mapped to `tech_drawdown_pct`)
- [ ] Cloud verification of structured cards

### Phase 2b — Valuation + stress testing

- Valuation questions (P/E, growth assumptions, ETF richness)
- Recession / rate-shock / sector drawdown templates
- Tie to macro engine + health assumptions

### Phase 2c — Interactive sliders

Sliders modify `scenario_params` in submit context:

| Control | Context key |
|---------|-------------|
| Risk tolerance | `risk_tolerance` |
| Allocation % | `allocation_pct` |
| Investment amount | `investment_amount` |
| Tech drawdown % | `tech_drawdown_pct` |
| Growth rate | `growth_rate` |
| Discount rate | `discount_rate` |
| Time horizon | `time_horizon` |
| Rebalance threshold | `rebalance_threshold` |

Unlike Music, Investment sliders directly change portfolio assumptions and scenario outputs.

---

## Accepted question families (Phase 2)

| Family | Example questions |
|--------|-------------------|
| ETF overlap | Should I own both VOO and QQQ? How much overlap? |
| Diversification | Am I diversified enough? What asset classes am I missing? |
| Sector exposure | Am I too exposed to tech? (Phase 1 — enhance with sections) |
| Valuation | Is this ETF expensive? What assumptions matter? |
| Scenario analysis | What if tech falls 20%? What if rates rise? |
| Stress testing | Recession scenario, rate shock, sector drawdown |

---

## Architecture (unchanged from Phase 1)

1. Local instant solver → on-page insight card
2. `store_applied_math_insight` with `canonical_instant=True`, `analyst_sections`
3. Context blob + resume URL include `instant_insight`
4. AMI loads canonical before re-solve
5. Baseball blueprint for submit; Music v5 pattern for canonical storage

---

## Test matrix (Phase 2a)

| # | Question | Expect |
|---|----------|--------|
| 1 | Is my portfolio too concentrated? | Structured sections; SCHD/weights cited |
| 2 | What is my biggest portfolio risk? | Analyst view + actions, not bullet-only |
| 3 | Should I own both VOO and QQQ? | Overlap % if context loaded |
| 4 | Am I diversified enough? | Asset-class breakdown |
| 5 | What happens if tech falls 20%? | Scenario impact estimate |
| 6 | Open full analysis | AMI shows same sections as on-page card |
| 7 | Beginner vs Advanced | Section depth differs |

---

## Deferred

- Full portfolio optimization (Baseball-style)
- Music-style coaching flows
- Investment sync/persistence architecture audit
