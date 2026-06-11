# Investment Portfolio Analyzer — Acceptance Matrix

**Last updated:** 2026-06-11  
**Status:** Deploy marker `investment-insight-hydrate-v2` (local, not yet pushed) · Tests A–C **PASS** (frozen) · Tests **D** and **E** **REOPENED** — live regressions: AMI label/hydrate, portfolio revert, workflow greens  
**Audit:** [INVESTMENT_PERSISTENCE_AUDIT.md](./INVESTMENT_PERSISTENCE_AUDIT.md)  
**Plan:** [../cursor-prompts/plans/investment-sync-architecture-plan.md](../cursor-prompts/plans/investment-sync-architecture-plan.md)

Legend: **PASS** · **PARTIAL** · **FAIL** · **N/A** · **PLANNED**

Music Tests A–E are **frozen**. Investment defines a parallel A–E protocol scoped to portfolio/tab sync — not a copy of Music studio pages.

---

## Cross-cutting tests (Investment A–E)

| Test | Goal | Primary keys / blobs | Phone → Dell procedure | Current status |
|------|------|----------------------|------------------------|----------------|
| **A** | Page / tab sync | `investment_active_tab`, `health_active_tab` | Set non-default tab (e.g. ③ Build Portfolio) → wait for `tab_change` save → hard refresh other device | **PASS** — frozen 2026-06-11 (PR2 scope A `c4bb94b`); re-open only on trace regression |
| **B** | Global sidebar settings sync | `experience`, `_suite_persisted_experience`, `sidebar_portfolio_value`, `analysis_start`/`analysis_end`, `risk_free_pct`, `portfolio_preset` | Change global sidebar settings on Dell → save trace → hard refresh phone → compare Test B block | **PASS** — frozen 2026-06-11 (PR2 scope B `7dc3595`); re-open only on trace regression |
| **C** | Page-specific filters sync | `overview_subtab`, `mc_assumption_mode`, `health_run_optimizer`, `health_bond_min`, `frontier_points`, macro keys | Set non-default filters on Dell → wait 8–10s → Test C block → phone hard refresh → compare | **PASS** — frozen 2026-06-11; re-open only on trace regression |
| **D** | Portfolio / ticker / analysis restore | `holdings_df`, `holdings_fingerprint`, `preset_applied`, `health_objective`, `workflow_state`, `health_summary` | Custom holdings (50% VYM / 50% BND) → confirm fingerprints match → phone hard refresh after AMI | **REOPENED** — 50/50 reverted to default mix post-AMI; holdings default guard + `portfolio_change` re-verify |
| **E** | AMI return restores investment state | `applied_math_context` source_state → session, insight card hydrate | Dell AMI from Portfolio Health → insight on source tab → phone hard refresh hydrates same card | **REOPENED** — label still generic on live (`64c4395`); phone missing insight card; §8 trace required |

---

## Test A — Page / tab sync

**Status: PASS (frozen 2026-06-11)** — Do not re-test unless a future trace shows regression.

### Evidence (Dell → phone)
- Dell save: `saved_tab` = `cloud_readback_tab` = **③ Build Portfolio**
- Phone restore: `cloud_fetch_tab` = `restored_tab` = `final_investment_tab` = **③ Build Portfolio**
- Fix: PR2 scope A — `notify_investment_tab_change()` + `tab_change` autosave (`c4bb94b`)

### Scope
- Active section (`investment_active_tab`) survives refresh, reboot, and cross-device restore
- Beginner ↔ Advanced label normalization does not bounce user to wrong section index
- Continue / deep link (`suite_page`, `_suite_investment_page`) lands on correct tab

### Setup (manual) — archived
1. Device A: open Investment (Beginner or Advanced)
2. Navigate to non-default tab (e.g. **③ Build Portfolio**)
3. Confirm save trace: `save_reason: tab_change`, `saved_tab` = `cloud_readback_tab`
4. Device B: hard refresh (no interaction)

### Pass criteria
- `investment_active_tab` on B matches A
- PR1 Test A copy block: `cloud_fetch_tab`, `restored_tab`, `final_investment_tab` all match
- `cloud_updated_at` advances on Device A after tab change

### Target module (future)
- `investment_nav_state.py` (optional refactor; not required while PASS frozen)

