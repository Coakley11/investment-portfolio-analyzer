"""Regression: AMI insight activity must not wipe cloud metrics.full_session."""

from __future__ import annotations

from unittest.mock import patch

import pytest

import suite_storage_supabase as storage


@pytest.fixture(autouse=True)
def _active_app(monkeypatch):
    monkeypatch.setattr(storage, "ACTIVE_APP_KEYS", frozenset({"investment"}))


def test_merge_state_metrics_preserves_full_session_when_incoming_omits_it():
    portfolio_session = {
        "holdings_df": [{"Ticker": "BND", "Allocation": 50}, {"Ticker": "VYM", "Allocation": 50}],
        "portfolio_built": True,
    }
    prior = {
        "full_session": portfolio_session,
        "page_hint": "Portfolio Health",
    }
    insight_blob = {
        "insight_id": "ami-test-1",
        "question_id": "q-1",
        "source_app": "investment",
        "conclusion": "test",
    }

    with patch.object(storage, "load_current_states", return_value={"investment": {"metrics": prior}}):
        merged = storage._merge_state_metrics("investment", insight_blob)

    assert merged["full_session"] == portfolio_session
    assert merged["insight_id"] == "ami-test-1"
    assert merged["page_hint"] == "Portfolio Health"


def test_merge_state_metrics_replaces_full_session_when_incoming_includes_it():
    prior = {"full_session": {"old": True}, "other": 1}
    incoming = {"full_session": {"holdings_df": [], "portfolio_built": True}}

    with patch.object(storage, "load_current_states", return_value={"investment": {"metrics": prior}}):
        merged = storage._merge_state_metrics("investment", incoming)

    assert merged["full_session"] == incoming["full_session"]
    assert merged["other"] == 1


def test_record_activity_applied_math_insight_skips_save_current_state():
    insight_blob = {"insight_id": "ami-test-2", "source_app": "investment"}
    with (
        patch.object(storage, "append_event") as mock_event,
        patch.object(storage, "save_current_state") as mock_save,
    ):
        storage.record_activity(
            "investment",
            "applied_math_insight",
            page="Portfolio Health",
            metrics=insight_blob,
            summary="insight",
        )

    mock_event.assert_called_once()
    mock_save.assert_not_called()


def test_save_current_state_merges_metrics_before_post():
    portfolio_session = {"holdings_df": [{"Ticker": "BND"}], "portfolio_built": True}
    prior = {"full_session": portfolio_session}
    captured: dict = {}

    def _fake_request(method, table, **kwargs):
        if table == storage._TABLE_STATE:
            captured["body"] = kwargs.get("json_body") or {}
        return []

    with (
        patch.object(storage, "load_current_states", return_value={"investment": {"metrics": prior}}),
        patch.object(storage, "_cloud_user_id", return_value="user-1"),
        patch.object(storage, "_request", side_effect=_fake_request),
        patch.object(storage, "normalize_app_key", return_value="investment"),
    ):
        storage.save_current_state(
            "investment",
            page="health",
            summary="activity",
            metrics={"last_event": "applied_math_insight"},
        )

    metrics = captured["body"]["metrics"]
    assert metrics["full_session"] == portfolio_session
    assert metrics["last_event"] == "applied_math_insight"
