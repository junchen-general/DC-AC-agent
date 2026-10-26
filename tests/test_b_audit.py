"""Audit reporting regression tests; these synthetic rows are not physics evidence."""
import unittest
from tools.summarize_b_audit import summarize


def row(steps, **metrics):
    return dict(stage="test", scenario="rated", steps=steps, ok=True,
                metrics=dict(output_rms=220., thd_percent=1., inductor_rms=2.,
                             inductor_peak=4., **metrics))


class AuditSummaryTests(unittest.TestCase):
    def test_adjacent_pairs_preserve_failure_history(self):
        a, b, c = row(400), row(800), row(1600)
        a["metrics"]["inductor_peak"] = 4.2
        report = summarize([c, a, b])
        self.assertEqual([p["converged"] for p in report["comparisons"]], [False, True])
        self.assertEqual(report["comparisons"][0]["failed_criteria"],
                         ["inductor_peak_relative_percent"])

    def test_missing_failed_or_nonfinite_runs_cannot_pass(self):
        a, b = row(400), row(800)
        self.assertEqual(summarize([a])["comparisons"][0]["status"], "incomplete")
        b["ok"] = False
        self.assertFalse(summarize([a, b])["comparisons"][0]["converged"])
        b["ok"] = True
        b["metrics"]["thd_percent"] = float("nan")
        self.assertEqual(summarize([a, b])["comparisons"][0]["status"], "incomplete")

    def test_duplicate_resolution_rejected(self):
        with self.assertRaises(ValueError):
            summarize([row(400), row(400)])