---

## Test B — Global sidebar settings sync

**Status: PASS (frozen 2026-06-11)** — Do not re-test unless a future trace shows regression.

### Evidence (Dell → phone)
- Dell: `sidebar_portfolio_value=250000`, `risk_free_pct=3.5`, `analysis_start=2020-01-01`, `analysis_end=2025-12-31`, `experience=Advanced Mode`
- Phone matched all Test B fields including `portfolio_preset=— custom —`
- Fix: PR2 scope B — widget keys + `global_setting_change` autosave (`7dc3595`)

### Scope (Test B trace fields)
| Setting | Session key | Test B trace label |
|---------|-------------|-------------------|
| Experience mode | `experience`, `_suite_persisted_experience` | same |
| Portfolio value | `sidebar_portfolio_value` | `sidebar_portfolio_value` |
| Historical start | `analysis_start_date` | `analysis_start` |
| Historical end | `analysis_end_date` | `analysis_end` |
| Risk-free rate (%) | `risk_free_pct` | `risk_free_pct` |
| Strategy preset | `portfolio_preset` | `portfolio_preset` |

### Setup (Device A — Dell)
1. Open Investment dev (PR1 trace visible).
2. Set **non-default** global settings (suggested baseline values):
   - **Experience:** Advanced Mode (or switch Beginner → Advanced to force `mode_change` save)
   - **Portfolio value:** `$250,000`
   - **Historical lookback:** e.g. start `2020-01-01`, end `2025-12-31`
   - **Risk-free rate:** `3.5%`
   - **Portfolio preset:** any non-default selection (e.g. **Balanced** in selectbox — do not need Apply preset for Test B unless testing holdings)
3. Wait **≥10s** for end-of-run autosave **or** toggle experience to force immediate save.
4. Open **Investment persistence trace** → section **8. Save/autosave trace**:
   - Confirm `save_reason` (expect `mode_change` and/or `end_of_run`)
   - Note `saved_tab` / `cloud_readback_*` if present
5. Copy **Test B — global settings sync** block from Device A.

### Setup (Device B — phone)
1. Hard refresh Investment (no edits).
2. Copy **Test B** block from Device B.

### Pass criteria
- All Test B fields match Dell → phone:
  - `experience`, `_suite_persisted_experience`
  - `sidebar_portfolio_value`
  - `analysis_start`, `analysis_end`
  - `risk_free_pct`
  - `portfolio_preset`
- `cloud_updated_at` on phone reflects Dell save time (not stale)
- Save trace on Dell shows settings in blob (section 4. Global settings trace)

### Watch items (pre-baseline)
- **Experience** has immediate `mode_change` save; other fields may rely on end-of-run autosave only.
- **`risk_free_pct`:** sidebar slider may not bind to session key — verify trace shows changed value on Dell before phone compare.
- If Dell trace shows correct values but phone does not → classify **receiver restore** (not Device A).
- If Dell `cloud_readback_*` ≠ widget values → classify **Device A save** (same pattern as Test A before scope A).

### Known failures (historical)
- Stale in-memory session vs newer cloud (`stale_session_likely`)
- End-of-run autosave skipped when `investment_cloud_resync_needed` true without `local_dirty`

### Target module (future — only if baseline fails on Device A save)
- Scoped `settings_change` autosave (mirror `tab_change`); no broad restore refactor until baseline classifies failure

---

## Test C — Page-specific filters sync

**Status: PASS (frozen 2026-06-11)** — Do not re-test unless a future trace shows regression.

### Evidence (Dell → phone)
- Phone Test C block matched Dell on all filter fields.
- No scoped PR2 code required — existing persistence path sufficient for baseline.

### Baseline procedure (archived)

### Scope (Test C trace fields)

