"""
Preserve non-auth query parameters across suite auth URL rewrites (``suite_sid``).

Streamlit auth stores session id via ``st.query_params['suite_sid']``. A prior login
often leaves the browser on ``?suite_sid=…`` only; debug/resume params must survive
in ``session_state`` and be merged back when the URL is updated.

Synced to sibling repos via ``scripts/sync_suite_cloud_modules.py``.
"""

from __future__ import annotations

from typing import Any

PRESERVED_QUERY_SESSION_KEY = "_suite_preserved_query_params"

# One-shot auth / recovery params — never stash for cross-rerun replay.
_EPHEMERAL_QUERY_KEYS: frozenset[str] = frozenset(
    {
        "type",
        "token_hash",
        "code",
        "access_token",
        "refresh_token",
        "suite_auth_recovery",
        "suite_auth_access",
        "suite_auth_refresh",
        "suite_auth_hash_probe",
        "suite_auth_recovery_promoted",
        "suite_auth_landing_diag",
        "suite_auth_browser_keys",
        "suite_auth_landing",
        "suite_auth_recovery_query_promoted",
    }
)

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _query_value_raw(st: Any, name: str) -> str:
    try:
        raw = st.query_params.get(name)
    except Exception:
        return ""
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    return str(raw or "").strip()


def _preserved_map(st: Any) -> dict[str, str]:
    raw = st.session_state.get(PRESERVED_QUERY_SESSION_KEY)
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, val in raw.items():
        text = str(key or "").strip()
        if not text:
            continue
        out[text] = str(val or "").strip()
    return out


def _should_preserve_key(key: str) -> bool:
    name = str(key or "").strip()
    if not name:
        return False
    if name.lower() in ("embed", "embed_options"):
        return False
    if name in _EPHEMERAL_QUERY_KEYS:
        return False
    return True


def capture_incoming_query_params(st: Any) -> dict[str, str]:
    """Merge current ``st.query_params`` into session (union across reruns)."""
    preserved = _preserved_map(st)
    try:
        current = st.query_params.to_dict()
    except Exception:
        current = {}
    for key, val in current.items():
        if not _should_preserve_key(key):
            continue
        text = str(val or "").strip()
        if text:
            preserved[str(key)] = text
    st.session_state[PRESERVED_QUERY_SESSION_KEY] = preserved
    return dict(preserved)


def restore_preserved_query_params(st: Any) -> bool:
    """
    Re-apply preserved params missing from the live URL (one ``update`` batch).

    Returns True when ``st.query_params`` was updated.
    """
    preserved = _preserved_map(st)
    if not preserved:
        return False
    try:
        live = st.query_params.to_dict()
    except Exception:
        live = {}
    missing: dict[str, str] = {}
    for key, val in preserved.items():
        if not val:
            continue
        if key not in live or not str(live.get(key) or "").strip():
            missing[key] = val
    if not missing:
        return False
    try:
        st.query_params.update(missing)
    except Exception:
        return False
    return True


def merge_query_params(st: Any, updates: dict[str, str]) -> None:
    """Set ``updates`` without dropping preserved or current URL parameters."""
    capture_incoming_query_params(st)
    preserved = _preserved_map(st)
    try:
        live = st.query_params.to_dict()
    except Exception:
        live = {}
    merged: dict[str, str] = {}
    merged.update(preserved)
    merged.update({k: str(v).strip() for k, v in live.items() if str(v or "").strip()})
    for key, val in updates.items():
        text = str(val or "").strip()
        if text:
            merged[str(key)] = text
    st.session_state[PRESERVED_QUERY_SESSION_KEY] = {
        k: v for k, v in merged.items() if _should_preserve_key(k) and v
    }
    try:
        st.query_params.update(merged)
    except Exception:
        for key, val in updates.items():
            text = str(val or "").strip()
            if text:
                try:
                    st.query_params[key] = text
                except Exception:
                    pass


def query_param_raw(st: Any, name: str) -> str:
    """Live URL param, else preserved session copy."""
    live = _query_value_raw(st, name)
    if live:
        return live
    return str(_preserved_map(st).get(name) or "").strip()


def query_flag(st: Any, name: str) -> bool:
    return query_param_raw(st, name).lower() in _TRUTHY


def temp_slider_debug_forced(st: Any) -> bool:
    """TEMP: set ``temp_slider_debug = true`` in Streamlit secrets to bypass URL flags."""
    try:
        block = st.secrets.get("debug")
        if isinstance(block, dict) and block.get("temp_slider_debug"):
            return True
    except Exception:
        pass
    try:
        if st.secrets.get("temp_slider_debug"):
            return True
    except Exception:
        pass
    return False


def slider_debug_active(st: Any) -> bool:
    return query_flag(st, "slider_debug") or temp_slider_debug_forced(st)
