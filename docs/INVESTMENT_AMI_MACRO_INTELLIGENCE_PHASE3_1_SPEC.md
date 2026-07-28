# Phase 3.1 — Macroeconomic Intelligence Implementation Specification

**Status:** Ready for implementation  
**Parent design:** `INVESTMENT_AMI_MACRO_INTELLIGENCE_PHASE3.md` (approved 2026-07-27)  
**Scope:** Intelligence + presentation only — **no** registry restructuring, **no** coefficient recalibration, **no** external macro indicator feeds  

---

## 1. Objectives

1. Introduce **`MacroIntelligenceBrief`** as the single canonical macro reasoning artifact.
2. Build **`MacroReasoningTrace`** with all approved trace sections (§6.2 of parent doc).
3. Render **compact Macro Outlook** at the top of every **`macro_rates`**, **`macro_recession`**, and **`macro_inflation`** answer.
4. Preserve existing **shock mathematics** in `investment_ami_macro.py` / `portfolio_core` (same coefficients and pp logic unless copy-only changes are approved in tests).
5. Attach brief + trace to **`InvestmentSolverResult.computed`** for UI, tests, and Phase 3.2 consumers.
6. Enrich narratives where they **follow from** the brief without contradicting existing golden behavior for quant fields.

---

## 2. Non-goals (Phase 3.1)

- New `macro_outlook` intent or routing changes.
- Full strategist dashboard UI (Phase 3.4).
- ValuationEngine / ScenarioStressEngine reading the brief (Phase 3.2).
- FRED or other live indicator ingestion (Phase 3.3).
- Changes to `INSTANT_ENGINE_REGISTRY` or engine class structure beyond calling new support functions.
- Recalibrating `portfolio_core._rate_environment_effects`, `_inflation_effects`, `_economic_regime_effects`, or `rate_rise_portfolio_impacts` / recession / inflation impact functions.

---

## 3. Module layout

| Path | Responsibility |
|------|----------------|
| `investment_ami/engines/support/macro_intelligence.py` | **`build_macro_intelligence_brief(context, *, macro_intent, question)`** — pipeline: scenario context → regime → channels → portfolio rank → trace → confidence |
| `investment_ami/engines/support/macro_outlook_render.py` | **`render_compact_macro_outlook(brief, *, beginner)`** and **`render_full_macro_outlook(brief, *, beginner)`** (full renderer stub for 3.4; compact used in 3.1) |
| `investment_ami/engines/support/macro_context.py` | Extend with **`resolve_macro_intelligence(context, *, macro_intent, question)`** delegating to brief builder (keeps `resolve_macro_scenario_context` unchanged) |

**Call site (Phase 3.1):** At the start of each `_macro_*_solve` in `investment_ami_macro.py`:

1. `brief = build_macro_intelligence_brief(ctx, macro_intent="macro_rates", question=question)` (etc.)
2. Prepend `render_compact_macro_outlook(brief, beginner=beginner)` to `short_answer` (or structured prefix separated by `\n\n`).
3. Merge trace + outlook fields into `result.computed`.
4. Optionally weave trace **final conclusion** into `analyst_sections` per experience mode rules.

Alternative approved pattern: brief built inside `MacroeconomicEngine.solve()` once per request and passed into solvers via ctx key `_macro_intelligence_brief` — **prefer single build in engine wrapper** to avoid triple build if solvers refactored later. For 3.1 minimal diff, building at top of each `_macro_*_solve` is acceptable if tests assert identical brief for same ctx across intents (regime must not depend on intent except **recommendation_drivers** and **final_conclusion** tail).

**Intent-specific trace tails:** Regime, drivers, risks, opportunities, evidence, confidence are **intent-invariant** for the same context. Only **recommendation_drivers** and **final_macro_conclusion** may reference the active intent (rates vs recession vs inflation).

---

## 4. Data structures

### 4.1 `MacroReasoningTrace` (dataclass, frozen)

```text
economic_regime: str          # Overall regime label
regime_rationale: str         # One sentence
supporting_evidence: tuple[str, ...]  # e.g. "Rate environment: Rising Rates"
key_drivers: tuple[str, ...]        # 2–4 bullets, no leading bullet char in storage
primary_risks: tuple[str, ...]
opportunities: tuple[str, ...]
recommendation_drivers: tuple[str, ...]
final_macro_conclusion: str
```

### 4.2 `MacroIntelligenceBrief` (dataclass, frozen)

```text
scenario: MacroScenarioContext   # existing type
trace: MacroReasoningTrace
confidence_pct: int              # 0–100, Outlook display
channel_ranks: tuple[tuple[str, float], ...]  # internal, optional in computed JSON
assumption_tensions: tuple[str, ...]            # empty in 3.1 unless logic detects slider conflicts
brief_version: str               # e.g. "3.1.0" for tests
```

