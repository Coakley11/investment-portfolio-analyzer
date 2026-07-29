"""Benchmark evaluation harness tests."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from investment_ami.evaluation.benchmark_eval import run_benchmark_evaluation


class TestBenchmarkEvaluationHarness(unittest.TestCase):
    def test_mock_eval_routing_and_report(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "INVESTMENT_AMI_ANALYTICAL_SYNTHESIS": "1",
                "INVESTMENT_AMI_SYNTHESIS_MOCK": "1",
            },
            clear=False,
        ):
            report = run_benchmark_evaluation(synthesis_mode="mock")
        self.assertEqual(len(report.runs), 6)
        self.assertTrue(all(r.routing_ok for r in report.runs))
        self.assertTrue(all(r.pipeline_step == "analytical_synthesis" for r in report.runs))


if __name__ == "__main__":
    unittest.main()
