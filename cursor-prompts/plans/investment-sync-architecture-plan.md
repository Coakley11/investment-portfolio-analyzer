# Investment App — Sync Architecture Plan (Phase 1)

**Last updated:** 2026-06-09  
**Status:** Planning only — **no implementation in this pass**  
**Repo:** `investment-portfolio-analyzer`  
**Related docs:**
- [docs/INVESTMENT_PERSISTENCE_AUDIT.md](../../docs/INVESTMENT_PERSISTENCE_AUDIT.md)
- [docs/INVESTMENT_ACCEPTANCE_MATRIX.md](../../docs/INVESTMENT_ACCEPTANCE_MATRIX.md)

**Constraints (user-mandated):**
- Do **not** change portfolio math, macro formulas, or calculations
- Do **not** mix UI polish / transparency work with sync architecture
- Do **not** modify Music app (frozen at maintenance)
- Audit and plan first; implement in focused PRs after review

---

## 1. Problem statement

Investment persists a flat `full_session` blob and uses `restore_once()` at bootstrap. Cross-device sync works for many scalars but has known gaps:

1. **Tab bounce** — `investment_active_tab` can be null or overwritten by widget init order
2. **Experience mode drift** — stale browser session vs newer cloud (diagnostics hypotheses A/B/C)
3. **Analysis object gap** — `health_result` not serializable; checklist can show analyzed without live object
4. **No workspace protocol** — Music uses `prepare_music_workspace()` + ownership; Investment does not
5. **Fragmented trace** — debug keys scattered; no `?dev=1` compare block like Music Test D
6. **AMI return incomplete** — `build_source_state` exists; hydrate/return pipeline missing

---

## 2. Target architecture (mirror Music patterns, Investment semantics)

```
streamlit_app.py
    │
    ├─ apply_suite_resume_launch("investment")     [URL — unchanged]
    │
    ├─ prepare_investment_workspace(st)             [NEW — like Music]
    │     └─ sync_workspace_protocol(
    │            apply_state=apply_investment_disk_state,
    │            cloud_resync_needed=investment_cloud_resync_needed,
    │        )
    │
    ├─ prepare_investment_canonical_state(ss)       [NEW — reconcile modules]
    │     ├─ investment_nav_state.prepare_tab_nav()
    │     ├─ portfolio_state.prepare_portfolio_context()
    │     └─ investment_global_settings.prepare_globals()
    │
    ├─ sidebar + tab radio (after prepare)
    │
    └─ end-of-run: autosave + flush deferred nav save
```

### Planned modules (new files — Phase 2+)

| Module | Owns | Tests |
|--------|------|-------|
| `investment_nav_state.py` | `investment_active_tab`, user tab ownership, AMI/continue tab preserve | A, E |
| `investment_global_settings_state.py` | experience, dates, risk_free, sidebar_portfolio_value | B |
| `portfolio_state.py` | holdings_df, fingerprint, preset, objective, workflow checklist | D |
| `investment_persistence_trace.py` | `?dev=1` trace read/write/render | All |
| `investment_macro_state.py` (optional) | macro assumption keys | C |

**Not in scope:** changing `portfolio_core.py`, `macro_engine.py`, or calculation transparency UI.

---

## 3. Investment Tests A–E (implementation mapping)

### Test A — Page / tab sync

**Acceptance:** Non-default tab on phone appears on Dell after hard refresh; Continue/deep link opens correct tab; no bounce to tab 0 after restore.

**Implementation tasks:**
1. `investment_nav_state.write_canonical_tab()` — single write path for `investment_active_tab`
2. `mark_investment_tab_local_edit()` — dirty flag during manual tab change
3. `resolve_tab_for_restore()` — respect user nav + AMI return + `suite_page`
4. Move `ensure_investment_active_tab()` to run **after** `prepare_investment_workspace`, **before** radio widget
5. Normalize beginner/advanced labels by **index** internally; persist mode-specific label

**Tests to add:**
- `tests/test_investment_nav_state.py` — restore preserves tab, user nav blocks cloud
- `tests/test_investment_tab_restore.py` — beginner/advanced label normalization

---

### Test B — Global sidebar settings sync

**Acceptance:** Experience mode, portfolio value, analysis dates, risk-free rate sync cross-device.

**Implementation tasks:**
1. Extract global keys from flat `_PERSIST_SCALAR_KEYS` into `investment_global_settings_state`
2. `prepare_global_settings()` — reconcile widget vs persisted vs cloud (like Music `prepare_active_song_context` pattern)
3. Keep `sync_experience_after_widget` immediate save on mode change
4. Wire `claim_user_settings_ownership` during sidebar edits (local dirty until cloud readback)

