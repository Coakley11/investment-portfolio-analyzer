# Investment Portfolio Analyzer

**A professional finance dashboard** built with Python and Streamlit. It combines real market data, portfolio analytics, Monte Carlo simulation, optimization, and structured Applied Math Intelligence (AMI) handoffs — all scoped to per-account workspace isolation in the Daniel Cohen AI Suite.

The platform supports beginner and advanced workflows across portfolio health, analytics, optimization, simulation, ETF overlap analysis, and macro-aware projections.

**Live demo:** [investment-portfolio-analyzer.streamlit.app](https://investment-portfolio-analyzer-ty2sbzumvxsqwbqhkvf6rz.streamlit.app)  
**Deploy branch:** `dev` · **Entry point:** `streamlit_app.py`

Built as part of the **Daniel Cohen AI Suite** (shared workspace auth, cloud persistence, and Command Center / AMI handoffs).

---

## Executive Summary

Most portfolio tools show charts. This app helps you **understand risk, rebalance with intent, and stress-test outcomes**.

The goal is to help users make better investment decisions by combining live market data, quantitative risk analysis, simulation, optimization, macro-aware projections, and AI-assisted reasoning within a single workflow.

Investment Portfolio Analyzer is an interactive dashboard for:

- Building portfolios from presets or custom holdings (stocks, ETFs, bonds, REITs)
- Computing return, volatility, Sharpe, Sortino, CAGR, max drawdown, beta vs SPY
- Running Monte Carlo paths with confidence intervals and loss probabilities
- Optimizing weights and visualizing the efficient frontier
- Exploring ETF holdings overlap and hidden concentration risk
- Macro-aware forward projections and beginner-friendly coaching flows
- Asking follow-up questions via **Applied Investment Insight**, with structured page context routed to **AMI / Command Center**

The app is designed as a portfolio piece demonstrating **quantitative finance, UX for non-experts, cloud persistence, and product-minded decision support** — not a static spreadsheet.

---

## Example Questions This App Can Help Answer

**Portfolio Health & Risk**
- Is my portfolio too concentrated in one sector or asset class?
- How much drawdown risk am I taking relative to my benchmark?
- Which holdings contribute most to overall portfolio risk?

**Optimization & Simulation**
- What portfolio mix improves return for a given level of risk?
- What is the probability of loss over my investment horizon?
- How might my portfolio perform under different macro assumptions?

**ETF & Holdings Analysis**
- How much do my ETFs overlap with each other?
- Am I accidentally doubling exposure through similar fund holdings?
- Which ETF pairs create the most hidden concentration?

**Beginner & Planning**
- Which preset portfolio best matches my goals and risk tolerance?
- How much should I invest monthly to reach my target?
- What should I rebalance first based on my current allocation?

**Investing & AMI Follow-Up**
- Which allocation change has the best risk/reward tradeoff?
- How sensitive is my forecast to inflation or rate assumptions?
- What follow-up analysis should I run in AMI on this portfolio state?

---

## At a Glance

| | |
|---|---|
| **Role** | Full-stack Python finance app — portfolio analytics, risk modeling, optimization, and test-driven persistence |
| **Stack** | Python 3.11+ · Streamlit · pandas · numpy · yfinance · Plotly · optional Supabase · AMI Command Center handoff |
| **Scale** | Beginner + Advanced modes · preset portfolios · efficient frontier · Monte Carlo · macro-aware projections |
| **Differentiators** | Dual experience modes (Beginner/Advanced) · ETF Holdings Explorer · rule-based + quantitative insights · workspace-scoped holdings and AMI return state |

---

## Development Scope

Investment Portfolio Analyzer is part of a seven-application analytics suite developed by a single developer.

The project combines quantitative finance, software engineering, product design, AI integration, persistence systems, authentication, cloud deployment, and cross-application workflows into a unified platform.

---

## For Employers & Reviewers

This project demonstrates end-to-end ownership of a data-heavy finance product: live market ingestion, portfolio risk metrics, optimization and simulation engines decoupled from UI (`portfolio_core.py`), and structured decision-support flows for both beginners and advanced users.

| Skill area | Evidence in Investment |
|------------|------------------------|
| **Quantitative finance** | Sharpe/Sortino, Monte Carlo, efficient frontier, macro engine |
| **Analytics architecture** | `portfolio_core.py` stable contract, `dashboard_charts.py`, ETF overlap engine |
| **Product development** | Beginner checklist + Advanced analyst tabs, coaching cards, guided workflows |
| **AI-assisted workflows** | Applied Investment Insight, AMI handoff with page/tab context |
| **Systems design** | Suite persistence, resume launch, workspace-scoped holdings restore |
| **Cross-application integration** | Command Center deep links, insight return from AMI |

Inspect `tests/test_workspace_account_ownership.py` and `investment_persistent_state.py` without running the full UI.

---

## Why This Project Is Different

Most portfolio tools focus on one layer of analysis — either charts, static uploads, or generic chat.

Investment Portfolio Analyzer was designed as a reusable investment decision framework that supports beginners and advanced users through the same underlying analytics engine.

The same platform architecture supports portfolio health review, optimization, simulation, ETF overlap diagnostics, macro-aware projections, and AMI follow-up through a shared calculation, persistence, and analysis layer.

| Typical portfolio tool | This platform |
|------------------------|---------------|
| One-size-fits-all UI | Beginner checklist + Advanced analyst tabs |
| Static CSV upload | Live Yahoo Finance data + preset portfolios |
| Surface-level ETF labels | ETF Holdings Explorer with pairwise overlap analysis |
| Single-purpose calculators | Integrated health, analytics, frontier, Monte Carlo, and coaching |
| Generic chat | Structured AMI handoff with page/tab context |
| Isolated local state | Account-owned workspace isolation + Supabase sync |

---

## Key Features

| Area | Highlights |
|------|------------|
| **Portfolio Health** | Core metrics, correlation heatmap, risk contribution, scenario analysis |
| **Portfolio Analytics** | Rolling returns/volatility, holdings drill-down, ETF coverage |
| **ETF Holdings Explorer** | Drill into ETF constituents, compare overlap across funds, surface hidden concentration |
| **Efficient Frontier** | Optimizer with highlighted portfolios and constraint panels |
| **Monte Carlo** | Path simulation, histogram, P(loss), P(2×) |
| **Beginner Mode** | Goal cards, guided adjustment, macro education, monthly review |
| **Applied Investment Insight** | Sidebar AMI panel with page-scoped return from Command Center |
| **Account & Workspace** | Real Accounts auth, owned workspace per login, foreign URL rejection |

---

## Analytics & AI Methods

| Method | Use |
|--------|-----|
| Historical return/volatility | Rolling windows, CAGR, drawdown |
| Risk-adjusted metrics | Sharpe, Sortino, beta vs benchmark |
| Correlation & risk contribution | Diversification diagnostics |
| ETF overlap analysis | Pairwise holdings overlap and concentration warnings |
| Monte Carlo simulation | Forward path distributions |
| Mean-variance optimization | Efficient frontier |
| Macro engine | Forward projection assumptions |
| Rule-based insights | Portfolio coaching cards |
| AMI integration | Structured analytical questions with solver handoff |

---

## Technical Architecture

```
streamlit_app.py              # UI shell, tabs, sidebar, exports
portfolio_core.py             # Core calculations (stable contract)
dashboard_charts.py           # Plotly chart builders
etf_holdings.py               # ETF constituent loading + overlap analysis
investment_persistent_state.py # Disk + cloud restore, holdings sync
components/                   # Beginner coach, macro, rebalancing, ETF explorer panels
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

## Screenshots

> Enable portfolio screenshot mode in the sidebar before capturing.

| # | Page | Filename (placeholder) | What to show |
|---|------|------------------------|--------------|
| 1 | Portfolio Health | `screenshots/01-portfolio-health.png` | Core metrics + correlation heatmap |
| 2 | Efficient Frontier | `screenshots/02-efficient-frontier.png` | Optimizer results + highlighted portfolios |
| 3 | Monte Carlo | `screenshots/03-monte-carlo.png` | Path fan + confidence intervals |
| 4 | ETF Holdings Explorer | `screenshots/04-etf-holdings-explorer.png` | ETF overlap pairs + concentration warnings |
| 5 | Beginner Mode | `screenshots/05-beginner-coach.png` | Goal cards + guided next step |
| 6 | Applied Investment Insight | `screenshots/06-ami-insight.png` | Sidebar insight + returned AMI answer |

---

## Portfolio Value

Investment Portfolio Analyzer shows that you can:

- Build a **quantitative finance engine** decoupled from Streamlit UI concerns
- Translate portfolio theory into **actionable beginner and advanced workflows**
- Detect **hidden ETF concentration** through holdings-level overlap analysis
- Integrate **LLM-assisted reasoning** without losing structured page and portfolio context
- Ship **cross-app intelligence** — questions and insights flow between Investment, AMI, and Command Center
- Bridge financial theory and practical decision support through interactive software

A hiring manager can grasp scope and sophistication in **2–3 minutes** from this README plus the live demo.

---

## Local Setup

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

## Roadmap

**Near term**
- [ ] `prepare_investment_workspace()` wrapper at startup (sync protocol parity with Music)
- [ ] Cross-device holdings validation (Sprint D P-rows)
- [ ] AMI solver routing polish for macro/optimizer questions

**Medium term**
- [ ] Tax-lot and cost-basis modeling
- [ ] Factor exposure and style analysis
- [ ] CI matrix with workspace ownership tests on every PR

---

## Testing

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
