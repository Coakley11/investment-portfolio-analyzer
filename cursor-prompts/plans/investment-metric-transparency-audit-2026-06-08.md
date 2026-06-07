# Investment metric transparency audit (2026-06-08)

**Scope:** Code audit + UI wording recommendations only. **No formula changes.**

**Goal:** A user should immediately understand what dates they are using, whether a number is historical or forward-looking, whether macro affects it, and why a recommendation appeared.

---

## Executive answer: “I want to invest for 10 years”

| User intent | Correct control | Wrong control |
|-------------|-----------------|---------------|
| “Use 10 years of **past** market data to describe my portfolio” | Sidebar **Historical lookback start** = today − 10 years, **end** = today | Forward horizon sliders |
| “**Project** my portfolio 10 years into the future” | Monte Carlo **Projection years**, Forward Macro **fwd_years**, or planning **Investment horizon** sliders | Sidebar Start/End dates set to future dates |

**Start/End are NOT investment dates.** They define which historical price window is downloaded and analyzed.

---

## Priority 1 — Date range dependency map (page-by-page)

### Global pipeline

| Source | Code path | Feeds |
|--------|-----------|-------|
| Sidebar `Start` / `End` date widgets | `render_sidebar()` → `settings["start"]`, `settings["end"]` ISO strings | All analytics when `needs_analytics_load()` is true |
| Price download | `load_market_data()` → `portfolio_core.fetch_price_history(start, end)` | Daily returns matrix |
| Derived inputs | `mean_rets = returns.mean() × 252`, `cov = returns.cov() × 252` | Optimizer, frontier, health cov inputs |
| Extended metrics | `compute_extended_metrics(returns, weights, …)` | Overview headline metrics |

**Persisted but disconnected:** ~~`analysis_start_date` / `analysis_end_date`~~ **Fixed Phase 1:** sidebar widgets bound via `key="analysis_start_date"` / `key="analysis_end_date"`.

**Health cache gap:** ~~`health_settings_fingerprint()` omits lookback dates~~ **Fixed Phase 1:** lookback ISO dates included in fingerprint.

### Page-by-page table

| Page / area | Tab label(s) | Date range used? | Horizon used? | Returns from range? | Vol from range? | Corr from range? | MC uses range? | Frontier uses range? | Ignores / notes |
|-------------|--------------|------------------|---------------|---------------------|-----------------|------------------|----------------|----------------------|-----------------|
| **Overview** | ② Overview / Overview | **Yes** — `settings["start/end"]` | Recommendation expander: `{prefix}_horizon_slider` → `recommend_portfolio()` only (preset mix, not charts) | **Yes** | **Yes** | Indirect (risk tab) | No | No | Cached health/recs may reflect prior window; **Projected Value (1Y)** always 1 year (`years_forward=1.0`) |
| **Portfolio Health** | ⑤ / Portfolio Health | **Yes** — all historical inputs | Internal hardcoded `recommend_portfolio(35, 15, …)` for drift compare | **Yes** (score inputs) | **Yes** | **Yes** | No | No (unless optimizer drift enabled — historical μ/Σ) | Macro panel affects score/narrative, not raw return series |
| **Analyze / Risk** | ④ Analyze / Portfolio Analytics | **Yes** — corr, vol rank, scenarios | Scenario table: **fixed 1Y** shocks | Base case **Yes** | **Yes** | **Yes** | No | No | `macro_regime_analysis(..., years=1)` — separate fixed regime dropdown, not Portfolio Health macro |
| **Monte Carlo** | Monte Carlo / ⑧ Scenarios | **Yes** in Historical mode | **`mc_years`** slider (1–15, default 5, not persisted) | Historical mode: **Yes** | Historical mode: **Yes** | N/A (GBM) | Historical μ/σ from range; Forward mode: macro-adjusted μ/σ | No | Forward mode via `get_forward_projection()` — **call sites omit required `start`/`end` args** (bug) |
| **Efficient Frontier** | Efficient Frontier / ⑩ Frontier | **Yes** in Historical mode | Forward branch: default **5 years** in projection helper | Historical: **Yes** | Historical: **Yes** | **Yes** (Σ) | No | **Yes** (μ, Σ) | Forward mode uses macro-adjusted μ/Σ |
| **Optimizer** | Optimization / ⑨ Optimizer | **Yes** in Historical mode | Forward: default **5 years** (no slider) | Historical: **Yes** | Historical: **Yes** | **Yes** | No | **Yes** | Compare table “Your allocation” row always shows **historical** metrics |
| **Forward Macro Analysis** | Forward Macro (Advanced tab 6) | **Yes** — seeds base metrics | **`fwd_years`** slider | Base from range, then adjusted | Base from range, then adjusted | Adjusted in forward path | No | Optional forward optimizer display | Direct `compute_forward_projection_with_profile()` — works |
| **Beginner Coach / Goal** | ① Choose Goal | **No** on goal cards | Goal cards set preset/objective only | No | No | No | No | No | Pipeline explainer documents sidebar dates |
| **Investment planning** | Portfolio Inputs → planning | **No** | **`plan_horizon`** / `{prefix}_plan_horizon` | No | No | No | No | No | Cash sleeve split only (`compute_investment_plan`) |
| **Beginner macro panel** | Sidebar / coach | **No** | N/A | No | No | No | No | No | Sets `health_*` keys from live data or scenarios |

