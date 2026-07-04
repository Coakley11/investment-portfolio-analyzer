# Investment Portfolio Analyzer

**A professional finance dashboard** built with Python and Streamlit. It combines real market data, portfolio analytics, Monte Carlo simulation, optimization, and structured Applied Math Intelligence (AMI) handoffs — all scoped to per-account workspace isolation in the Daniel Cohen AI Suite.

**Live demo:** [investment-portfolio-analyzer.streamlit.app](https://investment-portfolio-analyzer-ty2sbzumvxsqwbqhkvf6rz.streamlit.app)  
**Deploy branch:** `dev` · **Entry point:** `streamlit_app.py`

Built as part of the **Daniel Cohen AI Suite** (shared workspace auth, cloud persistence, and Command Center / AMI handoffs).

---

## At a Glance

| | |
|---|---|
| **Role** | Full-stack Python finance app — portfolio analytics, risk modeling, optimization, and test-driven persistence |
| **Stack** | Python 3.11+ · Streamlit · pandas · numpy · yfinance · Plotly · optional Supabase · AMI Command Center handoff |
| **Scale** | Beginner + Advanced modes · preset portfolios · efficient frontier · Monte Carlo · macro-aware projections |
| **Differentiators** | Dual experience modes (Beginner/Advanced) · rule-based + quantitative insights · workspace-scoped holdings and AMI return state |

---

## For Employers & Reviewers

This project demonstrates end-to-end ownership of a data-heavy finance product: live market ingestion, portfolio risk metrics, optimization and simulation engines decoupled from UI (`portfolio_core.py`), and **suite workspace isolation** so authenticated accounts (e.g. `coakley11`) never load another user's holdings. Inspect `tests/test_workspace_account_ownership.py` and `investment_persistent_state.py` without running the full UI.

---

## 1. Executive Summary

Most portfolio tools show charts. This app helps you **understand risk, rebalance with intent, and stress-test outcomes**.

Investment Portfolio Analyzer is an interactive dashboard for:

- Building portfolios from presets or custom holdings (stocks, ETFs, bonds, REITs)
- Computing return, volatility, Sharpe, Sortino, CAGR, max drawdown, beta vs SPY
- Running Monte Carlo paths with confidence intervals and loss probabilities
- Optimizing weights and visualizing the efficient frontier
- Macro-aware forward projections and beginner-friendly coaching flows
- Asking follow-up questions via **Applied Investment Insight**, with structured page context routed to **AMI / Command Center**

The app is designed as a portfolio piece demonstrating **quantitative finance, UX for non-experts, cloud persistence, and product-minded decision support** — not a static spreadsheet.

---

## 2. Why This Project Is Different

| Typical portfolio tool | This platform |
|------------------------|---------------|
| One-size-fits-all UI | Beginner checklist + Advanced analyst tabs |
| Static CSV upload | Live Yahoo Finance data + preset portfolios |
| Single-user local state | Account-owned workspace isolation + Supabase sync |
| Generic chat | Structured AMI handoff with page/tab context |

---

## 3. Key Features

| Area | Highlights |
|------|------------|
| **Portfolio Health** | Core metrics, correlation heatmap, risk contribution, scenario analysis |
| **Portfolio Analytics** | Rolling returns/volatility, holdings drill-down, ETF coverage |
| **Efficient Frontier** | Optimizer with highlighted portfolios and constraint panels |
| **Monte Carlo** | Path simulation, histogram, P(loss), P(2×) |
| **Beginner Mode** | Goal cards, guided adjustment, macro education, monthly review |
| **Applied Investment Insight** | Sidebar AMI panel with page-scoped return from Command Center |
| **Account & Workspace** | Real Accounts auth, owned workspace per login, foreign URL rejection |

---

## 4. Analytics & AI Methods

| Method | Use |
|--------|-----|
| Historical return/volatility | Rolling windows, CAGR, drawdown |
| Risk-adjusted metrics | Sharpe, Sortino, beta vs benchmark |
| Correlation & risk contribution | Diversification diagnostics |
| Monte Carlo simulation | Forward path distributions |
| Mean-variance optimization | Efficient frontier |
| Macro engine | Forward projection assumptions |
| Rule-based insights | Portfolio coaching cards |
| AMI integration | Structured analytical questions with solver handoff |

---

## 5. Technical Architecture

```
streamlit_app.py              # UI shell, tabs, sidebar, exports
portfolio_core.py             # Core calculations (stable contract)
dashboard_charts.py           # Plotly chart builders
investment_persistent_state.py # Disk + cloud restore, holdings sync
components/                   # Beginner coach, macro, rebalancing panels
├── suite_workspace.py        # Workspace profiles + bootstrap_suite_workspace
├── suite_workspace_registry.py # Account-owned workspace registry
├── suite_auth.py             # Real Accounts + ownership enforcement
├── suite_user_persistence.py # Scoped state paths + sync_workspace_protocol
└── applied_math_return_insight.py # AMI return panel (display-only v1)
```

**Persistence paths**

| Layer | Path / key |
|-------|------------|
| Active workspace (account) | `data/workspaces/_active/{owner_user_id}.json` |
| Ownership registry | `data/workspaces/_ownership_registry.json` |
| App state | `data/workspaces/{workspace_id}/investment_user_state.json` |
| Cloud | Supabase `suite_saved_items` scoped via `investment__{workspace}` |

**Startup order (v2 isolation)**

1. `bootstrap_suite_workspace(st)` — auth restore → ownership clamp → workspace init
2. `apply_suite_auth_gate(st)`
3. `apply_suite_resume_launch(st, "investment")`
4. `restore_investment_disk_state_once(st)`

---

## 6. Screenshots

> Enable portfolio screenshot mode in the sidebar before capturing.

| # | Page | Filename (placeholder) | What to show |
|---|------|------------------------|--------------|
| 1 | Portfolio Health | `screenshots/01-portfolio-health.png` | Core metrics + correlation heatmap |
| 2 | Efficient Frontier | `screenshots/02-efficient-frontier.png` | Optimizer results + highlighted portfolios |
| 3 | Monte Carlo | `screenshots/03-monte-carlo.png` | Path fan + confidence intervals |
| 4 | Beginner Mode | `screenshots/04-beginner-coach.png` | Goal cards + guided next step |
| 5 | Applied Investment Insight | `screenshots/05-ami-insight.png` | Sidebar insight + returned AMI answer |

---

## 7. Local Setup

### Requirements

- **Python 3.11+**
- `pip install -r requirements.txt`

### Run locally

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

### Optional environment variables

| Variable | Purpose |
|----------|---------|
| `SUITE_SUPABASE_URL` | Cloud persistence |
| `SUITE_SUPABASE_KEY` / `SUITE_SUPABASE_ANON_KEY` | Supabase client |
| `SUITE_AUTH_ENABLED` | Real Account sign-in |

Configure secrets in `.streamlit/secrets.toml` (see `.streamlit/secrets.toml.example`).

### Streamlit Cloud

- **Branch:** `dev`
- **Main file:** `streamlit_app.py`

---

## 8. Roadmap

**Near term**
- [ ] `prepare_investment_workspace()` wrapper at startup (sync protocol parity with Music)
- [ ] Cross-device holdings validation (Sprint D P-rows)
- [ ] AMI solver routing polish for macro/optimizer questions

**Medium term**
- [ ] Tax-lot and cost-basis modeling
- [ ] Factor exposure and style analysis
- [ ] CI matrix with workspace ownership tests on every PR

---

## 9. Testing

```bash
python -m pytest tests/test_workspace_account_ownership.py -q
python -m pytest tests/test_developer_workspace_gating.py -q
```

Workspace isolation acceptance: `coakley11` → `coakley11` workspace; foreign `?suite_workspace=daniel` rejected at startup.

---

## Disclaimer

This tool is for education and portfolio projects. It is not financial advice.

## Author

Daniel Cohen
