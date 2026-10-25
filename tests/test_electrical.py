"""Electrical contract tests; these do not claim that MATLAB simulation ran."""
from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from dcac_agent.config import ROOT
from dcac_agent.design import DesignSpec
from dcac_agent.runtime import MatlabRuntime


TEST_ROOT = (ROOT / "work" / "tests-electrical").resolve()
TEST_ROOT.mkdir(parents=True, exist_ok=True)


class ElectricalDesignTests(unittest.TestCase):
    def test_baseline_parameter_audit(self):
        spec = DesignSpec().validate()
        values = spec.derived()
        self.assertAlmostEqual(values["load_resistance"], 96.8)
        self.assertAlmostEqual(values["output_current"], 500 / 220)
        self.assertAlmostEqual(values["resonant_frequency"], 1641.7, places=0)
        self.assertAlmostEqual(values["switching_to_resonance_ratio"], 12.18, places=1)
        self.assertAlmostEqual(values["capacitor_current_estimate"],
                               2 * math.pi * 50 * 4.7e-6 * 220)
        self.assertGreater(values["inductor_current_estimate"], values["output_current"])
        self.assertIn("not total inverter loss", values["loss_estimate_scope"])

    def test_engineering_review_distinguishes_estimates(self):
        review = DesignSpec().engineering_review()
        self.assertTrue(all(review["checks"].values()))
        self.assertTrue(any("not simulation" in note for note in review["notes"]))
        self.assertTrue(any("provenance" in note for note in review["notes"]))

    def test_load_step_keeps_pre_and_post_analysis_windows(self):
        with self.assertRaises(ValueError):
            DesignSpec(load_step=True, load_step_time=0.06).validate()
        DesignSpec(load_step=True, load_step_time=0.12, stop_time=0.24).validate()


class ElectricalRuntimeContractTests(unittest.TestCase):
    def test_export_is_additive_and_self_contained(self):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT, prefix="contract-") as name:
            outdir = Path(name) / "abc123abc123" / "run123run123"
            MatlabRuntime.prepare(DesignSpec().to_dict(), "simulate", outdir)
            request = json.loads((outdir / "request.json").read_text(encoding="utf-8"))
            self.assertEqual(request["schema_version"], "dcac.request/1.1")
            self.assertEqual(request["action"], "simulate")
            self.assertEqual(request["electrical"]["model_fidelity"],
                             "baseline_ideal_switching_open_loop")
            self.assertEqual(request["electrical"]["steps_per_switching_period"], 100)
            self.assertFalse(request["electrical"]["closed_loop_dead_time_compensation"])
            self.assertEqual(request["run_context"]["session_id"], "abc123abc123")
            self.assertEqual(request["run_context"]["run_id"], "run123run123")
            self.assertIsNone(request["run_context"]["design_revision"])
            required = {
                "dcac_execute.m", "dcac_normalize_request.m", "dcac_build_baseline_model.m",
                "dcac_build_sps_model.m", "dcac_postprocess.m", "dcac_validate.m",
                "dcac_build_stages.m", "dcac_write_manifest.m", "run_in_matlab.m",
            }
            self.assertTrue(required.issubset({path.name for path in outdir.iterdir()}))
            manual = (outdir / "run_in_matlab.m").read_text(encoding="utf-8")
            self.assertIn("R2023b or newer", manual)

    def test_optional_context_and_electrical_settings_are_versioned(self):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT, prefix="context-") as name:
            outdir = Path(name) / "case"
            MatlabRuntime.prepare(
                DesignSpec().to_dict(), "build", outdir,
                electrical={"model_fidelity": "sps_device_lossy_open_loop",
                            "scenario_id": "half_load", "steps_per_switching_period": 200},
                context={"session_id": "session-test", "run_id": "run-test", "design_revision": 7},
            )
            request = json.loads((outdir / "request.json").read_text(encoding="utf-8"))
            self.assertEqual(request["electrical"]["scenario_id"], "half_load")
            self.assertEqual(request["electrical"]["steps_per_switching_period"], 200)
            self.assertEqual(request["run_context"]["design_revision"], 7)
            self.assertIn("component_revision_id", request["run_context"])

    def test_legacy_load_step_maps_to_versioned_scenario(self):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT, prefix="load-step-") as name:
            outdir = Path(name) / "case"
            spec = DesignSpec(load_step=True, load_final_ratio=0.7).to_dict()
            MatlabRuntime.prepare(spec, "simulate", outdir)
            request = json.loads((outdir / "request.json").read_text(encoding="utf-8"))
            self.assertEqual(request["electrical"]["scenario_id"], "load_step")
            self.assertEqual(request["spec"]["load_final_ratio"], 0.7)

    def test_matlab_sources_keep_legacy_and_full_resolution_contracts(self):
        post = (ROOT / "matlab" / "electrical" / "dcac_postprocess.m").read_text(encoding="utf-8")
        manifest = (ROOT / "matlab" / "electrical" / "dcac_write_manifest.m").read_text(encoding="utf-8")
        device = (ROOT / "matlab" / "electrical" / "dcac_build_sps_model.m").read_text(encoding="utf-8")
        self.assertIn("writematrix([t y(:,1:4)]", post)
        self.assertIn("y=yFull(:,1:4)", post)
        self.assertIn("electrical_full_v1.csv", post)
        self.assertIn("electrical_raw_v1.mat", post)
        self.assertIn("whole_inverter_efficiency_claimed=false", post)
        self.assertIn("schema_version='dcac.electrical.handoff/1.0'", manifest)
        self.assertIn("Web JSON waveforms are decimated", manifest)
        self.assertEqual(device.count("sps_lib/Power Electronics/Mosfet"), 1)
        self.assertIn("for k=1:4", device)
        self.assertIn("dead time", device.lower())
        self.assertIn("sps_lib/Utilities/Ground", device)
        self.assertIn("connect(source,'RConn',1,idc,'LConn',1)", device)
        self.assertIn("Desired_Double_", device)
        self.assertIn("Vout_PWM_Sample_Hold", device)
        self.assertNotIn("sps_lib/Power Grid Elements/Ground", device)
        self.assertIn("component_revision_id", manifest)
        self.assertIn("comparison_group_id", manifest)
        self.assertIn("dead_time_compensation_index", manifest)
        self.assertIn("feedforward_modulation_index", device)


if __name__ == "__main__":
    unittest.main()