**Tests to add:**
- `tests/test_investment_global_settings_state.py` — phone/Dell field round-trip

---

### Test C — Page-specific filters sync

**Acceptance:** Tab-local filters (overview subtab, MC mode, health optimizer flags, macro assumptions) survive cross-device.

**Implementation tasks:**
1. Document filter key ownership per tab (audit §3.6 — done)
2. `capture_tab_filters_snapshot(tab_id)` / `restore_tab_filters` in page-local prefixes
3. Ensure `apply_investment_disk_state` does not apply wrong-tab filters when tab differs (optional namespacing later)

**Pragmatic Phase 2 approach:** Keep flat scalar persist (already works) but add trace fields to prove no overwrite — minimal code churn.

**Tests to add:**
- `tests/test_investment_filter_persist.py` — macro + overview + MC keys round-trip

---

### Test D — Portfolio / ticker / analysis restore

**Acceptance:** Custom holdings, preset, objective, workflow checklist, and `health_summary` restore; analysis recomputes cleanly when `health_result` missing.

**Implementation tasks:**
1. `portfolio_state.py` — canonical holdings + fingerprint + objective
2. `apply_cloud_portfolio_state_if_allowed()` — skip when local dirty
3. On restore when `_restored_analysis_without_object()`: set `request_portfolio_analyze` or show re-analyze banner (UX only if needed — optional)
4. Fix `asset_preset` selectbox — add `key="asset_preset"` in sidebar

**Tests to add:**
- Extend `tests/test_workflow_persist_sync.py` for holdings + objective
- `tests/test_portfolio_state_restore.py`

---

### Test E — AMI return restores investment state

**Acceptance:** Send insight from Portfolio Health → return link → same tab, holdings, objective.

**Implementation tasks:**
1. Port Music patterns: `hydrate_applied_math_insight_for_session(st, "investment")`
2. `finalize_ami_return_restore(st, "investment")` after workspace prepare
3. `apply_studio_nav_source_state_from_ami` equivalent for investment tab
4. `investment_nav_state.apply_ami_return_tab()` — preserve tab over cloud blob
5. Eligible pages in `applied_math_return_insight.INSIGHT_ELIGIBLE_PAGES["investment"]`

**Tests to add:**
- `tests/test_investment_ami_return.py` — source_state round-trip
- Mirror `tests/test_insight_comparison_return.py` patterns from Command Center

---

## 4. Trace plan — `investment_persistence_trace.py`

Proposed module (not yet created). Mirror `music_persistence_trace.py` shape.

### Activation
- `?dev=1` query param sets `st.session_state["developer_mode"] = True`
- Sidebar expander: **Investment persistence trace** (alongside existing diagnostics)

### Trace keys

#### Workspace restore trace (all tests)
```
cloud_fetch_tab
restore_intermediate_tab
restored_tab
restored_tab_source
final_tab
page_overwrite_source
workspace_sync_attempted
workspace_restore_applied
restore_skip_reason
cloud_updated_at
local_updated_at
```

#### Navigation / tab trace (Test A)
```
nav_target_tab
active_tab_source          # user_sidebar | cloud_restore | ami_return | suite_resume
pre_restore_tab
post_restore_tab
investment_nav_dirty
suite_page_user_nav
```

#### Global settings trace (Test B)
```
experience_widget
experience_persisted
cloud_readback_experience
sidebar_portfolio_value
analysis_start_date
analysis_end_date
risk_free_pct
local_dirty
pending_experience_mode
end_of_run_autosave_blocked
```

#### Filter trace (Test C)
```
overview_subtab
overview_show_extended_metrics
mc_assumption_mode
health_run_optimizer
health_bond_min
health_rate_env
health_inflation
health_recession
health_valuation
health_regime
macro_scenario_id
```

#### Portfolio trace (Test D)
```
holdings_fingerprint
preset_applied
health_objective
portfolio_built
portfolio_analyzed
portfolio_health_reviewed
health_summary_score
health_result_present
health_result_fingerprint
workflow_checklist_json
holdings_restore_issue
holdings_fp_confirmed
holdings_fp_mismatch
```

#### AMI return trace (Test E)
```
ami_return_navigation_active
ami_return_source_page
ami_return_holdings_fp
restored_tab_from_ami
manual_nav_after_ami_return
```

#### Save trace
```
autosave_trigger
autosave_outcome
blob_experience
cloud_readback_ts
fp_before
fp_after
force_save_reason
```

