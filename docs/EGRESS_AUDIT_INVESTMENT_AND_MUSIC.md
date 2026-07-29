# Egress audit — Investment Portfolio Analyzer & Music Practice Coach

Audit date: 2026-07-28. Baseball uses the same **suite cloud modules** in this repo (`suite_storage_supabase`, `suite_cloud_state`, `suite_user_persistence`, `suite_egress_trace`); Investment adds **Yahoo market data** and **OpenAI analytical synthesis**.

## Executive summary

| Area | Investment | Music Practice Coach |
|------|------------|----------------------|
| Background polling | **None** (Streamlit reruns only) | Same (app not in this repo) |
| Supabase GET dedupe | **Yes** — per-run cache in `suite_storage_supabase.py` | Use synced suite modules |
| Full-session cloud cache | **Yes** — `load_cloud_full_session()` meta gate | Same |
| Autosave fingerprint skip | **Yes** — unchanged hash → no write | `autosave_if_changed` pattern |
| End-of-run autosave | **Yes** — every rerun; fp skip limits writes | Same pattern in Music app entry |
| Yahoo / market API | **Layered cache** — see `docs/INVESTMENT_MARKET_DATA.md` | N/A |
| OpenAI (AMI synthesis) | **On submit / slider refresh only**; session cache added | Coach sends — 120s AMI cooldown |
| Dev egress panel | `?dev=1` + admin → **Supabase egress** + **Market data cache** | Same suite panel when modules synced |

**Changes implemented in this audit (Investment):**

1. Skip redundant **Supabase GET after save** on `end_of_run` autosave (keeps readback for tab/mode/portfolio/global triggers).
2. **`clear_workspace_autosave_block(st, "investment")`** at end of `streamlit_app.py` (Baseball/Music pattern).
3. **OpenAI session cache** for identical synthesis prompts within a Streamlit session (`INVESTMENT_AMI_OPENAI_SESSION_CACHE`, default on).

---

## Investment — what was already optimized

### Supabase / persistence

- **`restore_investment_disk_state_once`** — single bootstrap restore per session (not every rerun).
- **`autosave_investment_state`** — SHA fingerprint skip when blob unchanged (except explicit triggers).
- **`_end_of_run_autosave_blocked` / clobber guards** — avoid destructive cloud writes.
- **`suite_analytical_question._recent_duplicate_send`** — 120s cooldown on duplicate AMI submits (all suite apps).
- **`load_cloud_full_session`** — session cache keyed by cloud `updated_at`.
- **`@st.cache_data`** on analytics wrappers in `streamlit_app.py` — price history and derived packs not refetched every widget interaction when inputs unchanged.
- **`investment_market_data`** — in-flight dedupe, session + disk TTLs, `INVESTMENT_EGRESS_STRICT`.
- **FRED macro** — disk cache in `components/macro_data.py`; forward projection fingerprint in `macro_engine.py`.
- **Screenshot/demo mode** — `portfolio_polish.skip_background_persistence` / `skip_api_refresh` skips end-of-run save and heavy work.

### OpenAI

- Calls only from **`analytical_synthesis`** when `response_mode == analytical_synthesis` and `INVESTMENT_AMI_ANALYTICAL_SYNTHESIS=1`.
- Deterministic instant engines **never** hit OpenAI.
- Mock path (`INVESTMENT_AMI_SYNTHESIS_MOCK=1`) avoids HTTP entirely.

### Polling

- No `st_autorefresh`, timers, or background threads fetching APIs in Investment `streamlit_app.py`.

---

## Investment — remaining opportunities

| Opportunity | Effort | Notes |
|-------------|--------|--------|
| **`sync_workspace_protocol`** for Investment bootstrap | Medium | Music uses full protocol; Investment still uses `restore_once` only — see `docs/INVESTMENT_PERSISTENCE_AUDIT.md`. Reduces restore storms on AMI deep links. |
| **Gate `reconcile_investment_cloud_drift_if_needed`** | Low | Runs once at bootstrap; keep as-is unless traces show duplicate GETs. |
| **Slider refresh + analytical synthesis** | Medium | Scenario sliders re-call `solve_instant_investment_insight`; OpenAI session cache mitigates duplicate identical prompts. |
| **Streamlit `@st.cache_data` TTL** | Low | Optional TTL on `load_market_data` if disk TTL is preferred over unbounded Streamlit cache. |
| **Production `INVESTMENT_EGRESS_STRICT=1`** | Config | Prefer cache/static over live Yahoo retry on Cloud. |

---

## Configuration flags (Investment)

Set in Streamlit Cloud **Secrets** (as env vars in Advanced settings) or local shell:

| Variable | Default | Purpose |
|----------|---------|---------|
| `INVESTMENT_EGRESS_STRICT` | `false` | Prefer cached/static market data over live retry |
| `INVESTMENT_MARKET_DISK_CACHE` | `true` | Disk cache for Yahoo ETF/history |
| `INVESTMENT_MARKET_*_TTL_*` | see `INVESTMENT_MARKET_DATA.md` | TTL hours/minutes |
| `INVESTMENT_AMI_ANALYTICAL_SYNTHESIS` | off | Enable OpenAI synthesis (only when needed) |
| `INVESTMENT_AMI_SYNTHESIS_MOCK` | off | Dev/CI — no OpenAI HTTP |
| `INVESTMENT_AMI_OPENAI_SESSION_CACHE` | `1` | Dedupe identical OpenAI bodies per browser session |
| `INVESTMENT_AMI_SLIDER_TRACE` | off | Verbose insight lifecycle logging only |

Dev observability (admin + `?dev=1`):

- Sidebar **Supabase egress (dev)** — `suite_egress_trace`
- Sidebar **Market data cache** — `investment_market_data/diagnostics.py`

---

## Music Practice Coach

The **Music Streamlit app source is not in this repository**. This repo only includes shared suite pieces (e.g. `music_resume_payload.py`, AMI submit helpers, tests).

For Music egress parity with Baseball, the Music app deployment should:

1. Sync suite cloud modules from Command Center (`scripts/sync_suite_cloud_modules.py` in sibling repo).
2. Call **`prepare_music_workspace()` + `sync_workspace_protocol()`** at startup (per `docs/INVESTMENT_PERSISTENCE_AUDIT.md`).
3. End each run with **`autosave_if_changed`** / Music equivalent and **`clear_workspace_autosave_block(st, "music")`**.
4. Use **`submit_analytical_question`** for coach sends (120s duplicate cooldown).
5. Enable **`?dev=1`** egress panel via `render_suite_sidebar_account_shell` / `suite_app_shell`.
6. Avoid polling; cache OpenAI/coach API responses per session where prompts repeat.

Audit Music-specific network calls in the **music-practice-coach** (or equivalent) repo for `@st.cache_data`, coach API wrappers, and audio CDN usage.

---

## Verification

1. Admin session, `?dev=1`, open Investment app.
2. Note **Supabase egress** reads on first load vs second rerun (GET cache hits should rise).
3. Change a tab → one write; end-of-run without blob change → **skipped_fp_unchanged** in persistence debug (dev).
4. Submit analytical AMI question twice with sliders unchanged → second synthesis should hit **OpenAI session cache** (no second HTTP if prompts identical).
5. Run tests: `pytest tests/test_investment_persistent_state.py tests/test_analytical_synthesis.py -q`