### Answers to explicit date questions

1. **Returns based on selected range?** — **Yes**, for all historical metrics (`annualized_return(daily.mean × 252)` on portfolio daily returns in window).
2. **Volatilities based on selected range?** — **Yes** (`daily.std × √252`).
3. **Correlations based on selected range?** — **Yes** (`returns.corr()` on same window).
4. **Monte Carlo using estimates from range?** — **Historical mode: Yes.** Forward mode: macro-adjusted μ/σ seeded from historical base metrics + mean/cov, then stressed.
5. **Efficient Frontier using estimates from range?** — **Historical mode: Yes.** Forward mode: macro-adjusted μ/Σ.
6. **Range ignored anywhere?** — Goal cards, planning horizons, recommendation preset slider, health internal 15Y drift helper, scenario fixed shocks, Overview 1Y projection label ambiguity, persisted date keys vs sidebar widgets.

---

## Priority 2 — Historical vs forward metrics

| Metric (UI label) | Formula / source | Historical or forward | Macro affects? | Dates affect? | Holdings affect? |
|-------------------|------------------|----------------------|----------------|---------------|------------------|
| **Annual Return** / Average Yearly Return | `mean(daily_portfolio_returns) × 252` | **Historical** | No | **Yes** | **Yes** (weights) |
| **Volatility** / How Bumpy | `std(daily) × √252` | **Historical** | No | **Yes** | **Yes** |
| **Sharpe Ratio** / Risk-Reward Score | `(ann_return − risk_free) / ann_vol` | **Historical** | No (risk-free slider only) | **Yes** | **Yes** |
| **Max Drawdown** / Worst Drop | Peak-to-trough on cumulative return in window | **Historical** | No | **Yes** | **Yes** |
| **Sortino Ratio** | Downside deviation vs risk-free | **Historical** | No | **Yes** | **Yes** |
| **CAGR** | From growth series over window | **Historical** | No | **Yes** | **Yes** |
| **Beta vs SPY** | Cov(port, SPY)/Var(SPY) in window | **Historical** | No | **Yes** | **Yes** |
| **Projected Value (1Y)** | `initial × (1 + ann_return)^1` | **Historical extrapolation** (1Y only) | No | **Yes** (via ann_return) | **Yes** |
| **Growth chart** | Compounded daily returns in window | **Historical** | No | **Yes** | **Yes** |
| **Correlation matrix** | `returns.corr()` | **Historical** | No | **Yes** | **Yes** (which tickers) |
| **Portfolio Health Score (0–100)** | Weighted components on historical metrics + macro rules | **Mixed** — base stats historical; macro component forward-leaning | **Yes** (Macro Regime Fit ±1–2 pts) | **Yes** (base stats) | **Yes** |
| **Health recommendations** | Rule engine on metrics + macro + objective | **Mixed** | **Yes** (triggers) | **Yes** (via cached run) | **Yes** |
| **Forward Return / Vol / Sharpe** (Forward Macro tab) | `compute_forward_projection_with_profile()` | **Forward** | **Yes** (primary driver) | **Yes** (base seed) | **Yes** |
| **Forward Max Drawdown** (forward tab) | `historical_max_dd × drawdown_mult` | **Forward estimate** (scaled, not simulated path) | **Yes** | **Yes** (base dd) | **Yes** |
| **MC median / percentiles** | GBM with μ/σ | **Forward simulation** | **Yes** if Forward mode | Historical mode: **Yes** | **Yes** |
| **Frontier curve** | Mean-variance on μ/Σ | Historical or Forward per mode toggle | Forward mode only | **Yes** | **Yes** |
| **Optimizer suggested weights** | Max Sharpe / min vol on μ/Σ | Same as mode toggle | Forward mode only | **Yes** | **Yes** |
| **Scenario Analysis base case** | Ann. return from window | **Historical** base, **1Y** projection | No | **Yes** | **Yes** |
| **Macro Regime Engine** (Risk tab) | Fixed scenario table on current metrics | **Forward-style** 1Y adjustment | Uses dropdown regime, **not** Portfolio Health macro | Indirect (base metrics) | **Yes** |

