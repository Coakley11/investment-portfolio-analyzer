# Real Portfolio Snapshot (Phase A)

Ledger-backed, read-only portfolio state for the future **Real Portfolio Advisor**.

## Authoritative data path

```
portfolio_transactions (persisted)
  → portfolio_engine._ledger_from_transactions / transactions_from_records
  → spot quotes via investment_market_data.get_spot_quote_freshness
  → RealPortfolioSnapshot
```

## Not used for valuation (by design)

| Source | Role today |
|--------|------------|
| `holdings_df` | Weight-based **model** portfolio for health/optimizer; mismatch warning only |
| `sidebar_portfolio_value` | Dollar sizing for weight analytics (default $100,000) |
| Applied / plan portfolio value | Planning and contribution advisors |
| `DEFAULT_HOLDINGS`, presets, `portfolio_demo.py` | First-run / demo — **never** read by the snapshot builder |

The Real Portfolio Advisor (later phases) will consume **`RealPortfolioSnapshot` only**, with **no silent fallback** to the model portfolio.

## Missing-price policy

When a quote is unavailable:

- Shares and cost basis are retained from the ledger.
- `current_price`, `gain_loss_dollars`, and `gain_loss_pct` are **None**.
- `current_value` is **0** (unknown mark — **not** treated as worthless economic value).
- Holding flag: `missing_price`.
- Portfolio flag: `missing_prices`; `market_data_status` → **`partial`**.
- `total_market_value` = **sum of priced position marks + cash** (`known_marked_securities_value + cash`).
- `total_gain_loss_pct` is **None** if any holding lacks a price; **`priced_holdings_gain_loss_pct`** reports gain on priced names only.

This avoids `portfolio_engine.build_positions` behavior that falls back to average cost as a fake mark.

## Freshness policy

- **`as_of`**: UTC time when the snapshot was built.
- **`price_as_of`**: UTC time the quote entered the session cache or was fetched from Yahoo — **not** an exchange print timestamp.
- **`market_data_age_seconds`**: Max cache age across priced holdings (seconds since `stored_at`).
- **`market_data_status`**: `fresh` (all priced, max age ≤ 90s), `cached`, `partial` (any missing price), or `unavailable` (no prices).
- Quotes are **not** labeled real-time.

## Dual-portfolio mismatch

Read-only **`holdings_df_mismatch_warning`** when:

- Ticker sets differ between ledger and `holdings_df`, or
- Normalized weights on shared tickers differ by more than **2.0 percentage points**.

Does not change ledger totals.

## API

```python
from investment_ami.decision_support.real_portfolio_snapshot import build_real_portfolio_snapshot

result = build_real_portfolio_snapshot(session_state)
if not result.ok:
    assert result.failure.code == "no_real_ledger"
else:
    snap = result.snapshot
```

Tests: `tests/test_real_portfolio_snapshot.py`.
