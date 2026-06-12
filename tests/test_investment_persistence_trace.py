"""Tests for Investment persistence trace panel (PR1 trace-only)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import pandas as pd


class TestInvestmentPersistenceTrace(unittest.TestCase):
    def _st(self, session: dict | None = None) -> MagicMock:
        st = MagicMock()
        st.session_state = dict(session or {})
        st.query_params = {}
        return st

    def test_init_developer_mode_from_query_enables_diagnostics(self) -> None:
        from investment_persistence_trace import init_developer_mode_from_query

        st = self._st()
        st.query_params = {"dev": "1"}
        init_developer_mode_from_query(st)
        self.assertTrue(st.session_state.get("investment_show_dev_diagnostics"))

    def test_pr1_baseline_trace_active_without_dev_query(self) -> None:
        from investment_persistence_trace import (
            INVESTMENT_PERSIST_DEPLOY_VERSION,
            investment_trace_enabled,
            pr1_baseline_trace_active,
        )

        self.assertTrue(pr1_baseline_trace_active(persistence_ok=True))
        self.assertFalse(pr1_baseline_trace_active(persistence_ok=False))
        st = self._st()
        self.assertTrue(investment_trace_enabled(st, persistence_ok=True))
        self.assertFalse(investment_trace_enabled(st, persistence_ok=False))
        self.assertEqual(INVESTMENT_PERSIST_DEPLOY_VERSION, "investment-durable-restore-v12")

    def test_render_pass_dedupes_trace_ui(self) -> None:
        from investment_persistence_trace import (
            bump_pr1_render_pass,
            render_persistence_trace_sidebar,
        )

        st = self._st()
        st.sidebar = MagicMock()
        st.sidebar.expander = MagicMock(return_value=MagicMock(__enter__=MagicMock(return_value=st), __exit__=MagicMock()))
        bump_pr1_render_pass(st)
        render_persistence_trace_sidebar(st, persistence_ok=True)
        self.assertEqual(st.session_state.get("_pr1_trace_ui_render_pass"), 1)
        self.assertTrue(st.session_state.get("_pr1_trace_sidebar_called"))
        self.assertTrue(st.session_state.get("_pr1_snapshot_full_trace_ran"))
        render_persistence_trace_sidebar(st, persistence_ok=True)
        self.assertEqual(st.session_state.get("_pr1_trace_ui_render_pass"), 1)

    def test_pr1_checkbox_enables_trace_when_baseline_inactive(self) -> None:
        from investment_persistence_trace import (
            PR1_DIAG_CHECKBOX_KEY,
            investment_trace_enabled,
            pr1_baseline_trace_active,
        )

        st = self._st({PR1_DIAG_CHECKBOX_KEY: True})
        # Simulate a future deploy marker by disabling baseline via persistence_ok=False.
        self.assertFalse(pr1_baseline_trace_active(persistence_ok=False))
        self.assertTrue(investment_trace_enabled(st, persistence_ok=False))

    def test_snapshot_tab_trace_uses_label_strings(self) -> None:
        from investment_persistence_trace import snapshot_tab_trace

        st = self._st(
            {
                "investment_active_tab": "Portfolio Health",
                "health_active_tab": "Portfolio Health",
                "_suite_persist_last_restore_source": "cloud",
            }
        )
        rows = snapshot_tab_trace(st)
        self.assertEqual(rows["final_investment_tab"], "Portfolio Health")
        self.assertEqual(rows["tab_widget_value"], "Portfolio Health")
        self.assertEqual(rows["tab_restore_source"], "cloud")

    def test_test_a_compare_trace_includes_tab_fields(self) -> None:
        from investment_persistence_trace import (
            TEST_A_TRACE_LABELS,
            collect_test_a_trace_rows,
            format_test_a_compare_trace,
            snapshot_workspace_restore_trace,
        )

        st = self._st(
            {
                "investment_active_tab": "Monte Carlo",
                "health_active_tab": "Monte Carlo",
                "_suite_cloud_fetch_updated_at": "2026-06-09T12:00:00+00:00",
            }
        )
        snapshot_workspace_restore_trace(st)
        trace = {
            "cloud_fetch_tab": "Overview",
            "restored_tab": "Overview",
            "final_investment_tab": "Monte Carlo",
            "restore_decision": "applied",
            "active_tab_source": "widget",
            "tab_restore_source": "cloud",
        }
        rows = collect_test_a_trace_rows(st, trace)
        text = format_test_a_compare_trace(rows)
        for label in TEST_A_TRACE_LABELS:
            self.assertIn(f"{label}:", text)
        self.assertIn("final_investment_tab: Monte Carlo", text)

    def test_test_b_compare_trace_includes_global_settings(self) -> None:
        from investment_persistence_trace import (
            TEST_B_TRACE_LABELS,
            collect_test_b_trace_rows,
            format_test_b_compare_trace,
            snapshot_global_settings_trace,
        )

        st = self._st(
            {
                "experience": "Advanced Mode",
                "_suite_persisted_experience": "Advanced Mode",
                "sidebar_portfolio_value": 250_000,
                "analysis_start_date": "2021-01-01",
                "analysis_end_date": "2026-06-01",
                "risk_free_pct": 3.5,
                "portfolio_preset": "Balanced",
            }
        )
        snapshot_global_settings_trace(st)
        trace = st.session_state["_investment_persist_trace"]
        rows = collect_test_b_trace_rows(st, trace)
        text = format_test_b_compare_trace(rows)
        for label in TEST_B_TRACE_LABELS:
            self.assertIn(f"{label}:", text)
        self.assertIn("portfolio_preset: Balanced", text)

    def test_test_c_compare_trace_includes_filters(self) -> None:
        from investment_persistence_trace import (
            TEST_C_TRACE_LABELS,
            collect_test_c_trace_rows,
            format_test_c_compare_trace,
            snapshot_filter_trace,
        )

        st = self._st(
            {
                "investment_active_tab": "Portfolio Health",
                "overview_subtab": "Risk",
                "mc_assumption_mode": "Historical returns",
                "health_run_optimizer": True,
                "health_bond_min": 10,
                "frontier_points": 1500,
                "macro_scenario_id": "stress",
                "macro_scenario_mode": "stress",
                "health_rate_env": "Rising Rates",
                "health_inflation": "High Inflation",
                "health_recession": 40,
                "health_valuation": "Overvalued",
                "health_regime": "Late Cycle",
            }
        )
        snapshot_filter_trace(st)
        trace = st.session_state["_investment_persist_trace"]
        rows = collect_test_c_trace_rows(st, trace)
        text = format_test_c_compare_trace(rows)
        for label in TEST_C_TRACE_LABELS:
            self.assertIn(f"{label}:", text)

    def test_test_d_compare_trace_includes_portfolio_fields(self) -> None:
        from investment_persistence_trace import (
            TEST_D_TRACE_LABELS,
            collect_test_d_trace_rows,
            format_test_d_compare_trace,
            snapshot_portfolio_trace,
        )

        st = self._st(
            {
                "holdings_df": pd.DataFrame({"Ticker": ["SPY", "BND"], "Weight": [0.6, 0.4]}),
                "preset_applied": "Balanced",
                "portfolio_preset": "Balanced",
                "health_objective": "balanced growth",
                "health_summary": {"score": 72},
                "health_result": {"score": 72},
                "workflow_state": {"portfolio_built": True},
            }
        )
        snapshot_portfolio_trace(st)
        trace = st.session_state["_investment_persist_trace"]
        rows = collect_test_d_trace_rows(st, trace)
        text = format_test_d_compare_trace(rows)
        for label in TEST_D_TRACE_LABELS:
            self.assertIn(f"{label}:", text)
        self.assertIn("health_summary_exists: True", text)
        self.assertEqual(rows["holdings_row_count"], 2)

    def test_record_ami_apply_trace_sets_test_e_fields(self) -> None:
        from investment_persistence_trace import collect_test_e_trace_rows, record_ami_apply_trace

        st = self._st({"investment_active_tab": "Overview"})
        source_state = {
            "source_app": "investment",
            "source_page": "Portfolio Health",
            "widget_params": {"health_rate_env": "Stable Rates"},
        }
        record_ami_apply_trace(st, source_state=source_state, success=True)
        trace = st.session_state["_investment_persist_trace"]
        rows = collect_test_e_trace_rows(st, trace)
        self.assertTrue(rows["ami_return_detected"])
        self.assertTrue(rows["apply_source_state_attempted"])
        self.assertTrue(rows["apply_source_state_success"])
        self.assertEqual(rows["source_app_normalized"], "investment")
        self.assertIn("source_app", rows["return_context_keys"])

    def test_record_ami_launch_trace_sets_launch_fields(self) -> None:
        from investment_persistence_trace import collect_test_e_trace_rows, record_ami_launch_trace

        st = self._st({"investment_active_tab": "⑤ Portfolio Health"})
        source_state = {
            "source_app": "investment",
            "source_page": "⑤ Portfolio Health",
            "entity_params": {"holdings_fingerprint": "BND:50.0:Bonds|VYM:50.0:Dividend ETF"},
        }
        record_ami_launch_trace(
            st,
            source_state=source_state,
            action_url="https://example.com/?suite_resume=1",
        )
        trace = st.session_state["_investment_persist_trace"]
        rows = collect_test_e_trace_rows(st, trace)
        self.assertTrue(rows["ami_launch_detected"])
        self.assertTrue(rows["source_state_created"])
        self.assertTrue(rows["return_url_generated"])
        self.assertEqual(
            rows["source_state_holdings_fingerprint"],
            "BND:50.0:Bonds|VYM:50.0:Dividend ETF",
        )

    def test_ami_trace_survives_snapshot_with_none_fields(self) -> None:
        from investment_persistence_trace import (
            AMI_TRACE_BACKUP_KEY,
            record_investment_ami_launch,
            snapshot_ami_return_trace,
        )

        st = self._st({"investment_active_tab": "Portfolio Health"})
        source_state = {
            "source_app": "investment",
            "entity_params": {"holdings_fingerprint": "BND:50.0:Bonds|VYM:50.0:Dividend ETF"},
        }
        record_investment_ami_launch(
            st,
            entrypoint="test",
            button_clicked=True,
            build_source_state_called=True,
            source_state=source_state,
            action_url="https://ami.example/resume",
        )
        snapshot_ami_return_trace(st)
        backup = st.session_state.get(AMI_TRACE_BACKUP_KEY)
        self.assertTrue(backup.get("ami_launch_detected"))
        trace = st.session_state["_investment_persist_trace"]
        self.assertTrue(trace.get("ami_launch_detected"))

    def test_record_save_trace_captures_autosave_event(self) -> None:
        from investment_persistence_trace import record_save_trace

        st = self._st(
            {
                "experience": "Beginner Mode",
                "_suite_persisted_experience": "Beginner Mode",
                "investment_active_tab": "My Goal",
                "sidebar_portfolio_value": 100_000,
                "holdings_df": pd.DataFrame({"Ticker": ["SPY"], "Weight": [1.0]}),
            }
        )
        event = {
            "trigger": "end_of_run",
            "saved_cloud": True,
            "blob_experience": "Beginner Mode",
            "cloud_readback_ts": "2026-06-09T13:00:00+00:00",
        }
        state = {
            "investment_active_tab": "My Goal",
            "sidebar_portfolio_value": 100_000,
            "holdings_fingerprint": "abc123",
        }
        record_save_trace(st, event=event, state=state)
        trace = st.session_state["_investment_persist_trace"]
        self.assertTrue(trace.get("autosave_ran"))
        self.assertEqual(trace.get("save_reason"), "end_of_run")
        self.assertTrue(trace.get("cloud_write_ok"))
        self.assertEqual(trace.get("saved_tab"), "My Goal")


if __name__ == "__main__":
    unittest.main()
