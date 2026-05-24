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