### Copy blocks (manual QA)
- **Test B compare** — experience + portfolio value + dates + risk_free
- **Test D compare** — fingerprint + objective + checklist + health_summary
- **Test E compare** — before send / after return AMI fields

### Integration
- `record_investment_workspace_restore_trace()` — called from `prepare_investment_workspace`
- `update_trace(st, **fields)` — called from autosave, tab change, AMI return
- `render_persistence_trace_sidebar(st)` — unified expander (may wrap existing `render_persistence_debug_sidebar` initially)

---

## 5. Implementation phases (recommended PR sequence)

| PR | Scope | Risk | Tests |
|----|-------|------|-------|
| **PR1** | `investment_persistence_trace.py` + `?dev=1` + copy blocks | Low | Unit trace tests |
| **PR2** | `prepare_investment_workspace()` wrapping `sync_workspace_protocol` | Medium | Extend `test_restore_skip` |
| **PR3** | `investment_nav_state.py` — Test A | Medium | `test_investment_nav_state` |
| **PR4** | Global settings module — Test B | Medium | New unit tests |
| **PR5** | `portfolio_state.py` — Test D + asset_preset key fix | Medium | Workflow + holdings tests |
| **PR6** | AMI return wiring — Test E | Medium | AMI return tests |
| **PR7** | Filter trace + overwrite guards — Test C | Low | Filter persist tests |

**Do not combine** calculation changes, UI polish, or Command Center suite sync script updates in the same PRs.

---

## 6. Bootstrap order fix (critical — no new features)

Current order in `streamlit_app.py`:

```
apply_suite_resume_launch → restore_once → sidebar → … → tab radio
```

Target order:

```
apply_suite_resume_launch
prepare_investment_workspace          # NEW
prepare_investment_canonical_state    # NEW
ensure_experience_mode
sidebar (widgets)
ensure_investment_active_tab
tab radio / workflow navigator
… page bodies …
flush_deferred_tab_save               # if history/AMI defer pattern needed
autosave_investment_state(end_of_run=True)
update_investment_persistence_trace()
```

This mirrors the Music fix: **commit navigation target before workspace restore consumes stale cloud.**

---

## 7. Suite module sync note

Investment ships its own copy of:
- `suite_user_persistence.py`
- `suite_cloud_state.py`
- `suite_resume_launch.py`
- `applied_math_return_insight.py`

Command Center `scripts/sync_suite_cloud_modules.py` may not sync all files. Before Phase 2:

1. Diff Investment vs Command Center suite modules
2. Port only persistence-related fixes (not Music-specific nav history)
3. Document in PR description — no drive-by refactors

---

## 8. Music app status (context)

Music live sign-off **PASSED** (2026-06-09):
- Tests A–E frozen
- UI polish accepted
- Back/Forward live navigation PASSED
- Maintenance / future polish only

Investment work proceeds **independently** in `investment-portfolio-analyzer` on `dev`.

---

## 9. Success criteria (Phase complete)

Investment sync Phase is complete when:

1. Manual Tests **A–E** marked PASS in `INVESTMENT_ACCEPTANCE_MATRIX.md`
2. `investment_persistence_trace` copy blocks used for phone ↔ Dell sign-off
3. `docs/INVESTMENT_PERSISTENCE_BASELINE.md` frozen (to be created at sign-off)
4. No regressions in existing pytest suite
5. User explicitly freezes Investment persistence before UI polish resume

---

## 10. Open questions (for user review)

1. **Tab persist strategy:** Store tab by **index** (0–9) internally vs label string? (Recommend index + mode for label rendering.)
2. **Analysis object:** Accept re-analyze on cross-device when fingerprint matches, or invest in serializing `health_summary` only? (Recommend summary + fingerprint + user prompt — no object serialize.)
3. **Dev trace default:** Merge into existing developer diagnostics toggle or separate `?dev=1` only?
4. **PR sequencing:** Approve PR1 (trace only) as first implementation slice?

---

## 11. Files referenced (audit anchors)

| Path | Role |
|------|------|
| `streamlit_app.py` | Entry, sidebar, tab dispatch |
| `investment_persistent_state.py` | Build/apply blob, autosave, restore |
| `investment_workflow.py` | Workflow blob, checklist, stale steps |
| `applied_math_context.py` | AMI build/apply source_state |
| `suite_resume_launch.py` | URL resume → `_suite_investment_page` |
| `suite_user_persistence.py` | `restore_once`, `sync_workspace_protocol` |
| `components/beginner_navigation.py` | Tab labels, normalization |
| `components/workflow_navigator.py` | Tab navigation side effects |

No code changes made in Phase 1 planning pass.