| Trace label | Session key | Where to set (Advanced) |
|-------------|-------------|-------------------------|
| `overview_subtab` | `overview_subtab` | **Overview** tab → subtab radio |
| `mc_assumption_mode` | `mc_assumption_mode` | **Monte Carlo** tab → assumption mode radio |
| `health_run_optimizer` | `health_run_optimizer` | **Portfolio Health** tab → run optimizer checkbox |
| `health_bond_min` | `health_bond_min` | **Portfolio Health** tab → bond min slider |
| `frontier_points` | `frontier_points` | Sidebar **Performance** → frontier granularity (Advanced only) |
| `macro_scenario_id` | `macro_scenario_id` | Macro panel (Health / Forward Macro) |
| `macro_scenario_mode` | `macro_scenario_mode` | Macro panel |
| `health_rate_env` | `health_rate_env` | **Portfolio Health** → macro assumptions |
| `health_inflation` | `health_inflation` | same |
| `health_recession` | `health_recession` | same (slider %) |
| `health_valuation` | `health_valuation` | same |
| `health_regime` | `health_regime` | same |

`final_investment_tab` is included in the Test C block for context (which tab was active at capture).

### Setup (Device A — Dell)

1. Open Investment dev (**Advanced Mode** recommended — frontier + full tab set).
2. Set **obvious non-default** filters (suggested baseline):
   - **Overview** → subtab e.g. **Risk** (not default)
   - **Portfolio Health** → bond min **10%**, optimizer **on**, macro: recession **40%**, rate env **Rising Rates**, inflation **High Inflation**, valuation **Overvalued**, regime **Late Cycle**
   - **Monte Carlo** → assumption **Forward macro-adjusted** (not Historical)
   - Sidebar **Frontier granularity** → **500** (not 2000)
3. Wait **8–10 seconds** for autosave (or navigate tabs to trigger reruns).
4. Open trace → **6. Filter trace** — confirm Dell values match widgets.
5. Copy **Test C — page filters sync** block from Dell.

### Setup (Device B — phone)

1. Hard refresh (no edits).
2. Copy **Test C** block from phone.

### Pass criteria

- All Test C fields match Dell → phone.
- `cloud_updated_at` on phone reflects Dell save (not stale).

### Classification

| Observation | Classify as |
|-------------|-------------|
| Dell trace ≠ widget values after edit | **Device A** binding/save (scoped PR2 follow-up) |
| Dell correct, phone differs | **Receiver restore** (scoped PR2 follow-up) |

### Watch items (pre-baseline)

- Filter keys are in `_PERSIST_SCALAR_KEYS` but there is **no `filter_change` autosave** yet (unlike `tab_change` / `global_setting_change`) — may rely on end-of-run save.
- Visit tabs that own each widget before copying Test C (trace snapshots live session).
- Macro keys are shared across Health + Forward Macro views.

### Known gaps (historical)

- `asset_preset` quick-add selectbox not widget-keyed — excluded from C
- Macro keys shared across Health + Forward — change on one affects both (by design)

---

## Test D — Portfolio / ticker / analysis restore

**Status: RE-VERIFY** — Test E exposed stale cloud portfolio; scoped `portfolio_change` autosave added. Re-confirm save/readback before re-running Test E.

### Failure that triggered re-verify (Test E prep)
- Expected cloud portfolio: `BND:50.0:Bonds|VYM:50.0:Dividend ETF`
- Cloud/phone showed stale: `BND:30.0:Bonds|VNQ:10.0:REIT|VTI:40.0:Equity|VXUS:20.0:Equity`
- Root cause: holdings edits relied on end-of-run autosave (no immediate `portfolio_change` save like A/B).

### Scoped fix (PR2 scope D — narrow)
- `notify_portfolio_change()` + `portfolio_change` autosave trigger (holdings editor + confirm + apply preset)
- Save trace: `saved_holdings_fingerprint`, `cloud_readback_holdings_fingerprint` in Test D block + §8 Save trace

### Re-verify procedure (Dell → phone)

### Scope (Test D trace fields)

| Trace label | Session / blob key | Notes |
|-------------|-------------------|-------|
| `holdings_fingerprint` | `holdings_fingerprint` | Hash of ticker + weight rows |
| `holdings_row_count` | derived from `holdings_df` | Row count at capture |
| `preset_applied` | `preset_applied` | Last preset name applied |
| `selected_portfolio` | `selected_portfolio` | Active portfolio selection |
| `health_objective` | `health_objective` | e.g. growth / income / balanced |
| `health_summary_exists` | `health_summary` | bool — summary dict persisted |
| `health_result_exists` | `health_result` | bool — full result object (may be absent cross-device) |
| `workflow_state_exists` | `workflow_state` | bool — checklist blob present |
| `restore_decision` | trace only | Receiver restore path taken |
| `page_overwrite_source` | trace only | What overwrote session on load |

