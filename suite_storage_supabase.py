"""
Supabase PostgREST backend for cross-deployment suite activity.
"""

from __future__ import annotations

import json
from activity_time import normalize_timestamp_iso, utc_now_iso
from datetime import datetime
from typing import Any

from suite_storage_config import SuiteCloudConfig, get_auth_api_key, get_cloud_config, reset_cloud_config_cache

MAX_EVENTS = 2000
ACTIVE_APP_KEYS = frozenset(
    {
        "music",
        "investment",
        "baseball",
        "nba",
        "applied_intelligence",
        "future_lens",
    }
)

_TABLE_USERS = "suite_users"
_TABLE_EVENTS = "suite_activity_events"
_TABLE_STATE = "suite_app_current_state"
_TABLE_RESUME = "suite_resume_items"
_TABLE_SAVED = "suite_saved_items"
_TABLE_SETTINGS = "suite_user_settings"
_SAVED_ITEM_CONFLICT_COLS = "user_id,app,item_type,item_key"
_FULL_SESSION_KEY = "full_session"
_READ_CACHE_KEY = "_suite_supabase_get_cache"


class AccountScopeError(RuntimeError):
    """A cloud read/write that could reach another account's rows was refused."""


def _empty_when_unscoped(default_factory):
    """Read helpers return an empty result (never another account's) when there is no account."""
    import functools

    def wrap(fn):
        @functools.wraps(fn)
        def inner(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except AccountScopeError:
                return default_factory()

        return inner

    return wrap


def _read_cache_bucket() -> dict[tuple[str, str, tuple[tuple[str, str], ...]], tuple[int, Any]]:
    try:
        import streamlit as st  # noqa: WPS433

        raw = st.session_state.get(_READ_CACHE_KEY)
        if isinstance(raw, dict):
            return raw
        bucket: dict[tuple[str, str, tuple[tuple[str, str], ...]], tuple[int, Any]] = {}
        st.session_state[_READ_CACHE_KEY] = bucket
        return bucket
    except Exception:
        return {}


def _cache_key(method: str, path: str, params: dict[str, str] | None) -> tuple[str, str, tuple[tuple[str, str], ...]]:
    items = tuple(sorted((params or {}).items()))
    return (method.upper(), path, items)


def _invalidate_read_cache_for_table(table: str) -> None:
    bucket = _read_cache_bucket()
    if not bucket:
        return
    drop = [k for k in bucket if k[1] == table or k[1].startswith(f"{table}/")]
    for key in drop:
        bucket.pop(key, None)


def _row_to_state_dict(row: dict[str, Any], *, logical: str) -> dict[str, Any]:
    metrics = row.get("metrics")
    if not isinstance(metrics, dict):
        metrics = {}
    page = str(row.get("page") or "")
    if not page.strip():
        full_session = metrics.get(_FULL_SESSION_KEY)
        if isinstance(full_session, dict):
            page = str(full_session.get("view_mode") or full_session.get("page") or "")
    return {
        "page": page,
        "summary": str(row.get("summary") or ""),
        "metrics": metrics,
        "updated_at": str(row.get("updated_at") or "")[:19],
    }


@_empty_when_unscoped(dict)
def load_current_state_meta_for_app(app: str) -> dict[str, Any]:
    """Lightweight row metadata for one app (no metrics / full_session download)."""
    from suite_workspace import logical_storage_app_key

    storage_app = _scoped_storage_app(app)
    logical = logical_storage_app_key(storage_app)
    if logical not in ACTIVE_APP_KEYS:
        return {}
    params: dict[str, str] = {
        "select": "app,page,summary,updated_at",
        "app": f"eq.{storage_app}",
        "limit": "1",
    }
    uid = _read_user_id()
    if uid:
        params["user_id"] = f"eq.{uid}"
    with _egress("load_current_state_meta_for_app"):
        rows = _request("GET", _TABLE_STATE, params=params, prefer="return=representation")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return {}
    row = rows[0]
    return {
        "app": logical,
        "page": str(row.get("page") or ""),
        "summary": str(row.get("summary") or ""),
        "updated_at": str(row.get("updated_at") or "")[:19],
    }


@_empty_when_unscoped(dict)
def load_current_state_for_app(app: str) -> dict[str, Any]:
    """Fetch one app's state row including metrics/full_session (not all apps)."""
    from suite_workspace import logical_storage_app_key

    storage_app = _scoped_storage_app(app)
    logical = logical_storage_app_key(storage_app)
    if logical not in ACTIVE_APP_KEYS:
        return {}
    params: dict[str, str] = {
        "select": "app,page,summary,metrics,updated_at",
        "app": f"eq.{storage_app}",
        "limit": "1",
    }
    uid = _read_user_id()
    if uid:
        params["user_id"] = f"eq.{uid}"
    with _egress("load_current_state_for_app"):
        rows = _request("GET", _TABLE_STATE, params=params, prefer="return=representation")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return {}
    return _row_to_state_dict(rows[0], logical=logical)


@_empty_when_unscoped(dict)
def load_current_states_summary() -> dict[str, dict[str, Any]]:
    """All workspace apps — page/summary/updated_at only (no metrics blobs)."""
    from suite_workspace import logical_storage_app_key, workspace_storage_app_keys

    allowed = workspace_storage_app_keys()
    params: dict[str, str] = {"select": "app,page,summary,updated_at"}
    uid = _read_user_id()
    if uid:
        params["user_id"] = f"eq.{uid}"
    if allowed:
        params["app"] = f"in.({','.join(sorted(allowed))})"
    with _egress("load_current_states_summary"):
        rows = _request("GET", _TABLE_STATE, params=params, prefer="return=representation")
    if not isinstance(rows, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        storage_app = str(row.get("app") or "")
        if storage_app not in allowed:
            continue
        logical = logical_storage_app_key(storage_app)
        if logical not in ACTIVE_APP_KEYS:
            continue
        out[logical] = {
            "page": str(row.get("page") or ""),
            "summary": str(row.get("summary") or ""),
            "metrics": {},
            "updated_at": str(row.get("updated_at") or "")[:19],
        }
    return out


def _merge_state_metrics(scoped_app_key: str, incoming: dict[str, Any] | None) -> dict[str, Any]:
    """Shallow-merge metrics; preserve ``full_session`` when incoming omits it."""
    new_metrics = dict(incoming or {})
    try:
        params: dict[str, str] = {
            "select": "metrics",
            "app": f"eq.{scoped_app_key}",
        }
        uid = _read_user_id()
        if uid:
            params["user_id"] = f"eq.{uid}"
        rows = _request("GET", _TABLE_STATE, params=params, prefer="return=representation")
        prior: dict[str, Any] = {}
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            raw = rows[0].get("metrics")
            if isinstance(raw, dict):
                prior = raw
        if not prior:
            return new_metrics
        merged = dict(prior)
        merged.update(new_metrics)
        if _FULL_SESSION_KEY not in new_metrics and _FULL_SESSION_KEY in prior:
            merged[_FULL_SESSION_KEY] = prior[_FULL_SESSION_KEY]
        return merged
    except Exception:
        return new_metrics


def _now_iso() -> str:
    """UTC with an explicit offset. ``datetime.now()`` (naive server-local time) was read as
    UTC by Command Center, shifting events by the server's UTC offset."""
    return utc_now_iso()


def _headers(cfg: SuiteCloudConfig, *, prefer: str = "return=minimal") -> dict[str, str]:
    return {
        "apikey": cfg.key,
        "Authorization": f"Bearer {cfg.key}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def _egress(source: str):
    try:
        from suite_egress_trace import egress_source

        return egress_source(source)
    except ImportError:
        from contextlib import nullcontext

        return nullcontext()


def _request(
    method: str,
    path: str,
    *,
    cfg: SuiteCloudConfig | None = None,
    params: dict[str, str] | None = None,
    json_body: Any = None,
    prefer: str = "return=minimal",
) -> Any:
    import requests  # lazy import — available in all suite apps

    config = cfg or get_cloud_config()
    if config is None:
        raise RuntimeError("Supabase is not configured")

    table = str(path or "").split("/", 1)[0]
    method_u = method.upper()
    cache_key = _cache_key(method_u, table, params)
    cached = False
    if method_u == "GET":
        bucket = _read_cache_bucket()
        hit = bucket.get(cache_key)
        if hit is not None:
            cached = True
            try:
                from suite_egress_trace import record_egress

                record_egress(
                    method=method_u,
                    path=table,
                    bytes_in=hit[0],
                    cached=True,
                )
            except ImportError:
                pass
            return hit[1]

    url = f"{config.url}/rest/v1/{path}"
    response = requests.request(
        method,
        url,
        headers=_headers(config, prefer=prefer),
        params=params,
        json=json_body,
        timeout=15,
    )
    if response.status_code >= 400:
        detail = response.text[:500]
        raise RuntimeError(f"Supabase {method} {path} failed ({response.status_code}): {detail}")
    bytes_in = len(response.content or b"")
    bytes_out = 0
    if json_body is not None:
        try:
            bytes_out = len(json.dumps(json_body, default=str).encode("utf-8"))
        except Exception:
            bytes_out = 0
    try:
        from suite_egress_trace import record_egress

        record_egress(method=method_u, path=table, bytes_in=bytes_in, bytes_out=bytes_out, cached=False)
    except ImportError:
        pass
    if method_u != "GET":
        _invalidate_read_cache_for_table(table)
    if not response.content:
        return None
    try:
        parsed = response.json()
    except json.JSONDecodeError:
        parsed = None
    if method_u == "GET" and parsed is not None:
        _read_cache_bucket()[cache_key] = (bytes_in, parsed)
    return parsed


def normalize_app_key(app: str) -> str:
    cleaned = str(app or "").strip()
    if cleaned == "math":
        return "applied_intelligence"
    return cleaned


def _scoped_storage_app(app: str) -> str:
    """Workspace-scoped cloud key (Daniel keeps legacy unscoped)."""
    app_key = normalize_app_key(app)
    if "__" in app_key:
        return app_key
    try:
        from suite_workspace import scoped_cloud_app_id

        return scoped_cloud_app_id(app_key)
    except Exception:
        return app_key


def _logical_app_key(storage_app: str) -> str:
    try:
        from suite_workspace import logical_storage_app_key

        return logical_storage_app_key(storage_app)
    except ImportError:
        return normalize_app_key(str(storage_app or "").split("__", 1)[0])


def _workspace_storage_app_keys() -> list[str]:
    try:
        from suite_workspace import workspace_storage_app_keys

        return sorted(workspace_storage_app_keys())
    except Exception:
        return [normalize_app_key(app) for app in sorted(ACTIVE_APP_KEYS)]


def _isolation_required() -> bool:
    """Sign-in on: every row must belong to this session's own account."""
    try:
        from suite_user import account_isolation_required

        return bool(account_isolation_required())
    except ImportError:
        return False


def _scoped_user_id() -> str:
    from suite_user import get_account_user_id

    return get_account_user_id()


def _cloud_user_id() -> str | None:
    uid = _scoped_user_id()
    if not uid or uid.startswith("local:"):
        return None
    return uid


def _read_user_id() -> str | None:
    """
    ``user_id`` filter for a read. Raises :class:`AccountScopeError` when sign-in is on
    and this session has no cloud account: an unfiltered read would return another
    account's row.
    """
    uid = _cloud_user_id()
    if uid is None and _isolation_required():
        raise AccountScopeError("No signed-in account for this session; cloud read refused.")
    return uid


def _write_user_id() -> str | None:
    """``user_id`` for a write; refuses (raises) under sign-in when there is no account."""
    uid = _cloud_user_id()
    if uid is None and _isolation_required():
        raise AccountScopeError("No signed-in account for this session; cloud write refused.")
    return uid


def _owned_user_id() -> str:
    """Account id for tables whose ``user_id`` is NOT NULL (saved items, settings)."""
    uid = _cloud_user_id()
    if uid is None:
        raise AccountScopeError("No cloud account for this session.")
    return uid


def _apply_user_scope_params(params: dict[str, str]) -> None:
    """
    Scope an activity / resume read to this account.

    Sign-in on: this account's rows only. Rows with no ``user_id`` are legacy writes from
    before accounts existed; they cannot be attributed, so no account is shown them.
    Sign-in off (single-tenant): the account's rows plus those legacy rows, as before.
    """
    uid = _read_user_id()
    if uid and _isolation_required():
        params["user_id"] = f"eq.{uid}"
    elif uid:
        params["or"] = f"(user_id.eq.{uid},user_id.is.null)"
    else:
        params["user_id"] = "is.null"


def _fresh_get(table: str, params: dict[str, str]) -> Any:
    """GET that bypasses and does not populate the per-session read cache."""
    bucket = _read_cache_bucket()
    key = _cache_key("GET", table, params)
    bucket.pop(key, None)
    try:
        return _request("GET", table, params=params, prefer="return=representation")
    finally:
        bucket.pop(key, None)


def _current_state_owner(app_key: str) -> tuple[bool, str | None]:
    """``(row_exists, owner_user_id)`` for one state key, read fresh."""
    rows = _fresh_get(_TABLE_STATE, {"select": "user_id", "app": f"eq.{app_key}", "limit": "1"})
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return False, None
    owner = rows[0].get("user_id")
    return True, (str(owner).strip() if owner else None)


def _guard_current_state_owner(app_key: str, uid: str | None) -> None:
    """
    Refuse a state upsert that would replace another account's row.

    ``suite_app_current_state`` is keyed by ``app`` alone in the database today, so a
    plain upsert by a second account silently replaces the first account's row,
    ``user_id`` included. Until the per-account key migration runs
    (docs/sql/investment_account_isolation_DRAFT.sql), the app checks the owner first.
    """
    if not _isolation_required():
        return
    exists, owner = _current_state_owner(app_key)
    if not exists:
        return
    if owner is None:
        raise AccountScopeError(
            f"Cloud state row {app_key!r} has no owner; refusing to claim it (needs owner review)."
        )
    if owner != uid:
        raise AccountScopeError(f"Cloud state row {app_key!r} belongs to another account; write refused.")



_UNCLAIMABLE_EXTERNAL_IDS = frozenset({"", "user_unidentified", "unauthenticated"})


def ensure_user_row(
    external_id: str,
    *,
    email: str = "",
    display_name: str = "",
) -> str:
    """Create or fetch suite_users row; returns Supabase UUID."""
    raw = str(external_id or "").strip()
    if _isolation_required() and raw.lower() in _UNCLAIMABLE_EXTERNAL_IDS:
        raise AccountScopeError("Refusing to resolve a shared fallback account id.")
    ext = raw or "default"
    existing = _request(
        "GET",
        _TABLE_USERS,
        params={
            "select": "id",
            "external_id": f"eq.{ext}",
            "limit": "1",
        },
        prefer="return=representation",
    )
    if isinstance(existing, list) and existing and isinstance(existing[0], dict):
        row_id = str(existing[0].get("id") or "").strip()
        if row_id:
            return row_id
    created = _request(
        "POST",
        _TABLE_USERS,
        json_body={
            "external_id": ext,
            "email": email or "",
            "display_name": display_name or ext.replace("_", " ").title(),
        },
        prefer="return=representation",
    )
    if isinstance(created, list) and created and isinstance(created[0], dict):
        row_id = str(created[0].get("id") or "").strip()
        if row_id:
            return row_id
    if isinstance(created, dict):
        row_id = str(created.get("id") or "").strip()
        if row_id:
            return row_id
    raise RuntimeError(f"Could not resolve suite_users row for external_id={ext!r}")


_PROFILE_BINDING_APP = "_auth_binding"


def _is_conflict_409(exc: BaseException) -> bool:
    """A duplicate-key refusal (HTTP 409 / SQLSTATE 23505), nothing broader."""
    text = str(exc)
    return "(409)" in text or "23505" in text


def load_profile_binding(profile_row_id: str) -> dict[str, Any]:
    """The Supabase Auth user a ``suite_users`` profile is bound to (``{}`` when unbound)."""
    pid = str(profile_row_id or "").strip()
    if not pid:
        return {}
    rows = _fresh_get(
        _TABLE_SETTINGS,
        {
            "select": "settings",
            "user_id": f"eq.{pid}",
            "app": f"eq.{_PROFILE_BINDING_APP}",
            "limit": "1",
        },
    )
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        settings = rows[0].get("settings")
        if isinstance(settings, dict):
            return settings
    return {}


def claim_profile_binding(external_id: str, *, auth_user_id: str, email: str = "") -> bool:
    """
    Bind profile ``external_id`` to one Supabase Auth user; True when it is bound to ``auth_user_id``.

    First claim wins. The insert never overwrites an existing binding
    (``resolution=ignore-duplicates`` on the ``(user_id, app)`` primary key), and the
    binding is re-read after the write, so two accounts racing for one profile cannot
    both get it. A profile bound to another Auth user returns False: the caller uses a
    private id instead. No existing row is changed.
    """
    uid = str(auth_user_id or "").strip()
    ext = str(external_id or "").strip()
    if not uid or not ext:
        return False
    row_id = ensure_user_row(ext, email=str(email or "").strip().lower())
    bound = str(load_profile_binding(row_id).get("auth_user_id") or "").strip()
    if bound:
        return bound == uid
    body = {
        "user_id": row_id,
        "app": _PROFILE_BINDING_APP,
        "settings": {
            "auth_user_id": uid,
            "email": str(email or "").strip().lower(),
            "bound_at": _now_iso(),
        },
        "updated_at": _now_iso(),
    }
    try:
        _request(
            "POST",
            _TABLE_SETTINGS,
            params={"on_conflict": "user_id,app"},
            json_body=body,
            prefer="resolution=ignore-duplicates,return=minimal",
        )
    except RuntimeError as exc:
        if not _is_conflict_409(exc):
            # e.g. no unique constraint matching on_conflict: a plain insert still can't
            # overwrite an existing binding (the primary key refuses a duplicate).
            try:
                _request("POST", _TABLE_SETTINGS, json_body=body, prefer="return=minimal")
            except RuntimeError as exc2:
                if not _is_conflict_409(exc2):
                    raise
    bound = str(load_profile_binding(row_id).get("auth_user_id") or "").strip()
    return bound == uid


def ping() -> bool:
    cfg = get_cloud_config()
    if cfg is None:
        return False
    try:
        _request("GET", _TABLE_EVENTS, cfg=cfg, params={"select": "id", "limit": "1"})
        return True
    except Exception:
        return False


_supabase_client: Any | None = None


def get_supabase_client() -> Any:
    """
    Lazy Supabase Python client for Auth API (``client.auth``).

    Requires ``supabase`` package and ``supabase_url`` + auth API key in secrets.
    """
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client
    cfg = get_cloud_config()
    if cfg is None:
        raise RuntimeError(
            "Supabase is not configured — set supabase_url and supabase_key under [suite_activity]."
        )
    auth_key = get_auth_api_key()
    if not auth_key:
        raise RuntimeError(
            "Supabase Auth key missing — set supabase_anon_key under [suite_activity] "
            "(or SUITE_SUPABASE_ANON_KEY env)."
        )
    try:
        from supabase import create_client
    except ImportError as exc:
        raise RuntimeError(
            "Python package 'supabase' is not installed — add supabase>=2.0.0 to requirements.txt."
        ) from exc
    _supabase_client = create_client(cfg.url, auth_key)
    return _supabase_client


def reset_supabase_client_cache() -> None:
    global _supabase_client
    _supabase_client = None


def append_event(
    app: str,
    event: str,
    *,
    page: str = "",
    metrics: dict[str, Any] | None = None,
) -> str:
    app_key = _scoped_storage_app(app)
    if not app_key:
        return ""
    try:
        from suite_activity_namespace import stamp_activity_metrics

        stamped = stamp_activity_metrics(metrics)
    except ImportError:
        stamped = dict(metrics or {})
    body: dict[str, Any] = {
        "app": app_key,
        "event": event,
        "page": page or "",
        "timestamp": _now_iso(),
        "metrics": stamped,
    }
    uid = _write_user_id()
    if uid:
        body["user_id"] = uid
    event_key = str(stamped.get("event_key") or "").strip()
    if event_key:
        # One event per confirmed action per account, across reruns, sessions and devices.
        existing = _fresh_get(
            _TABLE_EVENTS,
            {
                "select": "id",
                "app": f"eq.{app_key}",
                "user_id": f"eq.{uid}" if uid else "is.null",
                "metrics->>event_key": f"eq.{event_key}",
                "limit": "1",
            },
        )
        if isinstance(existing, list) and existing and isinstance(existing[0], dict):
            return str(existing[0].get("id") or "")
    rows = _request(
        "POST",
        _TABLE_EVENTS,
        json_body=body,
        prefer="return=representation",
    )
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return str(rows[0].get("id") or "")
    if isinstance(rows, dict):
        return str(rows.get("id") or "")
    return ""


def save_current_state(
    app: str,
    *,
    page: str = "",
    summary: str = "",
    metrics: dict[str, Any] | None = None,
) -> None:
    app_key = _scoped_storage_app(app)
    # Check the logical app of the scoped key (``investment__coakley11`` -> ``investment``).
    # Checking the scoped key itself silently skipped every save outside workspace daniel.
    logical_app = _logical_app_key(app_key)
    if logical_app not in ACTIVE_APP_KEYS:
        return
    uid = _write_user_id()
    _guard_current_state_owner(app_key, uid)
    body: dict[str, Any] = {
        "app": app_key,
        "page": page or "",
        "summary": summary or "",
        "metrics": _merge_state_metrics(app_key, metrics),
        "updated_at": _now_iso(),
    }
    if uid:
        body["user_id"] = uid
    _request(
        "POST",
        _TABLE_STATE,
        json_body=body,
        prefer="resolution=merge-duplicates,return=minimal",
    )


def upsert_resume_item(
    app: str,
    item_key: str,
    *,
    title: str,
    subtitle: str = "",
    action_url: str = "",
) -> None:
    app_key = _scoped_storage_app(app)
    # Check the logical app of the scoped key (``investment__coakley11`` -> ``investment``).
    # Checking the scoped key itself silently skipped every save outside workspace daniel.
    logical_app = _logical_app_key(app_key)
    key = str(item_key or "").strip()
    title_clean = str(title or "").strip()
    if not app_key or not key or not title_clean:
        return
    if logical_app not in ACTIVE_APP_KEYS:
        return
    body: dict[str, Any] = {
        "app": app_key,
        "item_key": key,
        "title": title_clean,
        "subtitle": subtitle or "",
        "action_url": action_url or "",
        "valid": True,
        "updated_at": _now_iso(),
    }
    uid = _write_user_id()
    if uid:
        body["user_id"] = uid
    # The table's primary key is a generated id and rows are unique per
    # (user_id, app, item_key). A plain "merge-duplicates" POST resolves on the id, so the
    # second write of a key failed with 409 -- and because record_activity wrote the
    # resume item before the event, every later event for that key was lost too.
    # Update this account's row first; insert only when there is none.
    match = {
        "app": f"eq.{app_key}",
        "item_key": f"eq.{key}",
        "user_id": f"eq.{uid}" if uid else "is.null",
    }
    patch = {k: v for k, v in body.items() if k not in ("app", "item_key", "user_id")}
    updated = _request("PATCH", _TABLE_RESUME, params=match, json_body=patch, prefer="return=representation")
    if isinstance(updated, list) and updated:
        return
    try:
        _request("POST", _TABLE_RESUME, json_body=body, prefer="return=minimal")
    except RuntimeError as exc:
        if not _is_duplicate_key_error(exc):
            raise
        _request("PATCH", _TABLE_RESUME, params=match, json_body=patch, prefer="return=minimal")


def invalidate_resume_item(app: str, item_key: str) -> None:
    app_key = _scoped_storage_app(app)
    key = str(item_key or "").strip()
    if not app_key or not key:
        return
    params: dict[str, str] = {"app": f"eq.{app_key}", "item_key": f"eq.{key}"}
    uid = _write_user_id()
    if uid:
        params["user_id"] = f"eq.{uid}"
    _request(
        "PATCH",
        _TABLE_RESUME,
        params=params,
        json_body={"valid": False, "updated_at": _now_iso()},
    )


def invalidate_app_resume_items(app: str) -> None:
    app_key = _scoped_storage_app(app)
    if not app_key:
        return
    params: dict[str, str] = {"app": f"eq.{app_key}"}
    uid = _write_user_id()
    if uid:
        params["user_id"] = f"eq.{uid}"
    _request(
        "PATCH",
        _TABLE_RESUME,
        params=params,
        json_body={"valid": False, "updated_at": _now_iso()},
    )


@_empty_when_unscoped(list)
def load_events(limit: int = MAX_EVENTS) -> list[dict[str, Any]]:
    from suite_workspace import logical_storage_app_key, workspace_storage_app_keys

    allowed = workspace_storage_app_keys()
    params: dict[str, str] = {
        "select": "app,event,page,timestamp,metrics",
        "order": "timestamp.desc",
        "limit": str(limit),
    }
    _apply_user_scope_params(params)
    if allowed:
        params["app"] = f"in.({','.join(sorted(allowed))})"
    with _egress("load_events"):
        rows = _request(
            "GET",
            _TABLE_EVENTS,
            params=params,
            prefer="return=representation",
        )
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in reversed(rows):
        if not isinstance(row, dict):
            continue
        storage_app = str(row.get("app") or "")
        if storage_app not in allowed:
            continue
        metrics = row.get("metrics")
        if not isinstance(metrics, dict):
            metrics = {}
        raw_ts = str(row.get("timestamp") or "")
        out.append(
            {
                "app": logical_storage_app_key(storage_app),
                "event": str(row.get("event") or ""),
                "page": str(row.get("page") or ""),
                "timestamp": normalize_timestamp_iso(raw_ts) or raw_ts,
                "metrics": metrics,
            }
        )
    return out


@_empty_when_unscoped(dict)
def load_current_states(*, include_metrics: bool = False) -> dict[str, dict[str, Any]]:
    """
    Load current app states for active workspace.

    Default is summary-only (no metrics/full_session) to limit Supabase egress.
    Pass ``include_metrics=True`` only when shallow resume hints inside metrics are required.
    """
    if not include_metrics:
        return load_current_states_summary()
    from suite_workspace import logical_storage_app_key, workspace_storage_app_keys

    allowed = workspace_storage_app_keys()
    params: dict[str, str] = {"select": "app,page,summary,metrics,updated_at"}
    uid = _read_user_id()
    if uid:
        params["user_id"] = f"eq.{uid}"
    if allowed:
        params["app"] = f"in.({','.join(sorted(allowed))})"
    with _egress("load_current_states"):
        rows = _request(
            "GET",
            _TABLE_STATE,
            params=params,
            prefer="return=representation",
        )
    if not isinstance(rows, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        storage_app = str(row.get("app") or "")
        if storage_app not in allowed:
            continue
        logical = logical_storage_app_key(storage_app)
        if logical not in ACTIVE_APP_KEYS:
            continue
        out[logical] = _row_to_state_dict(row, logical=logical)
    return out


@_empty_when_unscoped(list)
def load_active_resume_items(limit: int = 8, *, app: str | None = None) -> list[dict[str, Any]]:
    from suite_workspace import logical_storage_app_key

    app_keys = [_scoped_storage_app(app)] if app else _workspace_storage_app_keys()
    if not app_keys:
        return []
    params: dict[str, str] = {"select": "app,item_key,title,subtitle,action_url,updated_at"}
    _apply_user_scope_params(params)
    with _egress("load_active_resume_items"):
        rows = _request(
            "GET",
            _TABLE_RESUME,
            params={
                **params,
                "valid": "eq.true",
                "order": "updated_at.desc",
                "limit": str(limit),
                "app": f"in.({','.join(app_keys)})",
            },
            prefer="return=representation",
        )
    if not isinstance(rows, list):
        return []
    return [
        {
            "app": logical_storage_app_key(str(row.get("app") or "")),
            "item_key": str(row.get("item_key") or ""),
            "title": str(row.get("title") or ""),
            "subtitle": str(row.get("subtitle") or ""),
            "action_url": str(row.get("action_url") or ""),
            "updated_at": str(row.get("updated_at") or "")[:19],
        }
        for row in rows
        if isinstance(row, dict)
    ]


def _is_duplicate_key_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "409" in str(exc) or "duplicate key" in msg or "unique constraint" in msg


def upsert_saved_item(
    app: str,
    item_type: str,
    item_key: str,
    *,
    title: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Idempotent write for ``suite_saved_items``.

    Uses PostgREST upsert on ``(user_id, app, item_type, item_key)``; falls back to
  PATCH when a duplicate-key 409 still occurs (older PostgREST / missing on_conflict).
    """
    app_key = _scoped_storage_app(app)
    key = str(item_key or "").strip()
    title_clean = str(title or "").strip()
    itype = str(item_type or "item").strip() or "item"
    if not app_key or not key or not title_clean:
        return {"write_mode": "skipped", "duplicate_handled": False}
    uid = _owned_user_id()
    row_body = {
        "user_id": uid,
        "app": app_key,
        "item_type": itype,
        "item_key": key,
        "title": title_clean,
        "payload": payload or {},
        "valid": True,
        "updated_at": _now_iso(),
    }
    patch_body = {
        "title": title_clean,
        "payload": payload or {},
        "valid": True,
        "updated_at": _now_iso(),
    }
    patch_params = {
        "user_id": f"eq.{uid}",
        "app": f"eq.{app_key}",
        "item_type": f"eq.{itype}",
        "item_key": f"eq.{key}",
    }
    try:
        _request(
            "POST",
            _TABLE_SAVED,
            params={"on_conflict": _SAVED_ITEM_CONFLICT_COLS},
            json_body=row_body,
            prefer="resolution=merge-duplicates,return=minimal",
        )
        return {"write_mode": "upsert", "duplicate_handled": False}
    except RuntimeError as exc:
        if not _is_duplicate_key_error(exc):
            raise
        _request(
            "PATCH",
            _TABLE_SAVED,
            params=patch_params,
            json_body=patch_body,
            prefer="return=minimal",
        )
        return {"write_mode": "update", "duplicate_handled": True}


_AUTH_BROWSER_APP = "_auth_browser"
_AUTH_SESSION_ITEM_TYPE = "browser_session"


def _browser_auth_bridge_enabled() -> bool:
    """URL sign-in restore is disabled (security hotfix 2026-11-23): no bridge token is read or written."""
    try:
        from suite_auth_browser import url_auth_restore_enabled

        return bool(url_auth_restore_enabled())
    except ImportError:
        return False


def save_browser_auth_session(
    session_id: str,
    *,
    user_id: str,
    tokens: dict[str, Any],
) -> None:
    """Persist refreshable auth tokens server-side; URL holds opaque session id only."""
    if not _browser_auth_bridge_enabled():
        return
    sid = str(session_id or "").strip()
    uid = str(user_id or "").strip()
    access = str((tokens or {}).get("access_token") or "").strip()
    refresh = str((tokens or {}).get("refresh_token") or "").strip()
    if not sid or not uid or not access or not refresh:
        return
    payload = {
        "access_token": access,
        "refresh_token": refresh,
        "expires_at": int((tokens or {}).get("expires_at") or 0),
    }
    row_body = {
        "user_id": uid,
        "app": _AUTH_BROWSER_APP,
        "item_type": _AUTH_SESSION_ITEM_TYPE,
        "item_key": sid,
        "title": "Browser auth session",
        "payload": payload,
        "valid": True,
        "updated_at": _now_iso(),
    }
    patch_body = {
        "title": "Browser auth session",
        "payload": payload,
        "valid": True,
        "updated_at": _now_iso(),
    }
    patch_params = {
        "user_id": f"eq.{uid}",
        "app": f"eq.{_AUTH_BROWSER_APP}",
        "item_type": f"eq.{_AUTH_SESSION_ITEM_TYPE}",
        "item_key": f"eq.{sid}",
    }
    try:
        _request(
            "POST",
            _TABLE_SAVED,
            params={"on_conflict": _SAVED_ITEM_CONFLICT_COLS},
            json_body=row_body,
            prefer="resolution=merge-duplicates,return=minimal",
        )
    except RuntimeError as exc:
        if not _is_duplicate_key_error(exc):
            raise
        _request(
            "PATCH",
            _TABLE_SAVED,
            params=patch_params,
            json_body=patch_body,
            prefer="return=minimal",
        )


def load_browser_auth_session(session_id: str) -> dict[str, Any] | None:
    """Load token bundle by opaque browser session id (capability URL)."""
    if not _browser_auth_bridge_enabled():
        return None
    sid = str(session_id or "").strip()
    if not sid:
        return None
    with _egress("load_browser_auth_session"):
        rows = _request(
            "GET",
            _TABLE_SAVED,
            params={
                "select": "payload,updated_at",
                "app": f"eq.{_AUTH_BROWSER_APP}",
                "item_type": f"eq.{_AUTH_SESSION_ITEM_TYPE}",
                "item_key": f"eq.{sid}",
                "valid": "eq.true",
                # Several suite apps may hold a row for one browser session id (under
                # different user_id keys); use the most recently refreshed tokens.
                "order": "updated_at.desc",
                "limit": "1",
            },
            prefer="return=representation",
        )
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return None
    payload = rows[0].get("payload")
    if not isinstance(payload, dict):
        return None
    access = str(payload.get("access_token") or "").strip()
    refresh = str(payload.get("refresh_token") or "").strip()
    if not access or not refresh:
        return None
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_at": int(payload.get("expires_at") or 0),
    }


def invalidate_browser_auth_session(session_id: str) -> None:
    sid = str(session_id or "").strip()
    if not sid:
        return
    _request(
        "PATCH",
        _TABLE_SAVED,
        params={
            "app": f"eq.{_AUTH_BROWSER_APP}",
            "item_type": f"eq.{_AUTH_SESSION_ITEM_TYPE}",
            "item_key": f"eq.{sid}",
        },
        json_body={"valid": False, "payload": {"revoked": True}, "updated_at": _now_iso()},  # erase tokens
        prefer="return=minimal",
    )


def invalidate_saved_item(app: str, item_type: str, item_key: str) -> None:
    app_key = _scoped_storage_app(app)
    key = str(item_key or "").strip()
    itype = str(item_type or "item").strip() or "item"
    if not app_key or not key:
        return
    _request(
        "PATCH",
        _TABLE_SAVED,
        params={
            "user_id": f"eq.{_owned_user_id()}",
            "app": f"eq.{app_key}",
            "item_type": f"eq.{itype}",
            "item_key": f"eq.{key}",
        },
        json_body={"valid": False, "updated_at": _now_iso()},
    )


@_empty_when_unscoped(list)
def load_saved_items(
    *,
    app: str | None = None,
    item_type: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    from suite_workspace import logical_storage_app_key

    allowed = set(_workspace_storage_app_keys())
    params: dict[str, str] = {
        "select": "app,item_type,item_key,title,payload,updated_at",
        "user_id": f"eq.{_owned_user_id()}",
        "valid": "eq.true",
        "order": "updated_at.desc",
        "limit": str(limit),
    }
    if app:
        params["app"] = f"eq.{_scoped_storage_app(app)}"
    elif allowed:
        params["app"] = f"in.({','.join(sorted(allowed))})"
    if item_type:
        params["item_type"] = f"eq.{item_type}"
    rows = _request("GET", _TABLE_SAVED, params=params, prefer="return=representation")
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        storage_app = str(row.get("app") or "")
        if not app and storage_app not in allowed:
            continue
        payload = row.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        out.append(
            {
                "app": logical_storage_app_key(storage_app),
                "item_type": str(row.get("item_type") or ""),
                "item_key": str(row.get("item_key") or ""),
                "title": str(row.get("title") or ""),
                "payload": payload,
                "updated_at": str(row.get("updated_at") or "")[:19],
            }
        )
    return out


def save_user_settings(app: str, settings: dict[str, Any]) -> None:
    app_key = str(app or "_global").strip() or "_global"
    _request(
        "POST",
        _TABLE_SETTINGS,
        json_body={
            "user_id": _owned_user_id(),
            "app": app_key,
            "settings": settings or {},
            "updated_at": _now_iso(),
        },
        prefer="resolution=merge-duplicates,return=minimal",
    )


@_empty_when_unscoped(dict)
def load_user_settings(app: str = "_global") -> dict[str, Any]:
    app_key = str(app or "_global").strip() or "_global"
    rows = _request(
        "GET",
        _TABLE_SETTINGS,
        params={
            "select": "settings,updated_at",
            "user_id": f"eq.{_owned_user_id()}",
            "app": f"eq.{app_key}",
            "limit": "1",
        },
        prefer="return=representation",
    )
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        settings = rows[0].get("settings")
        if isinstance(settings, dict):
            return settings
    return {}


def record_activity(
    app: str,
    event: str,
    *,
    page: str = "",
    metrics: dict[str, Any] | None = None,
    summary: str = "",
    resume_key: str = "",
    resume_title: str = "",
    resume_subtitle: str = "",
    action_url: str = "",
) -> str:
    # Applied-math insight events must not replace metrics.full_session (Test D portfolio).
    if str(event or "").strip() == "applied_math_insight":
        event_id = append_event(app, event, page=page, metrics=metrics)
        if resume_key and resume_title:
            upsert_resume_item(
                app,
                resume_key,
                title=resume_title,
                subtitle=resume_subtitle,
                action_url=action_url,
            )
        return event_id
    # The event is the record of what happened: write it even when the current-state or
    # resume write fails (those failures used to drop the event silently).
    side_errors: list[str] = []
    if summary or page or metrics:
        try:
            save_current_state(app, page=page, summary=summary, metrics=metrics)
        except Exception as exc:  # noqa: BLE001
            side_errors.append(f"current_state: {exc}")
    if resume_key and resume_title:
        try:
            upsert_resume_item(
                app,
                resume_key,
                title=resume_title,
                subtitle=resume_subtitle,
                action_url=action_url,
            )
        except Exception as exc:  # noqa: BLE001
            side_errors.append(f"resume: {exc}")
    event_id = append_event(app, event, page=page, metrics=metrics)
    _LAST_RECORD_SIDE_ERRORS[:] = side_errors
    return event_id


# Non-fatal write problems from the last record_activity (diagnostics only).
_LAST_RECORD_SIDE_ERRORS: list[str] = []
