# Investment market data (P0)

Central service: `investment_market_data.get_market_data_provider()`.

All Yahoo Finance access for portfolio analytics, ETF explorer, AMI overlap, and live quotes should go through this provider.

## Cache layers

1. In-run request deduplication (in-flight coalescing)
2. Streamlit session (`st.session_state["_inv_market_data_cache_v1"]`)
3. Process fallback bucket (tests / non-Streamlit)
4. Disk under `data/market_data_cache/` (ETF JSON, history pickle)
5. Streamlit `@st.cache_data` on analytics wrappers in `streamlit_app.py` (unchanged)

## Environment

| Variable | Default | Meaning |
|----------|---------|---------|
| `INVESTMENT_MARKET_ETF_TTL_HOURS` | 24 | ETF holdings bundle |
| `INVESTMENT_MARKET_SPOT_TTL_MINUTES` | 15 | Latest quotes |
| `INVESTMENT_MARKET_HISTORICAL_TTL_HOURS` | 24 | Price history |
| `INVESTMENT_MARKET_INFO_TTL_HOURS` | 6 | Trailing P/E / info |
| `INVESTMENT_MARKET_DISK_CACHE` | true | Persist ETF/history to disk |
| `INVESTMENT_EGRESS_STRICT` | false | Prefer cache/static over live retry |

## Developer diagnostics

With developer mode enabled, sidebar panels:

- **Supabase egress** (existing)
- **Market data cache** — Yahoo request count, cache hits, dedupe waits

## Cache invalidation (Refresh Market Data)

Sidebar **Refresh Market Data** must clear **both**:

1. ``st.cache_data`` (analytics wrappers in ``streamlit_app.py``)
2. ``invalidate_all_market_data_caches()`` (provider session + process + disk)

If only one layer is cleared, users can see stale quotes or history until tickers/dates change.

## Layering note

``@st.cache_data`` on ``load_market_data`` has no TTL by default (unchanged from pre-P0). Provider TTL applies when Streamlit cache misses. That is intentional: reruns stay fast; explicit refresh resets everything.

## Macro data

FRED / beginner macro remains in ``components/macro_data.py`` (not Yahoo). A future ``MacroDataProvider`` can mirror this package without changing ``MarketDataProvider``.

## Next (P1)

AMI orchestration package; engines consume this provider for quotes, history, and ETF holdings.
