"""Tests for suite query-param preservation (auth must not drop debug flags)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from suite_query_param_preservation import (
    capture_incoming_query_params,
    merge_query_params,
    query_flag,
    slider_debug_active,
)


class _QueryParams(dict):
    def get(self, key: str, default: Any = None) -> Any:  # noqa: ANN401
        return super().get(key, default)

    def keys(self):  # noqa: ANN201
        return super().keys()

    def to_dict(self) -> dict[str, str]:
        return {str(k): str(v) for k, v in self.items()}

    def update(self, other: dict[str, str], /, **kw: str) -> None:
        super().update(other, **kw)


def _fake_st(*, query: dict[str, str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        query_params=_QueryParams(query or {}),
        session_state={},
        secrets={},
    )


def test_capture_preserves_slider_debug_when_live_url_loses_it() -> None:
    st = _fake_st(query={"slider_debug": "1"})
    capture_incoming_query_params(st)
    st.query_params.clear()
    st.query_params["suite_sid"] = "abc-123"
    assert query_flag(st, "slider_debug") is True
    assert slider_debug_active(st) is True


def test_merge_query_params_keeps_slider_debug_when_setting_suite_sid() -> None:
    st = _fake_st(query={"slider_debug": "1"})
    capture_incoming_query_params(st)
    merge_query_params(st, {"suite_sid": "session-uuid"})
    assert st.query_params.get("suite_sid") == "session-uuid"
    assert st.query_params.get("slider_debug") == "1"


def test_ephemeral_auth_keys_are_not_preserved() -> None:
    st = _fake_st(query={"token_hash": "secret", "slider_debug": "1"})
    preserved = capture_incoming_query_params(st)
    assert "token_hash" not in preserved
    assert preserved.get("slider_debug") == "1"