**“Expected Return” is not used as a label today** — closest labels are “Annual Return” (historical) and “Forward Return” (forward tab). Ambiguity risk: “Projected Value” and beginner “one-year estimate” sound forward but use historical ann_return.

---

## Priority 3 — Macro dependency map

| Control | Session key | Default | What changes | Mechanism (approx.) |
|---------|-------------|---------|--------------|---------------------|
| **Interest rate environment** | `health_rate_env` | Stable Rates | Health Macro Regime Fit score ±1.5; forward return/vol/μ/Σ; health narrative | Additive return shift by asset mix (e.g. Rising: −2%×equity, −6%×bonds); vol mult 0.90–1.30 |
| **Recession probability** | `health_recession` | 25% | Health score ±1–2; recommendations if >50% & high equity; forward all metrics; MC in forward mode | Return −18%×p×equity; vol × (1 + 0.75p); corr stress +30%×p; drawdown mult +90%×p |
| **Inflation assumption** | `health_inflation` | Moderate | Health score vs long bonds; recommendations; forward metrics | Category shifts (High: −8%×bonds); vol mult up to 1.28 |
| **Valuation environment** | `health_valuation` | Fair Value | Forward metrics; macro_fit narrative (**not** scored Macro Regime Fit) | Equity-weighted ±1.5–3% return; vol mult 0.95–1.15 |
| **Economic regime** | `health_regime` | Expansion | Health score (regime/asset rules); forward metrics; narrative | Large discrete shifts (Recession −18%×equity); vol mult up to 1.95 |
| **Portfolio objective** | `health_objective` | balanced growth | Objective Alignment score (0–12); rebalance vs target mix; `recommend_portfolio` preset | Target allocation tables — **not** return model |
| **Bond/cash minimum** | `health_bond_min` | 0% | Recommendation threshold only | Rule gate |
| **Optimizer in drift** | `health_run_optimizer` | off (beginner) | Rebalance vs optimizer weights | Historical optimizer only; **not** in health fingerprint |
| **MC / Opt / Frontier mode** | `mc_assumption_mode`, etc. | Historical | Gates whether macro-adjusted μ/Σ used | Mode toggle |

### What macro does **NOT** change

- Historical Overview metrics (return, vol, Sharpe, drawdown) on Performance row
- Raw price history or daily return series
- Correlation matrix from historical window (unless Forward mode replaces Σ for optimizer/frontier/MC)
- Static macro sensitivity heatmap (education lookup — not live slider values)
- Risk tab **Macro Regime Engine** dropdown (separate fixed scenarios from Portfolio Health macro)

### Batch controls (Beginner)

