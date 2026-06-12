"""AMI return must not overwrite Test D portfolio state."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from applied_math_context import apply_source_state_to_session, build_source_state
from applied_math_return_insight import (
    SESSION_PENDING_KEY,
    _enrich_insight_from_question_blob,
    _insight_blob_restore_score,
    _resolve_return_source_state,
    _source_state_has_restore_payload,
    ami_return_navigation_active,
    diagnose_ami_return_source_state_resolution,
    hydrate_investment_ami_return_state,
    load_applied_math_insight,
    resolve_ami_return_source_state_for_store,
    store_applied_math_insight,
)

class _FakeSessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class _FakeSt:
    def __init__(self, params: dict[str, str] | None = None) -> None:
        self.session_state = _FakeSessionState()
        self.query_params = dict(params or {})


class TestInvestmentAmiReturnRestore(unittest.TestCase):
    def test_ami_return_navigation_active_with_insight_query(self) -> None:
        st = _FakeSt({"suite_ami_insight": "abc123"})
        self.assertTrue(ami_return_navigation_active(st, "investment"))

    def test_ami_return_navigation_inactive_with_stale_session_context_only(self) -> None:
        st = _FakeSt()
        st.session_state["_ami_return_context"] = {"source_page": "Portfolio Health"}
        st.session_state["_skip_page_restore_for"] = "Portfolio Health"
        self.assertFalse(ami_return_navigation_active(st, "investment"))

    def test_build_source_state_includes_holdings_df_records(self) -> None:
        holdings = pd.DataFrame(
            {
                "Ticker": ["BND", "VYM"],
                "Weight (%)": [50.0, 50.0],
                "Asset Type": ["Bonds", "Dividend ETF"],
            }
        )
        state = build_source_state(
            "Portfolio Health",
            {"investment_active_tab": "Portfolio Health", "holdings_df": holdings},
        )
        ent = state["entity_params"]
        self.assertIn("holdings_df", ent)
        self.assertEqual(len(ent["holdings_df"]), 2)
        self.assertIn("BND:50.0:Bonds", ent["holdings_fingerprint"])
        self.assertIn("VYM:50.0:Dividend ETF", ent["holdings_fingerprint"])

    def test_apply_deferred_restore_skips_stale_blob_holdings(self) -> None:
        import investment_persistent_state as ips

        st = _FakeSt({"suite_ami_insight": "live-return-id"})
        st.session_state["_skip_page_restore_for"] = "⑤ Portfolio Health"
        st.session_state["_suite_holdings_fp"] = "BND:50.0:Bonds|VYM:50.0:Dividend ETF"
        stale = {
            "investment_active_tab": "① Choose Goal",
            "holdings_fingerprint": "BND:30.0:Bonds|VNQ:10.0:REIT|VTI:40.0:Equity|VXUS:20.0:Equity",
            "holdings_df": [
                {"Ticker": "VTI", "Weight (%)": 40.0, "Asset Type": "Equity"},
                {"Ticker": "VXUS", "Weight (%)": 20.0, "Asset Type": "Equity"},
                {"Ticker": "BND", "Weight (%)": 30.0, "Asset Type": "Bonds"},
                {"Ticker": "VNQ", "Weight (%)": 10.0, "Asset Type": "REIT"},
            ],
            "experience": "Beginner Mode",
            "portfolio_built": False,
        }
        good_state = build_source_state(
            "⑤ Portfolio Health",
            {
                "investment_active_tab": "⑤ Portfolio Health",
                "guide_goal_choice": "Income",
                "portfolio_built": True,
                "holdings_df": pd.DataFrame(
                    {
                        "Ticker": ["BND", "VYM"],
                        "Weight (%)": [50.0, 50.0],
                        "Asset Type": ["Bonds", "Dividend ETF"],
                    }
                ),
            },
        )
        apply_source_state_to_session(st.session_state, good_state)
        ips.apply_investment_disk_state(st, stale)
        df = st.session_state["holdings_df"]
        tickers = set(df["Ticker"].astype(str).str.upper())
        self.assertEqual(tickers, {"BND", "VYM"})
        self.assertEqual(st.session_state["investment_active_tab"], "⑤ Portfolio Health")
        self.assertEqual(
            st.session_state.get("_suite_page_overwrite_source"),
            "ami_return_deferred_holdings",
        )

    def test_resolve_source_state_from_entity_params_without_widget_params(self) -> None:
        holdings = pd.DataFrame(
            {
                "Ticker": ["BND", "VYM"],
                "Weight (%)": [50.0, 50.0],
                "Asset Type": ["Bonds", "Dividend ETF"],
            }
        )
        built = build_source_state(
            "Portfolio Health",
            {"investment_active_tab": "Portfolio Health", "holdings_df": holdings},
        )
        built.pop("widget_params", None)
        built["widget_params"] = {}
        insight = {"insight_id": "x", "source_state": built, "source_app": "investment"}
        st = _FakeSt()
        resolved = _resolve_return_source_state(st, "investment", insight)
        self.assertTrue(_source_state_has_restore_payload(resolved))
        self.assertIn("BND:50.0:Bonds", str(resolved.get("entity_params", {}).get("holdings_fingerprint")))

    def test_hydrate_applies_source_state_from_question_id_url(self) -> None:
        holdings = pd.DataFrame(
            {
                "Ticker": ["BND", "VYM"],
                "Weight (%)": [50.0, 50.0],
                "Asset Type": ["Bonds", "Dividend ETF"],
            }
        )
        source_state = build_source_state(
            "Portfolio Health",
            {"investment_active_tab": "Portfolio Health", "holdings_df": holdings},
        )
        st = _FakeSt(
            {
                "suite_ami_insight": "insight-abc",
                "suite_ai_question_id": "q-123",
            }
        )
        insight = {
            "insight_id": "insight-abc",
            "question_id": "q-123",
            "source_app": "investment",
            "source_page": "Portfolio Health",
            "conclusion": "Test conclusion",
        }

        with patch(
            "applied_math_return_insight.load_applied_math_insight",
            return_value=insight,
        ), patch(
            "suite_analytical_question.load_analytical_question_source_state",
            return_value=source_state,
        ):
            ok = hydrate_investment_ami_return_state(st, "investment")

        self.assertTrue(ok)
        self.assertTrue(st.session_state.get("_ami_return_source_applied"))
        df = st.session_state["holdings_df"]
        self.assertEqual(set(df["Ticker"].astype(str).str.upper()), {"BND", "VYM"})

    def test_hydrate_missing_source_state_allows_cloud_restore(self) -> None:
        st = _FakeSt({"suite_ami_insight": "insight-only"})
        insight = {
            "insight_id": "insight-only",
            "source_app": "investment",
            "source_page": "Portfolio Health",
            "conclusion": "No source state",
        }
        st.session_state["_skip_page_restore_for"] = "Portfolio Health"

        with patch(
            "applied_math_return_insight.load_applied_math_insight",
            return_value=insight,
        ), patch(
            "suite_analytical_question.load_analytical_question_source_state",
            return_value={},
        ):
            ok = hydrate_investment_ami_return_state(st, "investment")

        self.assertFalse(ok)
        self.assertTrue(st.session_state.get("_ami_return_allow_cloud_restore"))
        self.assertNotIn("_skip_page_restore_for", st.session_state)
        self.assertEqual(
            st.session_state.get("apply_source_state_skip_reason"),
            "no_usable_source_state_on_return",
        )

    def test_resolve_ami_return_source_state_for_store_prefers_question_blob(self) -> None:
        holdings = pd.DataFrame(
            {
                "Ticker": ["BND", "VYM"],
                "Weight (%)": [50.0, 50.0],
                "Asset Type": ["Bonds", "Dividend ETF"],
            }
        )
        question_ss = build_source_state(
            "Portfolio Health",
            {"investment_active_tab": "Portfolio Health", "holdings_df": holdings},
        )
        st = _FakeSt()
        st.session_state["_suite_ai_source_state"] = {"source_app": "investment"}
        insight = {
            "insight_id": "insight-store",
            "question_id": "q-store-1",
            "source_app": "investment",
            "source_page": "Portfolio Health",
        }
        with patch(
            "suite_analytical_question.load_analytical_question_source_state",
            return_value=question_ss,
        ):
            resolved = resolve_ami_return_source_state_for_store(
                st,
                insight,
                source_state={"source_app": "investment"},
                return_context={"page": "Portfolio Health"},
            )
        self.assertTrue(_source_state_has_restore_payload(resolved))
        ent = resolved.get("entity_params") or {}
        self.assertIn("holdings_df", ent)
        self.assertEqual(ent.get("holdings_fingerprint"), question_ss["entity_params"]["holdings_fingerprint"])

    def test_load_applied_math_insight_prefers_blob_with_source_state(self) -> None:
        iid = "674475f5a3c1c57a"
        thin = {"insight_id": iid, "source_app": "investment", "conclusion": "thin"}
        rich = {
            "insight_id": iid,
            "source_app": "investment",
            "question_id": "q-rich",
            "source_state": {
                "source_app": "investment",
                "source_page": "Portfolio Health",
                "entity_params": {"holdings_fingerprint": "BND:50.0:Bonds|VYM:50.0:Dividend ETF"},
                "page_params": {"page": "Portfolio Health"},
            },
        }
        self.assertLess(_insight_blob_restore_score(thin), _insight_blob_restore_score(rich))

        def _load_saved_items(*, app=None, item_type=None, limit=100):
            if app == "investment":
                return [{"item_key": iid, "payload": thin}]
            if app == "applied_intelligence":
                return [{"item_key": iid, "payload": rich}]
            return []

        with patch("suite_account.load_saved_items", side_effect=_load_saved_items):
            loaded = load_applied_math_insight(iid, source_app="investment")
        self.assertTrue(_source_state_has_restore_payload(loaded.get("source_state")))

    def test_enrich_insight_from_question_blob(self) -> None:
        holdings = pd.DataFrame(
            {
                "Ticker": ["BND", "VYM"],
                "Weight (%)": [50.0, 50.0],
                "Asset Type": ["Bonds", "Dividend ETF"],
            }
        )
        question_ss = build_source_state(
            "Portfolio Health",
            {"investment_active_tab": "Portfolio Health", "holdings_df": holdings},
        )
        insight = {"insight_id": "insight-thin", "question_id": "q-enrich", "source_app": "investment"}
        with patch(
            "suite_analytical_question.load_analytical_question_source_state",
            return_value=question_ss,
        ):
            enriched = _enrich_insight_from_question_blob(insight)
        self.assertTrue(_source_state_has_restore_payload(enriched.get("source_state")))
        ent = enriched["source_state"]["entity_params"]
        self.assertIn("holdings_df", ent)

    def test_diagnose_ami_return_source_state_resolution_question_blob(self) -> None:
        st = _FakeSt({"suite_ami_insight": "674475f5a3c1c57a", "suite_ai_question_id": "q-diag"})
        insight = {"insight_id": "674475f5a3c1c57a", "source_app": "investment"}
        question_ss = {
            "source_app": "investment",
            "source_page": "Portfolio Health",
            "entity_params": {
                "holdings_fingerprint": "BND:50.0:Bonds|VYM:50.0:Dividend ETF",
                "holdings_df": [{"Ticker": "BND"}],
            },
            "page_params": {"page": "Portfolio Health"},
        }
        with patch(
            "suite_analytical_question.load_analytical_question_source_state",
            return_value=question_ss,
        ):
            diag = diagnose_ami_return_source_state_resolution(
                st, "investment", insight, question_id_qp="q-diag"
            )
        self.assertTrue(diag["question_blob_loaded"])
        self.assertTrue(diag["question_blob_has_source_state"])
        self.assertEqual(diag["resolved_source_state_source"], "question_blob")

    def test_store_applied_math_insight_embeds_resolved_source_state(self) -> None:
        holdings = pd.DataFrame(
            {
                "Ticker": ["BND", "VYM"],
                "Weight (%)": [50.0, 50.0],
                "Asset Type": ["Bonds", "Dividend ETF"],
            }
        )
        question_ss = build_source_state(
            "Portfolio Health",
            {"investment_active_tab": "Portfolio Health", "holdings_df": holdings},
        )
        st = _FakeSt()
        insight = {
            "insight_id": "insight-embed",
            "question_id": "q-embed-1",
            "source_app": "investment",
            "source_page": "Portfolio Health",
            "conclusion": "Holdings look balanced.",
        }
        captured: list[dict] = []

        def _remember_saved_item(app, item_type, item_key, *, title="", payload=None, **_kwargs):
            captured.append({"app": app, "item_type": item_type, "payload": dict(payload or {})})
            return True

        with patch(
            "suite_analytical_question.load_analytical_question_source_state",
            return_value=question_ss,
        ), patch(
            "suite_account.remember_saved_item",
            side_effect=_remember_saved_item,
        ), patch(
            "suite_activity_client.record_activity",
            return_value=None,
        ):
            store_applied_math_insight(insight, st=st)

        self.assertTrue(captured)
        blob = captured[0]["payload"]
        self.assertTrue(_source_state_has_restore_payload(blob.get("source_state")))
        self.assertEqual(blob.get("question_id"), "q-embed-1")
        ent = (blob.get("source_state") or {}).get("entity_params") or {}
        self.assertIn("holdings_df", ent)


if __name__ == "__main__":
    unittest.main()
