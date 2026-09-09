"""Monte Carlo projection years seeds from persisted planning horizon once."""

from __future__ import annotations

import unittest
from pathlib import Path

from components.macro_engine import (
    FORWARD_HORIZON_PERSIST_KEY,
    MC_HORIZON_FALLBACK,
    MC_HORIZON_MAX,
    MC_HORIZON_PERSIST_KEY,
    clamp_mc_horizon_years,
    harvest_mc_horizon_widget_to_persist,
    macro_widget_key,
    seed_forward_horizon_from_plan_if_needed,
    seed_mc_horizon_from_plan_if_needed,
    simulate_macro_widget_teardown,
)

ROOT = Path(__file__).resolve().parents[1]


class TestMonteCarloHorizonFromPlan(unittest.TestCase):
    def test_A_plan_horizon_10_first_mc_load_is_10(self) -> None:
        ss: dict = {"plan_horizon": 10}
        self.assertEqual(seed_mc_horizon_from_plan_if_needed(ss), 10)
        self.assertEqual(ss[MC_HORIZON_PERSIST_KEY], 10)

    def test_B_plan_horizon_15_first_mc_load_is_15(self) -> None:
        ss: dict = {"plan_horizon": 15}
        self.assertEqual(seed_mc_horizon_from_plan_if_needed(ss), 15)

    def test_C_missing_or_invalid_plan_horizon_uses_fallback(self) -> None:
        self.assertEqual(seed_mc_horizon_from_plan_if_needed({}), MC_HORIZON_FALLBACK)
        ss_bad: dict = {"plan_horizon": "nope"}
        self.assertEqual(seed_mc_horizon_from_plan_if_needed(ss_bad), MC_HORIZON_FALLBACK)

    def test_D_out_of_range_horizon_clamps(self) -> None:
        self.assertEqual(clamp_mc_horizon_years(40), MC_HORIZON_MAX)
        self.assertEqual(clamp_mc_horizon_years(0), 1)
        ss_high: dict = {"plan_horizon": 25}
        self.assertEqual(seed_mc_horizon_from_plan_if_needed(ss_high), MC_HORIZON_MAX)

    def test_E_manual_mc_change_persists(self) -> None:
        ss: dict = {"plan_horizon": 10}
        seed_mc_horizon_from_plan_if_needed(ss)
        ss[MC_HORIZON_PERSIST_KEY] = 6
        self.assertEqual(seed_mc_horizon_from_plan_if_needed(ss), 6)
        ss["plan_horizon"] = 15
        self.assertEqual(seed_mc_horizon_from_plan_if_needed(ss), 6)

    def test_F_navigation_preserves_mc_override(self) -> None:
        ss: dict = {"plan_horizon": 10}
        seed_mc_horizon_from_plan_if_needed(ss)
        wkey = macro_widget_key(MC_HORIZON_PERSIST_KEY)
        ss[wkey] = 6
        harvest_mc_horizon_widget_to_persist(ss)
        simulate_macro_widget_teardown(ss)
        self.assertNotIn(wkey, ss)
        self.assertEqual(ss[MC_HORIZON_PERSIST_KEY], 6)
        seed_mc_horizon_from_plan_if_needed(ss)
        self.assertEqual(ss[MC_HORIZON_PERSIST_KEY], 6)

    def test_G_forward_override_does_not_change_mc(self) -> None:
        ss: dict = {"plan_horizon": 10}
        seed_forward_horizon_from_plan_if_needed(ss)
        seed_mc_horizon_from_plan_if_needed(ss)
        ss[FORWARD_HORIZON_PERSIST_KEY] = 9
        self.assertEqual(seed_mc_horizon_from_plan_if_needed(ss), 10)
        self.assertEqual(ss[MC_HORIZON_PERSIST_KEY], 10)

    def test_H_mc_override_does_not_change_forward(self) -> None:
        ss: dict = {"plan_horizon": 10}
        seed_forward_horizon_from_plan_if_needed(ss)
        seed_mc_horizon_from_plan_if_needed(ss)
        ss[MC_HORIZON_PERSIST_KEY] = 6
        self.assertEqual(seed_forward_horizon_from_plan_if_needed(ss), 10)
        self.assertEqual(ss[FORWARD_HORIZON_PERSIST_KEY], 10)

    def test_I_saved_mc_override_wins_over_planning_default(self) -> None:
        restored = {"plan_horizon": 10, MC_HORIZON_PERSIST_KEY: 6}
        self.assertEqual(seed_mc_horizon_from_plan_if_needed(restored), 6)

    def test_J_saved_plan_horizon_seeds_mc_when_mc_override_absent(self) -> None:
        restored = {"plan_horizon": 10}
        self.assertNotIn(MC_HORIZON_PERSIST_KEY, restored)
        self.assertEqual(seed_mc_horizon_from_plan_if_needed(restored), 10)

    def test_K_no_hardcoded_five_year_mc_first_load_path(self) -> None:
        text = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
        self.assertIn("render_monte_carlo_projection_years_slider()", text)
        self.assertNotIn('st.slider("Projection years", 1, 15, 5)', text)


if __name__ == "__main__":
    unittest.main()
