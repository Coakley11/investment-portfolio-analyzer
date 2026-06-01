# Model Assumptions & Quantitative Methods

This document describes how the Investment Portfolio Analyzer computes key metrics.
It is the source of truth for methodology copy in the app and for future development.

**Design principle:** Beginner Mode shows *what to do*, *why*, and *dollar amounts*.
Advanced Mode shows formulas, methodology expanders, and this document.

---

## Historical analysis window (Start / End dates)

Sidebar **Start** and **End** define which daily prices are downloaded (yfinance) and converted to `returns`.
Almost all analytics share this single baseline computed at app load:

```text
Start / End
    → prices → daily returns
    → mean_rets (μ), cov (Σ), metrics (portfolio stats)
    → Portfolio Health, recommendations, risk pack
    → Forward macro (historical + adjustments)
    → Monte Carlo / Optimizer / Frontier
```

### Uses the selected window consistently

| Component | Uses Start/End baseline? | Notes |
|-----------|-------------------------|--------|
| Portfolio Analytics (return, vol, Sharpe, Sortino, beta, drawdown, CAGR) | **Yes** | From `returns` / `metrics` |
| Correlation & covariance displays | **Yes** | `returns.corr()` / `returns.cov()` × 252 |
| Portfolio Health & recommendations | **Yes** | Same `metrics`, `mean_rets`, `cov` |
| Forward Macro (on **Run**) | **Yes** → macro | `metrics` + `mean_rets` + `cov`, then adjustments |
| Monte Carlo — **Historical** | **Yes** (μ, σ only) | Portfolio-level GBM from window; **not** full Σ in paths |
| Monte Carlo — **Forward** | **Yes** indirectly | Macro-adjusted μ, σ from window-based forward projection |
| Optimizer — **Historical** | **Yes** | `mean_rets`, `cov` from window |
| Optimizer — **Forward** | **Yes** → macro | `adjusted_mean_returns`, `adjusted_cov` |
| Efficient Frontier | Same as optimizer | Historical or forward μ, Σ |
| Beginner Analyze / coach | **Yes** | Same pipeline; advanced tabs hidden |

### Exceptions / caveats

1. **Monte Carlo paths** — Uses portfolio-level expected return and volatility (historical or forward-adjusted). Does **not** simulate correlated multi-asset paths from Σ today. See *Multi-asset Monte Carlo* under Future Model Improvements.

2. **Forward projection cache** — `get_forward_projection()` caches by **Start**, **End**, macro assumptions, projection **years**, and asset count. Changing only holdings with the same ticker count still recomputes when metrics change on rerun; cache invalidates when dates or macro change.

3. **Forward Macro tab (Run button)** — Calls `compute_forward_projection_with_profile` directly each run (always uses current `metrics` from the active window).

4. **Risk-free rate** — Sidebar slider; not tied to Start/End.

5. **Portfolio value ($)** — Dollar amounts only; does not change historical return estimation.

---

## Portfolio Health — Objective Alignment

### Category drift

1. Compute category weights from holdings: `equity`, `bonds`, `tbills` (REITs count toward equity).
2. Look up targets from `OBJECTIVE_ALLOCATIONS` for the selected objective.
3. Per-category drift: `|current − objective|`
4. **Average drift** (0–1): `(eq_drift + bond_drift + tbill_drift) / 3`

### Objective Alignment subscore (0–12 of 100)

```python
s_obj = clip(12 - avg_drift * 30, 0, 12)
```

### Beginner wording (no formulas in UI)

| avg_drift | Message |
|-----------|---------|
| &lt; 3% | Portfolio is **close to** the allocation for the selected goal |
| 3–6% | Portfolio is **somewhat different from** the goal allocation |
| ≥ 6% | Portfolio is **significantly different from** the goal allocation |

---

## Rebalancing vs Suggested Allocation Adjustment

| State | Label | Meaning |
|-------|-------|---------|
| Capital not deployed (`capital_deployed` false) | **Suggested Allocation Adjustment** | Planned mix vs objective — not selling existing holdings |
| Capital deployed | **Rebalancing guidance** | Current weights vs objective |