Also verify **§5 Portfolio trace** in sidebar (same fields minus device/timestamp rows).

Underlying blob keys (not all in copy block): `holdings_df` records, `workflow_state.checklist`, `portfolio_analyzed`, `health_summary` dict.

### Setup (Device A — Dell)

1. Open Investment dev (**Advanced Mode**).
2. Navigate to **③ Build Portfolio** (or **Portfolio Inputs**).
3. Set **non-default holdings** (suggested baseline):
   - e.g. **50% VTI / 50% BND** (or any obvious non-default mix — not default SPY/BND 60/40)
   - Optionally apply a **preset** then tweak weights (sets `preset_applied` + custom fingerprint)
4. Set **health objective** to non-default (e.g. **Income**).
5. Run **Analyze** (Portfolio Health or workflow analyze step) — confirm checklist shows analyze complete.
6. Wait **8–10 seconds** for autosave.
7. Open trace → **§5 Portfolio trace** — confirm Dell values match UI:
   - `holdings_fingerprint` non-empty, `holdings_row_count` matches table
   - `health_objective` matches widget
   - `health_summary_exists` = true (if analyze ran)
   - `workflow_state_exists` = true
8. Copy **Test D — portfolio/analysis restore** block from Dell.

### Setup (Device B — phone)

1. Hard refresh (no edits).
2. Visually confirm holdings table + objective match Dell.
3. Copy **Test D** block from phone.

### Pass criteria

- `holdings_fingerprint` matches Dell → phone.
- `holdings_row_count` matches.
- `health_objective` matches.
- `preset_applied` / `selected_portfolio` match (if set on Dell).
- `health_summary_exists` and `workflow_state_exists` match.
- Holdings weights in UI match (tickers + %).
- `cloud_updated_at` on phone reflects Dell save (not stale).

### Acceptable partial pass

- `health_result_exists` = false on phone while Dell = true — **acceptable** if UI prompts re-run analysis and `health_summary_exists` + fingerprint still match (full `health_result` object is not always persisted cross-device).

### Classification

| Observation | Classify as |
|-------------|-------------|
| Dell trace ≠ widget/holdings after edit | **Device A** binding/save (scoped PR2 follow-up) |
| Dell correct, phone differs (fp, objective, holdings) | **Receiver restore** (scoped PR2 follow-up) |
| Fingerprint matches but UI table wrong | **Widget hydrate** — holdings editor not reading restored blob |

### Fail criteria

- Phone shows default SPY/BND when Dell had custom holdings.
- `holdings_fingerprint` mismatch without `_suite_holdings_fp_mismatch` trace explanation.
- Objective or checklist flags diverge with matching fingerprint.

### Watch items

- After holdings edit, confirm §8 Save trace shows `save_reason: portfolio_change` (not only `end_of_run`).
- `asset_preset` quick-add selectbox not widget-keyed — use manual ticker/weight edits or Apply preset for baseline.
- Analyze must complete on Dell before copy — `health_summary_exists` depends on analyze run.
- `health_result` object recompute on phone is expected; do not fail D solely on `health_result_exists` if summary + fp match.

### Known gaps (historical)

- `health_result` object missing cross-device — recompute expected (documented in audit).
- Holdings restore works in isolation; full analyze artifact sync is PARTIAL.

### Target module (future — only if baseline fails)

- `portfolio_state.py` (planned)

---

## Test E — AMI return restores investment state

**Status: INCONCLUSIVE (2026-06-11)** — AMI return not detected on Dell or phone. **Do not re-run until Test D cloud portfolio is current.**

### Baseline failure (observed)
- `ami_return_detected` = False, `return_context_keys` = empty
- `apply_source_state_attempted` / `apply_source_state_success` = empty
- Holdings fp reverted to stale cloud portfolio (see Test D re-verify)
- Likely causes: (A) portfolio not saved to cloud before AMI; (B) return did not use `?suite_ami_insight=` URL (manual nav skips hydrate)

