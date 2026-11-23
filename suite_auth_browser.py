"""
Browser auth persistence for Streamlit Cloud (C2b).

CookieManager/iframed cookies do not survive on Streamlit Cloud (component iframe
isolation). This module stores tokens in Supabase and keeps an opaque session id in
``st.query_params['suite_sid']``, which survives browser refresh on the same URL.

Synced to sibling repos.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

SESSION_QUERY_PARAM = "suite_sid"
SESSION_STATE_SID_KEY = "_suite_browser_session_id"

InitState = Literal["ready"]

# SECURITY (2026-11-23): URL-carried sign-in restore is DISABLED. A ``suite_sid`` value was a bearer
# capability for that account's stored tokens. With URL_AUTH_RESTORE_ENABLED = False nothing is read from
# or written to the token bridge, a ``suite_sid`` arriving in a URL is removed from the address bar and the
# record it named is revoked (marked invalid, stored tokens erased), and a page reload asks to sign in again.
URL_AUTH_RESTORE_ENABLED = False
_REVOKED_SIDS_KEY = "_suite_browser_sids_revoked"


def url_auth_restore_enabled() -> bool:
    """Whether a URL ``suite_sid`` may restore a sign-in (off: security hotfix 2026-11-23)."""
    return bool(URL_AUTH_RESTORE_ENABLED)


def _query_sid(st: Any) -> str:
    try:
        raw = st.query_params.get(SESSION_QUERY_PARAM)
    except Exception:
        return ""
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    return str(raw or "").strip()


def strip_url_auth_param(st: Any) -> bool:
    """Remove ``suite_sid`` from the URL and session and revoke the record it named (once per session).
    Returns True when a value was present. A no-op while URL restore is enabled."""
    if url_auth_restore_enabled():
        return False
    sid = _query_sid(st)
    try:
        st.session_state.pop(SESSION_STATE_SID_KEY, None)
    except Exception:
        pass
    if not sid:
        return False
    try:
        done = st.session_state.get(_REVOKED_SIDS_KEY)
        done = done if isinstance(done, list) else []
        if sid not in done:
            done.append(sid)
            st.session_state[_REVOKED_SIDS_KEY] = done[-8:]
            try:
                from suite_storage_supabase import invalidate_browser_auth_session

                invalidate_browser_auth_session(sid)
            except Exception:
                pass
    except Exception:
        pass
    try:
        if SESSION_QUERY_PARAM in st.query_params:
            del st.query_params[SESSION_QUERY_PARAM]
    except Exception:
        pass
    return True


def init_browser_auth_storage(st: Any) -> InitState:
    """Query-param storage is synchronous — always ready."""
    return "ready"


def _session_id_from_st(st: Any) -> str:
    if not url_auth_restore_enabled():
        return _query_sid(st)
    raw = st.query_params.get(SESSION_QUERY_PARAM)
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    sid = str(raw or st.session_state.get(SESSION_STATE_SID_KEY) or "").strip()
    return sid


def _set_session_id(st: Any, session_id: str) -> None:
    if not url_auth_restore_enabled():
        return
    sid = str(session_id or "").strip()
    if not sid:
        return
    st.session_state[SESSION_STATE_SID_KEY] = sid
    try:
        from suite_query_param_preservation import merge_query_params

        merge_query_params(st, {SESSION_QUERY_PARAM: sid})
    except ImportError:
        st.query_params[SESSION_QUERY_PARAM] = sid


def _clear_session_id(st: Any) -> None:
    st.session_state.pop(SESSION_STATE_SID_KEY, None)
    try:
        if SESSION_QUERY_PARAM in st.query_params:
            del st.query_params[SESSION_QUERY_PARAM]
    except Exception:
        pass


def load_browser_auth_tokens(st: Any) -> dict[str, Any] | None:
    if not url_auth_restore_enabled():
        strip_url_auth_param(st)
        return None
    sid = _session_id_from_st(st)
    if not sid:
        return None
    try:
        from suite_storage_supabase import load_browser_auth_session

        tokens = load_browser_auth_session(sid)
    except Exception:
        return None
    if tokens:
        st.session_state[SESSION_STATE_SID_KEY] = sid
    return tokens


def save_browser_auth_tokens(
    st: Any,
    tokens: dict[str, Any],
    *,
    auth_user_id: str = "",
) -> None:
    """Write tokens to Supabase and mirror opaque id in URL query params."""
    if not url_auth_restore_enabled():
        strip_url_auth_param(st)
        return
    access = str((tokens or {}).get("access_token") or "").strip()
    refresh = str((tokens or {}).get("refresh_token") or "").strip()
    if not access or not refresh:
        return
    uid = str(auth_user_id or "").strip()
    if not uid:
        return
    sid = _session_id_from_st(st) or str(uuid.uuid4())
    try:
        from suite_storage_supabase import save_browser_auth_session

        save_browser_auth_session(sid, user_id=uid, tokens=tokens)
    except Exception:
        return
    _set_session_id(st, sid)


def clear_browser_auth_tokens(st: Any) -> None:
    sid = _session_id_from_st(st)
    if sid:
        try:
            from suite_storage_supabase import invalidate_browser_auth_session

            invalidate_browser_auth_session(sid)
        except Exception:
            pass
    _clear_session_id(st)


def browser_auth_storage_status(st: Any) -> dict[str, Any]:
    """Dev diagnostics — no secret token values."""
    sid = _session_id_from_st(st)
    qp_raw = st.query_params.get(SESSION_QUERY_PARAM)
    out: dict[str, Any] = {
        "storage": "supabase_query_param",
        "session_id_present": bool(sid),
        "session_id_prefix": sid[:8] if sid else "",
        "query_param_present": bool(qp_raw),
        "cloud_payload_present": False,
        "cloud_payload_bytes": 0,
    }
    if sid:
        try:
            from suite_storage_supabase import load_browser_auth_session

            payload = load_browser_auth_session(sid)
            if payload:
                out["cloud_payload_present"] = True
                out["cloud_payload_bytes"] = len(str(payload.get("access_token") or "")) + len(
                    str(payload.get("refresh_token") or "")
                )
        except Exception as exc:
            out["cloud_error"] = str(exc)[:120]
    return out


def ensure_browser_cookies_loaded(st: Any) -> bool:
    return True
