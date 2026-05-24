# Investment Portfolio Analyzer

A Streamlit dashboard for analyzing investment portfolios with real market data from Yahoo Finance.

## Features

- Real ticker data via **yfinance**
- Annual return, volatility, and **Sharpe ratio**
- Correlation matrix and scenario analysis
- **Monte Carlo** simulation
- Portfolio **optimizer** (max Sharpe, min volatility)
- **Efficient frontier** chart
- Support for bonds, T-bills, REITs, and dividend ETFs (presets + custom tickers)

## Quick start

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Project structure

| File | Purpose |
|------|---------|
| `streamlit_app.py` | Dashboard UI (tabs, sidebar, charts) |
| `portfolio_core.py` | Core calculations (keep stable when changing UI) |

## Disclaimer

This tool is for education and portfolio projects. It is not financial advice.
