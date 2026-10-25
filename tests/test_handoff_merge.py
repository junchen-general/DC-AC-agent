"""Regression coverage for A/B manifest coexistence, without invoking solvers."""
import json
import unittest
from pathlib import Path

from test_core import temporary_workspace, cleanup_workspace
from dcac_agent.contracts import write_manifest


class HandoffMergeTests(unittest.TestCase):
    def test_preserve_repeat_and_reject_wrong_evidence(self):
        temp = temporary_workspace()
        try:
            folder = Path(temp.name)
            run = dict(id="run1", revision=2, spec={"power": 500},
                       status="completed", action="simulate")
            data = dict(schema_version="dcac.electrical.handoff/1.0",
                        identity=dict(session_id="session1", run_id="run1", design_revision=2),
                        spec=run["spec"], status="success", data_origin="real_simulation",
                        custom_provenance={"retain": True})
            original = json.dumps(data).encode("utf-8")
            (folder / "run_manifest.json").write_bytes(original)
            for _ in range(2):
                manifest = write_manifest(folder, "session1", run, "MATLAB/Simulink")
                self.assertEqual(manifest["handoff"]["status"], "available")
                self.assertEqual((folder / "electrical_handoff.json").read_bytes(), original)
                self.assertEqual(manifest["schema_version"], "1.0")
            for source, action, revision in [("TEST_DOUBLE_ONLY", "simulate", 2),
                                              ("MATLAB/Simulink", "build", 2),
                                              ("MATLAB/Simulink", "simulate", 3)]:
                manifest = write_manifest(folder, "session1", dict(run, action=action, revision=revision), source)
                self.assertEqual(manifest["handoff"]["status"], "not_ready")
        finally:
            cleanup_workspace(temp)