- **Use current environment** → writes all `health_*` from FRED via `macro_data.apply_current_environment_from_live()`
- **Custom scenario** → bundled preset of all five macro keys

---

## Priority 4 — UI transparency recommendations (wording only)

### Global banners

**Historical metrics banner** (Overview, Analyze, Performance expander):
> These metrics use **historical market data** from **[start]** to **[end]** and your **current portfolio weights**. They describe past behavior, not guaranteed future results.

**Macro banner** (Portfolio Health, Forward Macro, MC when Forward mode):
> **Macro assumptions** affect the health score, forward projections, and recommendations. They do **not** change historical return or volatility on the Overview tab.

### Label renames

| Current | Recommended | Where |
|---------|-------------|-------|
| Start / End | **Historical lookback start / end** | Sidebar |
| Annual Return | **Historical annualized return** | Advanced Overview |
| Average Yearly Return | **Average yearly return (historical)** | Beginner Overview |
| Volatility | **Historical annualized volatility** | Advanced |
| How Bumpy (Volatility) | **Typical ups & downs (historical)** | Beginner |
| Sharpe Ratio | **Historical risk-adjusted return (Sharpe)** | Advanced |
| Projected Value (1Y) | **Simple 1-year extrapolation (historical rate)** | Both |
| Projection years (MC) | **Forward simulation horizon (years)** | Monte Carlo |
| Years until you need the money | **Planning horizon (years)** — *does not change charts* | Recommendation expander |
| Portfolio Health Score | **Portfolio Health Score** + subtitle: *Based on historical data + macro assumptions* | Health tab |

### Read-only date summary (under sidebar dates)

> Analyzing **[tickers]** from **{start}** to **{end}** ({N} years of daily data).

### Beginner callout (Goal tab or sidebar)

> **Two different time settings:**  
> • **Historical lookback** (sidebar dates) = how much past market history to analyze  
> • **Planning horizon** (goal / planning sliders) = when you expect to need the money

---

## UI mockups (wording-only)

### Beginner — Overview metrics row

```
┌─────────────────────────────────────────────────────────────────┐
│ ℹ️ Based on historical data Jan 2021 – Jun 2026 & current weights │
└─────────────────────────────────────────────────────────────────┘

 Average yearly return     Typical ups & downs     Risk/reward score
 (historical)              (historical)              (historical)
     8.2%                       12.4%                    0.62
```

### Advanced — Overview

```
Historical analysis window: 2021-01-04 → 2026-06-06 (5.4 years)
Macro settings do not alter these headline metrics.

┌──────────────┬──────────────┬──────────────┬──────────────────────┐
│ Hist. ann.   │ Hist. ann.   │ Hist. Sharpe │ 1Y extrapolation     │
│ return 8.2%  │ volatility   │ 0.62         │ $108,200             │
│              │ 12.4%        │              │ (not a forecast)     │
└──────────────┴──────────────┴──────────────┴──────────────────────┘
```

### Portfolio Health page

```
┌─────────────────────────────────────────────────────────────────┐
│ Health score uses historical return/vol/drawdown from your        │
│ lookback window PLUS macro assumptions below. Refresh after       │
│ changing dates or macro settings.                                 │
└─────────────────────────────────────────────────────────────────┘

Portfolio Health Score: 72 / 100
Historical base: 2021-01-04 → 2026-06-06 · Macro: Stable rates, 25% recession, Moderate inflation

[Macro & objective settings ▼]
```

---

## Priority 5 — Future enhancement ideas (do not implement yet)

1. **Historical Mode / Forward Forecast Mode** — explicit top-level toggle with separate metric panels
2. **Combined view** — split card: “What happened (historical)” vs “What the model projects (forward)”
3. **Explicit Investment Horizon selector** — one persisted `investment_horizon_years` wired to MC, planning, and forward tabs
4. **Forward-return assumptions panel** — show adjusted μ, σ, and each macro contribution as a waterfall
5. **Macro impact breakdown** — “Recession +10% → vol +2.1%, return −1.4%” on Forward tab
6. **Wire sidebar dates to persisted keys** — single source of truth; include dates in health fingerprint
7. **Fix `get_forward_projection()` call sites** — pass `start`/`end` on MC/Optimizer/Frontier
8. **Recommendation explainers** — “Triggered because: recession 55% + equity 78%”

