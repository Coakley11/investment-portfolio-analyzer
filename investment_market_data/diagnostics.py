"""Lightweight market-data egress diagnostics (dev / tests)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MarketDataDiagnostics:
    cache_hits_session: int = 0
    cache_hits_disk: int = 0
    cache_hits_streamlit: int = 0
    cache_misses: int = 0
    yahoo_requests: int = 0
    dedupe_waits: int = 0
    estimated_bytes_saved: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)
    last_fetch: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cache_hits_session": self.cache_hits_session,
            "cache_hits_disk": self.cache_hits_disk,
            "cache_hits_streamlit": self.cache_hits_streamlit,
            "cache_misses": self.cache_misses,
            "yahoo_requests": self.yahoo_requests,
            "dedupe_waits": self.dedupe_waits,
            "estimated_bytes_saved": self.estimated_bytes_saved,
            "by_kind": dict(self.by_kind),
            "last_fetch": dict(self.last_fetch),
        }


_lock = threading.Lock()
_global = MarketDataDiagnostics()


def get_market_data_diagnostics() -> MarketDataDiagnostics:
    return _global


def reset_market_data_diagnostics() -> None:
    global _global
    with _lock:
        _global = MarketDataDiagnostics()


def record_hit(*, layer: str, kind: str, bytes_saved: int = 0) -> None:
    with _lock:
        if layer == "session":
            _global.cache_hits_session += 1
        elif layer == "disk":
            _global.cache_hits_disk += 1
        elif layer == "streamlit":
            _global.cache_hits_streamlit += 1
        _global.by_kind[kind] = _global.by_kind.get(kind, 0) + 1
        if bytes_saved > 0:
            _global.estimated_bytes_saved += bytes_saved


def record_miss(kind: str) -> None:
    with _lock:
        _global.cache_misses += 1
        _global.by_kind[f"miss:{kind}"] = _global.by_kind.get(f"miss:{kind}", 0) + 1


def record_yahoo_request(kind: str, *, count: int = 1) -> None:
    with _lock:
        _global.yahoo_requests += max(1, int(count))
        _global.by_kind[f"yahoo:{kind}"] = _global.by_kind.get(f"yahoo:{kind}", 0) + count


def record_dedupe_wait(kind: str) -> None:
    with _lock:
        _global.dedupe_waits += 1
        _global.by_kind[f"dedupe:{kind}"] = _global.by_kind.get(f"dedupe:{kind}", 0) + 1


def record_fetch_attempt(
    *,
    kind: str,
    ok: bool,
    symbols: list[str],
    start: str | None,
    end: str | None,
    shape: tuple[int, int] | None,
    attempts: list[str],
    error_class: str | None = None,
    error_message: str | None = None,
    yahoo_errors: dict[str, str] | None = None,
    warnings_list: list[str] | None = None,
) -> None:
    """Record last Yahoo fetch outcome for safe UI/dev diagnostics (no secrets)."""
    payload = {
        "kind": kind,
        "ok": bool(ok),
        "provider": "yfinance",
        "symbols": [str(s) for s in symbols[:20]],
        "symbol_count": len(symbols),
        "start": start,
        "end": end,
        "response_shape": list(shape) if shape else None,
        "attempts": list(attempts),
        "error_class": error_class,
        "error_message": (error_message or "")[:500] or None,
        "yahoo_errors": {str(k): str(v)[:300] for k, v in (yahoo_errors or {}).items()},
        "warnings": list(warnings_list or [])[:5],
    }
    with _lock:
        _global.last_fetch = payload
        key = f"fetch_ok:{kind}" if ok else f"fetch_fail:{kind}"
        _global.by_kind[key] = _global.by_kind.get(key, 0) + 1


def format_market_data_diagnostics_markdown(diag: MarketDataDiagnostics | None = None) -> str:
    d = diag or get_market_data_diagnostics()
    base = (
        f"**Market data (this process):** "
        f"Yahoo requests={d.yahoo_requests}, "
        f"session hits={d.cache_hits_session}, "
        f"disk hits={d.cache_hits_disk}, "
        f"dedupe waits={d.dedupe_waits}, "
        f"misses={d.cache_misses}, "
        f"saved≈{_human_bytes(d.estimated_bytes_saved)}"
    )
    last = d.last_fetch or {}
    if not last:
        return base
    syms = ", ".join(last.get("symbols") or []) or "—"
    shape = last.get("response_shape")
    shape_s = f"{shape[0]}×{shape[1]}" if isinstance(shape, list) and len(shape) == 2 else "—"
    status = "ok" if last.get("ok") else "failed"
    extra = (
        f"\n\n**Last fetch ({status}):** provider=`{last.get('provider')}`, "
        f"symbols=[{syms}], start=`{last.get('start')}`, end=`{last.get('end')}`, "
        f"shape=`{shape_s}`, attempts=`{', '.join(last.get('attempts') or [])}`"
    )
    if last.get("error_class"):
        extra += f", error=`{last.get('error_class')}`"
    if last.get("error_message") and not last.get("ok"):
        extra += f"\n\n_{last.get('error_message')}_"
    return base + extra


def _human_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.2f} MB"


def render_market_data_diagnostics_panel(st: Any) -> None:
    """Sidebar panel when developer tools are enabled."""
    try:
        from suite_workspace import can_show_developer_tools

        if not can_show_developer_tools(st=st):
            return
    except Exception:
        return
    with st.sidebar.expander("Market data cache (dev)", expanded=False):
        st.markdown(format_market_data_diagnostics_markdown())
        last = get_market_data_diagnostics().last_fetch or {}
        if last and not last.get("ok"):
            st.warning(
                "Last Yahoo history/spot fetch failed. On Streamlit Cloud this is often "
                "shared-IP rate limiting, not bad tickers."
            )
        st.caption("Centralized via `investment_market_data.MarketDataProvider`.")

