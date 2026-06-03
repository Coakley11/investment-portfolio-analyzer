"""Tests for cloud vs disk restore conflict resolution."""

from __future__ import annotations

import unittest

from suite_cloud_state import parse_persist_timestamp, pick_restore_session


class TestRestorePick(unittest.TestCase):
    def test_parse_supabase_space_separated_naive_as_utc(self) -> None:
        disk = parse_persist_timestamp("2026-06-03 10:00:00")
        cloud = parse_persist_timestamp("2026-06-03T11:00:00+00:00")
        self.assertLess(disk, cloud)

    def test_cloud_newer_wins_when_not_dirty(self) -> None:
        picked = pick_restore_session(
            {"experience": "Beginner Mode"},
            "2026-06-03T12:00:00+00:00",
            {"experience": "Advanced Mode"},
            "2026-06-03T11:00:00+00:00",
            local_dirty=False,
        )
        self.assertEqual(picked.source, "cloud")
        self.assertEqual(picked.state["experience"], "Beginner Mode")
        self.assertEqual(picked.reason, "cloud newer")

    def test_disk_newer_wins_when_not_dirty(self) -> None:
        picked = pick_restore_session(
            {"experience": "Beginner Mode"},
            "2026-06-03T10:00:00+00:00",
            {"experience": "Advanced Mode"},
            "2026-06-03T12:00:00+00:00",
            local_dirty=False,
        )
        self.assertEqual(picked.source, "disk")
        self.assertEqual(picked.state["experience"], "Advanced Mode")

    def test_tie_prefers_cloud(self) -> None:
        ts = "2026-06-03T12:00:00+00:00"
        picked = pick_restore_session(
            {"experience": "Beginner Mode"},
            ts,
            {"experience": "Advanced Mode"},
            ts,
            local_dirty=False,
        )
        self.assertEqual(picked.source, "cloud")
        self.assertEqual(picked.reason, "tie → cloud")

    def test_local_dirty_prefers_disk(self) -> None:
        picked = pick_restore_session(
            {"experience": "Beginner Mode"},
            "2026-06-03T13:00:00+00:00",
            {"experience": "Advanced Mode"},
            "2026-06-03T10:00:00+00:00",
            local_dirty=True,
        )
        self.assertEqual(picked.source, "disk")
        self.assertEqual(picked.reason, "local unsaved edits")


if __name__ == "__main__":
    unittest.main()