### 4.3 `computed` keys (stable contract for 3.2)

| Key | Type | Description |
|-----|------|-------------|
| `ami_engine_id` | str | unchanged |
| `ami_macro_intent` | str | unchanged |
| `macro_brief_version` | str | brief version |
| `macro_outlook_regime` | str | trace.economic_regime |
| `macro_outlook_confidence` | int | brief.confidence_pct |
| `macro_outlook_compact` | str | rendered compact header (idempotent with short_answer prefix) |
| `macro_reasoning_trace` | dict | JSON-serializable trace sections |

Do not break existing computed keys for rate/recession/inflation scenarios (e.g. tech drawdown keys unaffected).

---

## 5. Regime and bullet generation (3.1 logic)

**Inputs only:** `MacroScenarioContext` fields + `allocation_profile` sleeves.

### 5.1 Regime scoring

Map combinations of:

- `rate_environment` (Falling / Stable / Rising / High Rate Environment)
- `inflation` (Deflation / Low / Moderate / High)
- `economic_regime` (Expansion, Recession, Credit Crisis, AI / Tech Boom, etc.)
- `recession_probability` (thresholds: e.g. ≥40% elevates late-cycle / recession stress language)

to approved **label enum** (parent doc § Macro Outlook). Default tie-break: **Neutral / Mixed**.

Example mapping (implementation detail, tunable in tests):

- Rising or High rates + Moderate/Low inflation + Expansion → **Moderately Restrictive**
- High Rate Environment → **Restrictive**
- Recession regime or recession_prob ≥ 50% → **Recession stress** (unless Credit Crisis → **Crisis / Liquidity stress**)
- High Inflation + Rising/High rates → **Stagflation stress**

### 5.2 Drivers, risks, opportunities

Use **template libraries** keyed by regime label + dominant **channel ranks** from profile:

| Channel | Profile signal |
|---------|----------------|
| Duration | `long_duration_bonds`, `bonds` |
| Growth / discount rate | `tech`, `qqq_spy`, growth proxy |
| REIT / housing rate | `reit` |
| Defensive | `tbills`, `dividend` |
| Cyclical equity | `equity` minus defensive |

- **Drivers:** 2–4 plain-English lines from regime templates (e.g. “Elevated interest rates” when Rising/High).
- **Risks:** merge regime templates + optional portfolio line if sleeve > threshold (e.g. bonds ≥ 20% → duration risk bullet).
- **Opportunities:** theme templates; if portfolio already heavy in a theme, swap to “maintain quality/diversification” monitor language (not “add more”).

**No verbatim hard-coded example block** — derive from rules so Health changes update Outlook.

### 5.3 Confidence (3.1)

Start from base **72**. Adjust:

| Condition | Δ |
|-----------|---|
| Portfolio weights present (has_portfolio_weights) | +8 |
| Missing weights | set cap **55** (align empty-portfolio macro answers) |
| Assumption tension detected (e.g. Expansion + recession_prob ≥ 45%) | −6 |
| Regime label confidence low (conflicting rate vs regime) | −4 |
| All Health macro fields present | +2 |

Clamp **45–88** for 3.1 (avoid claiming 95+). Intent-specific shock answers may keep legacy confidence on **body** or align body confidence with brief — **decision:** use `max(legacy_body_confidence, brief.confidence_pct)` or replace with brief confidence; spec recommends **single displayed confidence** = `brief.confidence_pct` on result for macro intents in 3.1 (update tests if legacy differed).

Document choice in PR: unify on brief confidence for consistency with Outlook header.

### 5.4 Recommendation drivers (intent-specific)

Examples:

- **macro_rates:** monitor duration, stress rate rise, revisit bond sleeve, check overlap on growth stacks
- **macro_recession:** review defensive allocation, stress recession scenario, trim concentration
- **macro_inflation:** review long bond exposure, real return framing, cash/T-bill role

Stored in trace; compact Outlook may show 0 in header (full dashboard shows in 3.4).

---

## 6. Compact Outlook format (exact layout)

Markdown text prepended to `short_answer`:

```text
**Macro Outlook**
**Overall Regime:** {regime}
**Key Drivers:** {driver1}; {driver2}[; {driver3}]
**Primary Risk:** {risk1}[; {risk2} for advanced]
**Opportunity:** {opp1}
**Confidence:** {confidence_pct}%
```

