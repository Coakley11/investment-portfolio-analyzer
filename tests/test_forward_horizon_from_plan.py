"""Forward projection horizon seeds from persisted planning horizon once."""

from __future__ import annotations

import unittest

from components.macro_engine import (
    FORWARD_HORIZON_FALLBACK,
    FORWARD_HORIZON_MAX,
    FORWARD_HORIZON_PERSIST_KEY,
    clamp_forward_horizon_years,
    harvest_forward_horizon_widget_to_persist,
    macro_widget_key,
    seed_forward_horizon_from_plan_if_needed,
    simulate_macro_widget_teardown,
)


class TestForwardHorizonFromPlan(unittest.TestCase):
    def test_A_plan_horizon_10_first_load_defaults_to_10(self) -> None:
        ss: dict = {"plan_horizon": 10}
        self.assertEqual(seed_forward_horizon_from_plan_if_needed(ss), 10)
        self.assertEqual(ss[FORWARD_HORIZON_PERSIST_KEY], 10)

    def test_B_plan_horizon_15_defaults_to_15(self) -> None:
        ss: dict = {"plan_horizon": 15}
        self.assertEqual(seed_forward_horizon_from_plan_if_needed(ss), 15)

    def test_C_missing_plan_horizon_uses_fallback(self) -> None:
        ss: dict = {}
        self.assertEqual(seed_forward_horizon_from_plan_if_needed(ss), FORWARD_HORIZON_FALLBACK)
        self.assertEqual(ss[FORWARD_HORIZON_PERSIST_KEY], 5)

    def test_D_out_of_range_horizon_clamps(self) -> None:
        self.assertEqual(clamp_forward_horizon_years(40), FORWARD_HORIZON_MAX)
        self.assertEqual(clamp_forward_horizon_years(0), 1)
        self.assertEqual(clamp_forward_horizon_years(-3), 1)
        ss_high: dict = {"plan_horizon": 25}
        self.assertEqual(seed_forward_horizon_from_plan_if_needed(ss_high), FORWARD_HORIZON_MAX)
        ss_low: dict = {"plan_horizon": 0}
        self.assertEqual(seed_forward_horizon_from_plan_if_needed(ss_low), 1)

    def test_E_manual_forward_override_not_overwritten_by_plan(self) -> None:
        ss: dict = {"plan_horizon": 10}
        seed_forward_horizon_from_plan_if_needed(ss)
        ss[FORWARD_HORIZON_PERSIST_KEY] = 7
        self.assertEqual(seed_forward_horizon_from_plan_if_needed(ss), 7)
        ss["plan_horizon"] = 15
        self.assertEqual(seed_forward_horizon_from_plan_if_needed(ss), 7)

    def test_F_navigation_preserves_explicit_override(self) -> None:
        ss: dict = {"plan_horizon": 10}
        seed_forward_horizon_from_plan_if_needed(ss)
        wkey = macro_widget_key(FORWARD_HORIZON_PERSIST_KEY)
        ss[wkey] = 8
        harvest_forward_horizon_widget_to_persist(ss)
        simulate_macro_widget_teardown(ss)
        self.assertNotIn(wkey, ss)
        self.assertEqual(ss[FORWARD_HORIZON_PERSIST_KEY], 8)
        seed_forward_horizon_from_plan_if_needed(ss)
        self.assertEqual(ss[FORWARD_HORIZON_PERSIST_KEY], 8)

    def test_G_restored_plan_horizon_seeds_when_no_forward_override(self) -> None:
        restored = {"plan_horizon": 10}  # saved session without fwd_years
        self.assertNotIn(FORWARD_HORIZON_PERSIST_KEY, restored)
        self.assertEqual(seed_forward_horizon_from_plan_if_needed(restored), 10)

    def test_restored_forward_override_beats_plan_horizon(self) -> None:
        restored = {"plan_horizon": 10, FORWARD_HORIZON_PERSIST_KEY: 12}
        self.assertEqual(seed_forward_horizon_from_plan_if_needed(restored), 12)

    def test_streamlit_app_no_hardcoded_five_year_slider(self) -> None:
        from pathlib import Path

        src = Path(__file__).resolve().parents[1] / "streamlit_app.py"
        text = src.read_text(encoding="utf-8")
        self.assertIn("render_forward_projection_horizon_slider()", text)
        self.assertNotIn(
            'st.slider("Forward projection horizon (years)", 1, 15, 5)',
            text,
        )


if __name__ == "__main__":
    unittest.main()
