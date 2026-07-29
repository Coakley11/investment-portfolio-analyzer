"""Tests for benchmark run history archival."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from investment_ami.evaluation.benchmark_eval import run_benchmark_evaluation
from investment_ami.evaluation.run_history import load_run_index, record_benchmark_run


class TestBenchmarkRunHistory(unittest.TestCase):
    def test_record_run_writes_index_and_artifacts(self) -> None:
        import os
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            eval_dir = Path(tmp)
            with mock.patch.dict(
                os.environ,
                {"INVESTMENT_AMI_ANALYTICAL_SYNTHESIS": "1", "INVESTMENT_AMI_SYNTHESIS_MOCK": "1"},
                clear=False,
            ):
                report = run_benchmark_evaluation(synthesis_mode="mock")
            meta = record_benchmark_run(
                report,
                eval_dir=eval_dir,
                hypothesis="Test hypothesis",
                lever_changed="baseline",
            )
            self.assertTrue((eval_dir / "runs").is_dir())
            self.assertTrue((eval_dir / meta["artifact_json"]).is_file())
            index = load_run_index(eval_dir)
            self.assertEqual(len(index), 1)
            self.assertEqual(index[0]["hypothesis"], "Test hypothesis")


if __name__ == "__main__":
    unittest.main()