Beginner: max 2 drivers, 1 risk, 1 opportunity (semicolon-separated inline or short bullets — match existing AMI markdown style; prefer **bullets** if `build_analyst_sections` already uses bullets elsewhere for macro).

Intermediate/advanced compact: up to 3 drivers, 2 risks, 2 opportunities (still “compact” vs full dashboard).

Separator: `\n\n---\n\n` between Outlook header and intent-specific direct answer.

---

## 7. Integration with existing solvers

### 7.1 `investment_ami_macro.py`

For each `_macro_rates_solve`, `_macro_recession_solve`, `_macro_inflation_solve`:

1. Build brief (once).
2. Render compact header.
3. Run **existing** body logic unchanged for numeric `comps`, `net`, `prof`, etc.
4. Append/adjust analyst sections:
   - Inject trace **final_macro_conclusion** into `portfolio_analyst_view` prefix or new subsection **“Why AMI said this”** for intermediate+.
5. Set `computed` merge as §4.3.

### 7.2 `MacroeconomicEngine`

Optional: build brief here and inject into `ctx["_macro_intelligence_brief"]` before dispatch — reduces duplication. Either approach acceptable if tests cover parity.

### 7.3 `resolve_macro_scenario_context`

Unchanged signature. Brief builder **calls** it internally.

---

## 8. Testing strategy

### 8.1 New unit tests — `tests/test_investment_ami_macro_intelligence.py`

| Test | Assert |
|------|--------|
| Brief builds from minimal Health ctx | regime non-empty, trace sections populated |
| Same ctx → same regime across three intents | drivers/risks/opportunities identical |
| Intent changes recommendation_drivers / conclusion | different strings, same regime |
| Rising + Moderate inflation + Expansion | regime **Moderately Restrictive** (or approved mapping) |
| Missing weights | confidence ≤ 55 |
| Compact render contains regime + confidence | substring match |
| Trace JSON round-trip | all keys present |

### 8.2 Existing tests

- Run full investment AMI battery after implementation.
- **`test_investment_ami_macroeconomic_engine.py`:** update if confidence or short_answer prefix changes — use assertions on **body after separator** or computed keys for quant fields.
- **`test_investment_ami_phase2.py` / macro macro tests:** preserve numeric computed fields (`net_return_shift_pp`, etc.) — **must not change** shock math outputs.

### 8.3 Golden snapshots (optional)

Store normalized compact Outlook for one fixture ctx per regime label to prevent accidental copy drift.

---

## 9. Documentation updates (same PR as code)

- `INVESTMENT_AMI_DECISION_ENGINE.md` — link Phase 3.1 brief + Outlook header.
- `INVESTMENT_AMI_MACRO_INTELLIGENCE_PHASE3.md` — already approved; no further edits required unless implementation diverges.

---

## 10. Phase 3.2 handoff (not implemented in 3.1)

Prepare brief resolver for consumers:

```text
resolve_macro_intelligence(context) -> MacroIntelligenceBrief | None
```

ValuationEngine and ScenarioStressEngine will:

- Read `macro_outlook_regime`, `channel_ranks`, trace risks — or call resolver if brief not in computed.
- **Not** duplicate Outlook rendering.

---

## 11. Acceptance criteria (Phase 3.1 done)

- [ ] `build_macro_intelligence_brief` and trace dataclasses live in support module.
- [ ] Compact Macro Outlook appears on all three macro instant answers.
- [ ] Full Outlook renderer exists but is **not** routed (callable for tests / future intent).
- [ ] One brief builder; compact and full renderers read the same struct.
- [ ] `macro_reasoning_trace` in computed with all seven trace sections.
- [ ] Shock math outputs unchanged (same computed numeric fields as pre-3.1 for fixed fixtures).
- [ ] No new external data dependencies.
- [ ] All investment AMI tests pass (with approved updates for prefix/confidence only).
- [ ] New unit test file ≥ 8 cases covering regime, confidence, intent invariance, render.

---

## 12. Implementation order

1. Dataclasses + brief builder (pure functions, no Streamlit).
2. Regime + template libraries + confidence.
3. Compact renderer.
4. Wire into three `_macro_*_solve` functions + computed merge.
5. Analyst section / trace UX by experience mode.
6. Tests + doc links.
7. Full AMI pytest run.

---

## 13. Open implementation choices (resolve in PR, not blockers)

| Choice | Recommendation |
|--------|----------------|
| Build brief in engine vs each solver | Engine injects into ctx once |
| Unified vs dual confidence | Single `brief.confidence_pct` on result |
| Compact inline vs bullets | Bullets for drivers/risks/opportunities in intermediate+; single-line beginner |

---

*Approved by product owner 2026-07-27. Begin coding when explicitly requested.*