### AMI launch path (round-trip — not in-page helper)
- **Sidebar:** `### Analyze with Applied Math` → question text → **`Send to Command Center`** (primary button)
- Creates `source_state` + resume URL to Applied Intelligence; return uses `?suite_ami_insight=` via Command Center insight link
- **Not** the in-page insight card alone (`render_suite_applied_math_insight` is return display only)

### AMI diagnostics (PR2 scope E — launch wiring)
| Field | When set |
|-------|----------|
| `ami_launch_button_clicked` | **Send to Command Center** clicked |
| `ami_launch_entrypoint` | `sidebar_analyze_with_applied_math` |
| `build_source_state_called` | `ensure_investment_source_state` / builder ran |
| `ami_launch_detected` | Successful send with source_state or action_url |
| `source_state_created` | Non-empty `source_state` in payload |
| `source_state_keys` | Top-level keys in source_state |
| `source_state_holdings_fingerprint` | `entity_params.holdings_fingerprint` |
| `return_url_generated` | Non-empty resume `action_url` |
| `return_url_has_suite_ami_insight` | True on return URL only (not launch URL) |
| `ami_return_detected` | Return hydrate (`?suite_ami_insight=`) or apply |
| `apply_source_state_*` | `apply_return_source_state` for investment |

### Re-baseline procedure (after Test D re-verify)

### Goal

Verify that when the user leaves Investment for an Applied Math Insight (AMI) workflow and returns, Investment restores the correct context instead of resetting or overwriting state.

### Scope (Test E trace fields)

| Trace label | Notes |
|-------------|-------|
| `ami_return_detected` | Return URL / navigation detected |
| `source_app_normalized` | Source app id (e.g. `investment`) |
| `current_investment_tab` | Tab at trace capture |
| `final_investment_tab` | Active tab after restore |
| `return_context_keys` | Keys in `_ami_return_context` |
| `apply_source_state_attempted` | `apply_source_state_to_session` ran |
| `apply_source_state_success` | Source state applied without error |
| `holdings_fingerprint` | Must match pre-AMI fingerprint |
| `page_overwrite_source` | Empty or AMI-specific — not cloud overwrite |
| `cloud_fetch_tab` | Tab from cloud fetch (receiver context) |
| `restored_tab` | Tab after cloud restore path |

Also spot-check frozen **Test B** fields (experience, dates, portfolio value) and **§5 Portfolio trace** after return.

Underlying: `build_source_state()` captures tab, objective, holdings fingerprint, health score; `apply_source_state_to_session()` restores widget params + tab.

### Setup (Device A — Dell)

1. Leave app in a **distinctive state** (build on frozen A–D baseline):
   - **Tab:** Portfolio Health (or another non-default tab)
   - **Portfolio:** current **50% VYM / 50% BND** (or other known custom mix from Test D)
   - **Mode:** Advanced Mode
   - **Global settings:** retain frozen Test B values (e.g. `$250k`, `3.5%` risk-free, custom date range)
2. Wait **8–10 seconds** for save.
3. **Trigger AMI flow:**
   - Click **Analyze with Applied Math** (or equivalent AMI entry on Portfolio Health)
   - Ask a simple AMI question; allow AMI context to load
4. **Return to Investment** (follow return link / Command Center navigation).
5. Copy **Test E — AMI return** block (+ **§5 Portfolio trace** if helpful).

### Expected on Dell return

- `ami_return_detected` = **True**
- `apply_source_state_attempted` = **True**
- `apply_source_state_success` = **True**
- `final_investment_tab` = tab before AMI (e.g. Portfolio Health)
- `holdings_fingerprint` = unchanged from pre-AMI
- `page_overwrite_source` = empty or AMI-specific (not generic cloud overwrite)

### Setup (Device B — phone)

1. After Dell return completes and cloud save settles, **hard refresh** (no edits).
2. Copy **Test E** block.

### Pass criteria

- Investment state survives AMI round-trip on Dell.
- `holdings_fingerprint` unchanged (Dell return + phone).
- Tab unchanged (`final_investment_tab` matches pre-AMI).
- Frozen Test B global settings unchanged.
- No spurious `page_overwrite_source` (no cloud-driven tab/holdings reset).
- No portfolio reset to defaults.
- No experience-mode reset.

### Classification

