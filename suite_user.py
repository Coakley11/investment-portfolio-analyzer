"""
Resolve the suite account whose data this session may read and write.

Sign-in off (single-user installs): ``suite_user_id`` in Streamlit secrets (or
``SUITE_USER_ID`` env) names the one account, the same on every device.

Sign-in on (Real Accounts): the account is always the signed-in Supabase Auth user of
*this* Streamlit session. The configured ``suite_user_id`` / ``suite_user_email`` belong
to the owner and are never used for a session, signed in or not. A session with no
signed-in user has no account (``""``): storage refuses to read or write for it.

Streamlit serves every browser session from one Python process, so nothing here may
cache "the current account" globally. The only cache maps an account key to its
``suite_users`` row id, which is the same for every session.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from suite_storage_config import get_cloud_config, reset_cloud_config_cache

NO_ACCOUNT = ""


def _auth_enabled() -> bool:
    try:
        from suite_auth import is_auth_enabled

        return bool(is_auth_enabled())
    except ImportError:
        return False


def _streamlit_session_state() -> Any | None:
    try:
        import streamlit as st  # noqa: WPS433

        ss = st.session_state
        return ss if hasattr(ss, "get") else None
    except Exception:
        return None


def _auth_external_id_for(session_state: Any | None) -> str:
    """Profile id of the signed-in account in ``session_state``; "" when none."""
    if session_state is None:
        return NO_ACCOUNT
    try:
        from suite_auth import is_authenticated, resolve_auth_external_id

        if not is_authenticated(session_state):
            return NO_ACCOUNT
        return str(resolve_auth_external_id(session_state) or "").strip()
    except Exception:
        return NO_ACCOUNT


def _secrets_block() -> Any | None:
    try:
        import streamlit as st  # noqa: WPS433

        try:
            return st.secrets.get("suite_activity")
        except Exception:
            try:
                return st.secrets["suite_activity"]
            except Exception:
                return None
    except Exception:
        return None


def get_external_user_id() -> str:
    """Account key of this session ("" when sign-in is on and nobody is signed in)."""
    if _auth_enabled():
        return _auth_external_id_for(_streamlit_session_state())
    env_id = os.environ.get("SUITE_USER_ID", "").strip()
    if env_id:
        return env_id
    block = _secrets_block()
    if block is not None:
        for name in ("suite_user_id", "user_id", "account_id"):
            val = _read_secret(block, name)
            if val:
                return val
    return "default"


def get_user_email() -> str:
    if _auth_enabled():
        ss = _streamlit_session_state()
        if ss is None:
            return ""
        try:
            from suite_auth import current_auth_email, is_authenticated

            return current_auth_email(ss) if is_authenticated(ss) else ""
        except Exception:
            return ""
    env = os.environ.get("SUITE_USER_EMAIL", "").strip()
    if env:
        return env
    block = _secrets_block()
    if block is not None:
        for name in ("suite_user_email", "user_email", "email"):
            val = _read_secret(block, name)
            if val:
                return val
    return ""


def get_display_name() -> str:
    if not _auth_enabled():
        env = os.environ.get("SUITE_USER_DISPLAY_NAME", "").strip()
        if env:
            return env
        val = _read_secret(_secrets_block(), "display_name")
        if val:
            return val
    email = get_user_email()
    if email and "@" in email:
        return email.split("@", 1)[0].replace(".", " ").title()
    ext = get_external_user_id()
    return ext.replace("_", " ").replace("-", " ").title()


def _read_secret(block: Any, name: str) -> str:
    if block is None:
        return ""
    val: Any = None
    if hasattr(block, "get"):
        try:
            val = block.get(name)
        except Exception:
            val = None
    if val is None and hasattr(block, name):
        try:
            val = getattr(block, name)
        except Exception:
            val = None
    return str(val or "").strip()


def reset_account_cache() -> None:
    reset_cloud_config_cache()
    _resolve_account_user_id_cached.cache_clear()


@lru_cache(maxsize=256)
def _resolve_account_user_id_cached(external_id: str, email: str) -> str:
    """
    ``suite_users`` UUID for one account key (cloud), else ``local:{external_id}``.

    Keyed by the account key: the previous ``lru_cache(maxsize=1)`` with no arguments
    returned whichever account resolved first to every session on the process, so one
    signed-in user read and wrote another user's rows.
    """
    ext = str(external_id or "").strip()
    cfg = get_cloud_config()
    if cfg is None:
        return f"local:{ext}"
    from suite_storage_supabase import ensure_user_row

    return ensure_user_row(ext, email=str(email or "").strip(), display_name="")


def _resolve(external_id: str, email: str) -> str:
    ext = str(external_id or "").strip()
    if not ext:
        return NO_ACCOUNT
    try:
        return _resolve_account_user_id_cached(ext, str(email or "").strip())
    except Exception:
        # Not cached: the next call retries. A failed lookup never borrows another id.
        return f"local:{ext}"


def account_user_id_for_session(session_state: Any) -> str:
    """Account id for an explicit session (sign-in flows run before ``st.session_state`` is current)."""
    if not _auth_enabled():
        return get_account_user_id()
    ext = _auth_external_id_for(session_state)
    email = ""
    try:
        from suite_auth import current_auth_email

        email = current_auth_email(session_state)
    except Exception:
        email = ""
    return _resolve(ext, email)


def get_account_user_id() -> str:
    """Account id of this session; ``""`` when sign-in is on and nobody is signed in."""
    if _auth_enabled():
        return account_user_id_for_session(_streamlit_session_state())
    return _resolve(get_external_user_id(), get_user_email())


def account_isolation_required() -> bool:
    """True when sessions belong to different people (sign-in on): storage must be scoped."""
    return _auth_enabled()


def account_mode() -> str:
    """``cloud`` when a Supabase user UUID is active, ``none`` with no account, else ``local``."""
    uid = get_account_user_id()
    if not uid:
        return "none"
    return "cloud" if not uid.startswith("local:") else "local"