---

## Code audit findings (bugs / gaps affecting transparency)

| # | Finding | Impact | Suggested fix phase |
|---|---------|--------|---------------------|
| 1 | Sidebar dates not bound to `analysis_start_date`/`analysis_end_date` | Saved session ≠ displayed window | **Fixed Phase 1** — widgets use `key=` |
| 2 | Health fingerprint omits lookback | Stale health after date change | **Fixed Phase 1** — dates in fingerprint |
| 3 | `get_forward_projection()` missing `start`/`end` on MC/Opt/Frontier | Forward MC/Opt/Frontier may error or cache incorrectly | **Fixed Phase 1** |
| 4 | Overview “Projected Value (1Y)” uses historical rate | Users read as forecast | Phase 2 copy |
| 5 | Optimizer compare row always historical | Misleading in Forward optimizer mode | Phase 2 copy + optional row label |
| 6 | Multiple horizon sliders (`mc_years`, `fwd_years`, `_horizon_slider`, `plan_horizon`) | User confusion | Phase 2 UX consolidation plan |
| 7 | Risk tab Macro Regime Engine ≠ Portfolio Health macro | Two macro systems | Phase 3 doc + eventual unify |
| 8 | `health_valuation` affects forward math but not scored macro fit | Score/narrative inconsistency | Phase 3 formula review |

---

## Recommended implementation order

| Phase | Work | Formula changes? |
|-------|------|------------------|
| **1 — Truth in labeling** | Rename sidebar dates; add historical/macro banners; show active window summary; fix `get_forward_projection` args; wire persisted dates to widgets | No |
| **2 — Per-metric footnotes** | Overview/Health metric subtitles; rename Projected Value; Optimizer compare row labels; beginner two-time-settings callout | No |
| **3 — Cache & consistency** | Add lookback to `health_settings_fingerprint`; unify horizon slider naming; document Risk vs Health macro | No |
| **4 — Forward transparency** | Macro waterfall / assumption panel; Historical vs Forward mode toggle | Optional minor |
| **5 — Formula review** | Valuation in health score; drawdown forward estimate methodology | Yes — separate project |

---

## Key code references

- Sidebar dates: `streamlit_app.py` `render_sidebar()` ~1066–1127
- Analytics load: `streamlit_app.py` ~1917–1945; `investment_workflow.py` `needs_analytics_load()`
- Metrics: `portfolio_core.py` `compute_extended_metrics()`, `annualized_return()`, `annualized_volatility()`
- Health: `portfolio_core.py` `evaluate_portfolio_health()`; `components/macro_engine.py` `health_settings_fingerprint()`
- Forward: `portfolio_core.py` `compute_forward_projection_with_profile()`; `components/macro_engine.py` `get_forward_projection()`
- Persisted dates: `investment_persistent_state.py` `analysis_start_date`, `analysis_end_date`
- Help copy: `components/ui_helpers.py` `HISTORICAL_PERIOD_*`, transparency banners

---

## Phase 1 transparency — implemented (2026-06-08)

**No formula changes.**

| Priority | Deliverable | Status |
|----------|-------------|--------|
| 1 | Sidebar **Historical Lookback Start/End**, helper text, active window summary | Done |
| 2 | **Historical Metrics** banner on Overview, Analyze, Portfolio Health | Done |
| 3 | **Macro Assumptions** banner near macro controls (Health tab) | Done |
| 4 | Rename historical headline metrics (Advanced + Beginner labels) | Done |
| 5 | Beginner Coach lookback vs planning horizon education | Done |
| 6 | Bug fixes: date widget binding, health fingerprint lookback, `get_forward_projection(start/end)` | Done |

**Tests:** `tests/test_transparency_phase1.py` (window label + fingerprint with lookback dates).

**Last updated:** 2026-06-08 (Phase 1 shipped)