| Observation | Classify as |
|-------------|-------------|
| Dell return wrong (tab/fp/apply flags) | **AMI apply / source-side** (scoped PR2 follow-up) |
| Dell correct, phone wrong | **Receiver restore** (scoped PR2 follow-up) |
| Both correct | **Test E PASS / frozen** |

### Watch items (pre-baseline)

- `finalize_ami_return_restore` may not be wired for Investment (Music has it) — trace first, code only if baseline fails.
- AMI return may set `_ami_insight_return_preserve` — cloud restore should defer during active return (see `suite_user_persistence`).
- Copy Test E **immediately after return** on Dell — some flags are run-scoped.
- Phone step validates cloud persisted post-AMI state, not the AMI URL itself.

### Known gaps (historical)

- Audit: partial widget restore via `apply_source_state_to_session`; no full `hydrate_applied_math_insight` / `finalize_ami_return_restore` equivalent for Investment.
- Do **not** start broad persistence refactor until baseline classifies failure.

### Target module (future — only if baseline fails)

- AMI return wiring in `applied_math_return_insight.py` + `streamlit_app.py` workspace prepare

---

## Per-tab matrix (current baseline)

| Tab (Advanced) | A Tab | B Sidebar | C Filters | D Portfolio | E AMI | Canonical module |
|----------------|-------|-----------|-----------|-------------|-------|------------------|
| Getting Started | PARTIAL | N/A | N/A | N/A | N/A | — |
| Overview | PARTIAL | PASS | PASS | PASS | BASELINE | — |
| Portfolio Inputs | PARTIAL | PASS | N/A | PASS | BASELINE | holdings |
| Portfolio Analytics | PARTIAL | PASS | N/A | PASS | BASELINE | — |
| Portfolio Health | PARTIAL | PASS | PASS | PASS | BASELINE | health |
| Explain Portfolio | PARTIAL | N/A | N/A | N/A | PLANNED | — |
| Forward Macro | PARTIAL | PASS | PASS | N/A | PLANNED | macro |
| Monte Carlo | PARTIAL | PASS | PASS | N/A | PLANNED | — |
| Optimization | PARTIAL | PASS | PASS | N/A | PLANNED | — |
| Efficient Frontier | PARTIAL | PASS | PASS | N/A | PLANNED | — |

---

## Trace requirements (`?dev=1`)

See plan § Trace — required fields per test:

| Field group | Tests |
|-------------|-------|
| `final_tab`, `nav_target_tab`, `page_overwrite_source` | A, E |
| `experience`, `cloud_readback_experience`, `local_dirty` | B |
| `filter_*` snapshots per tab | C |
| `holdings_fingerprint`, `preset_applied`, `checklist` | D |
| `ami_return_*`, `source_state_tab` | E |

---

## Phase checklist

### Phase 1 — Audit ✅ (this document)
- [x] State inventory
- [x] Storage layer map
- [x] Investment A–E definitions
- [x] Gap ranking
- [x] Trace plan drafted

### Phase 2 — Trace + workspace bootstrap
- [x] `investment_persistence_trace.py` (PR1 `3b81e3d`)
- [x] PR1 trace visibility + cross-device render (`f0db478`)
- [ ] `prepare_investment_workspace()`

### Phase 3 — Canonical modules (planned)
- [ ] `investment_nav_state.py` (Test A)
- [ ] Global settings module (Test B)
- [ ] `portfolio_state.py` (Test D)
- [ ] AMI return wiring (Test E)

### Phase 4 — Manual sign-off
- [x] Test A PASS (frozen 2026-06-11 — PR2 scope A `c4bb94b`)
- [x] Test B PASS (frozen 2026-06-11 — PR2 scope B `7dc3595`)
- [x] Test C PASS (frozen 2026-06-11 — baseline passed without scoped PR2)
- [ ] Test D PASS (re-verify after `portfolio_change` autosave)
- [ ] Test E PASS (blocked on D + AMI return URL)
- [ ] Freeze Investment persistence baseline

---

## Verification commands (regression)

```bash
cd investment-portfolio-analyzer
python -m pytest tests/test_investment_persistent_state.py tests/test_workflow_persist_sync.py tests/test_restore_skip.py tests/test_applied_math_context.py -q
```

Manual: enable developer diagnostics → sidebar **Persistence diagnostics** → copy trace block before/after cross-device steps.
