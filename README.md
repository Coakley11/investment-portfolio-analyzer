# Investment Portfolio Analyzer

A Streamlit dashboard for analyzing investment portfolios with real market data from Yahoo Finance.

## Features

- Real ticker data via **yfinance**
- **Portfolio presets**: Conservative, Balanced, Aggressive, Dividend Income, Tech Growth, Retirement, All Weather
- Core metrics: return, volatility, Sharpe, Sortino, CAGR, max drawdown, beta vs SPY
- Rolling returns & volatility, correlation heatmap, risk contribution, scenario analysis
- **Monte Carlo**: paths, histogram, confidence intervals, P(loss), P(2×)
- Portfolio **optimizer** and **efficient frontier** with highlighted portfolios
- Rule-based **portfolio insights** and CSV / text **export**
- Bonds, T-bills, REITs, and dividend ETF support

## Quick start

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Project structure

| File | Purpose |
|------|---------|
| `streamlit_app.py` | Dashboard UI (tabs, sidebar, exports) |
| `portfolio_core.py` | Core calculations (keep stable when changing UI) |
| `dashboard_charts.py` | Plotly chart styling and builders |

## Disclaimer

This tool is for education and portfolio projects. It is not financial advice.

## Development workflow

This project uses two branches:

| Branch | Purpose |
|--------|---------|
| **`dev`** | Active development and testing — all new features and fixes land here first |
| **`main`** | Stable production branch — deployed to Streamlit Cloud |

**Streamlit Cloud (production):** branch **`main`**, main file **`streamlit_app.py`**.

**Analyze with Applied Math** appears at the top of the sidebar (under Command Center). Merge `dev` → `main` to ship it to production.

### Daily development

```bash
git checkout dev
git pull origin dev
# make changes, test locally
streamlit run streamlit_app.py
git add .
git commit -m "describe your change"
git push origin dev
```

### Testing before production

1. Run the app locally on `dev` and verify tabs, data loading, and exports.
2. Push changes to `origin/dev` only.
3. When stable, merge into `main` for deployment:

```bash
git checkout main
git pull origin main
git merge dev
git push origin main
```

**Do not push directly to `main` during normal development.** Keep `main` stable for Streamlit Cloud.
