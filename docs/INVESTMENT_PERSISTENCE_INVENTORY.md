# Investment Explorer — persistence inventory

Last updated: 2026-07-31 (plan + AMI insight submit fixes).

Legend: **Y** = durable, **Partial** = some keys only, **N** = session-only / at risk.

| Area | Browser refresh | App reboot / cold start | Workspace scoped | Notes |
|------|-----------------|-------------------------|------------------|-------|
| Experience mode | Y | Y | Y | `experience` + `_suite_persisted_experience` in cloud blob |
| Active tab | Y | Y | Y | `investment_active_tab` |
| Portfolio holdings | Y | Y | Y | `holdings_df` + fingerprint; clobber guards |
| Sidebar portfolio value | Y | Y | Y | `sidebar_portfolio_value` |
| Analysis dates / presets | Y | Y | Y | Scalar keys in `_PERSIST_SCALAR_KEYS` |
| Health / macro session knobs | Y | Y | Y | `health_*`, `macro_*` scalars |
| Workflow progress | Y | Y | Y | `workflow_state` blob |
| **How Much Should I Invest inputs** | Y | Y | Y | `plan_*` scalars + `investment_plan_persist` blob (v1) |
| Generated plan result | Y | Y | Y | Serialized in `investment_plan_persist.investment_plan` |
| Compare amounts | Y | Y | Y | `plan_compare_amounts_list` in blob |
| Applied plan portfolio value | Y | Y | Y | `investment_plan_applied_*` scalars |
| Monthly investment blank vs $0 | Y | Y | Y | `plan_monthly_provided` + `plan_monthly` |
| **AMI pending insight** | Y | Y | Y | `_ami_pending_insight` in full_session + saved items |
| AMI dismissals | Y | Y | Y | `_ami_dismissed_*` |
| Scenario params (AMI) | Partial | Partial | Y | On insight payload / session refresh paths |
| Monte Carlo / health results | N | N | Y | Recomputed on demand; not primary persist target |
| Transient UI flags | N | N | — | e.g. `_ami_force_insight_render`, loading flags (intentionally not persisted) |
| Selected subtabs / filters | Partial | Partial | Y | Some overview subtab keys persisted; ephemeral chart toggles not all persisted |

## How Much Should I Invest — behavior

1. **Hydrate once** on workspace load via `restore_investment_disk_state_once` → `apply_investment_disk_state`.
2. **Scalars** (`plan_total_cash`, `plan_horizon`, `plan_risk`, etc.) restore before widgets render.
3. **Blob** restores `investment_plan` object and compare list without requiring regeneration.
4. **Save points**: plan generate, compare list edits, apply-to-portfolio-value, debounced input fingerprint via `maybe_autosave_investment_plan`.
5. **Schema**: `investment-plan-v1` in `investment_plan_persist` (legacy `investment-plan-v0` accepted on read).
6. **Status UI**: “Changes saved.” / warning on failure without deleting prior cloud state.

## Beginner vs advanced widget keys

Both modes read and write the **same canonical session keys** (`plan_total_cash`, `plan_horizon`, `plan_risk`, `plan_compare_amounts_list`, etc.). Streamlit widget keys differ by prefix (`invest_plan_beginner_*` vs `invest_plan_advanced_*`); on workspace restore, `seed_plan_widget_keys_from_canonical()` copies canonical values into the active prefix before widgets render so modes do not diverge.

## Remaining gaps

- **Plan compare projections** (`plan_compare_return`): session-only, cleared on hydrate; recomputed when portfolio analytics run (not persisted).
- **Macro live snapshots** and **MC cached summaries**: session-only by design (large / stale quickly).
- **Tab-local UI** (expanders open, scroll position): not persisted.

## Migration

Older workspaces without `investment_plan_persist` still load scalar `plan_*` fields. On next save, blob v1 is written. No destructive migration; missing blob leaves `investment_plan` unset until user regenerates or a future save includes computed plan.