**Baseline:** current weights vs objective mix (not preset, not optimizer by default).

Per-ticker objective: category targets spread by asset type, normalized to 100%.

UI cards: moves ≥ 1 percentage point (`Objective % − Current %`).

---

## Forward Macro Analysis

### Expected return

```python
adjusted_return = historical_annual_return + ret_shift
```

`ret_shift` aggregates allocation-weighted effects from rate environment, inflation, valuation, regime, and recession probability.

### Volatility

```python
adjusted_volatility = max(0.001, historical_volatility * vol_mult)
```

Covariance (optimizer / forward Monte Carlo):

```python
adjusted_cov = historical_cov * (vol_scale**2) * corr_stress
vol_scale = adjusted_vol / historical_vol
corr_stress = 1 + recession_prob * 0.30
```

### Single-Scenario Projection (deterministic)

**Label in UI:** *Single-Scenario Projection* — not "Monte Carlo estimate."

```python
projected_value = initial_value * (1 + adjusted_return) ** years
```

One compound-growth path. For outcome **ranges**, use the **Monte Carlo** tab.

### Stress-Adjusted Historical Drawdown Estimate

**Label in UI:** *Stress-Adjusted Historical Drawdown Estimate* — not a forward drawdown forecast.

```python
adjusted_max_drawdown = historical_max_drawdown * (1 + recession_probability * 0.90)
```

Historical drawdown from weighted price history, scaled under recession stress.

### Forward Sharpe

```python
adjusted_sharpe = (adjusted_return - risk_free_rate) / adjusted_volatility
```

---

## Macro inputs — why they matter (model relationships)

### Recession probability

Higher values → lower expected returns (equity/REIT), higher volatility, larger stress-adjusted drawdown, higher correlation stress.

### Inflation

Higher settings → bond/long-duration drag, higher volatility (High Inflation category), lower real returns unless offsets apply.

### Interest rates

Rising/high rates → pressure on long-duration assets; T-Bills may benefit in the model. Falling rates → often help bonds.

---

## Optimizer

Long-only mean-variance (SciPy SLSQP):

| Objective | Minimizes |
|-----------|-----------|
| Max Sharpe | `−(μ_p − r_f) / σ_p` |
| Min volatility | `σ_p` |

Inputs: μ and Σ annualized (daily × 252). Forward mode uses macro-adjusted μ and Σ.

**Important:** Optimizer outputs depend entirely on input assumptions. They are not certainty or advice.

---

## Efficient Frontier

For each target return on a grid: minimize `σ_p` subject to `w·μ = target`, `Σw = 1`, `w ≥ 0`.

---

## Monte Carlo (separate from single-scenario projection)

Simulates many random paths using historical or forward-adjusted **portfolio-level** return and volatility.

Reports percentiles, P(loss), P(reach target), etc. — **not** the same as the deterministic forward projection.

Historical mode: μ and σ from the selected Start/End window. Forward mode: macro-adjusted μ and σ from the same window-based baseline.

---

## Future Model Improvements

### Current simplifications

- Single-scenario macro adjustments
- Drawdown scaling from history
- Scalar correlation stress
- No taxes, fees, or transaction costs
- Point-estimate optimization without confidence bands
- Monte Carlo: single portfolio process (not multi-asset correlated simulation)

### Multi-asset Monte Carlo (future enhancement)

- Simulate holdings separately (e.g. SPY, QQQ, AGG, BIL)
- Use the full covariance matrix
- Preserve asset correlations across paths
- Aggregate to portfolio-level paths

### Other possible enhancements

- Regime-switching Monte Carlo
- Macro-driven multi-scenario simulations
- Dynamic correlations
- Tax-aware optimization
- Transaction cost modeling
- Confidence intervals around optimizer outputs

---

## Disclaimer

All outputs are educational and model-driven. They are not investment advice, tax advice, or guarantees of future performance.
