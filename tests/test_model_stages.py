import json
import unittest
from pathlib import Path
from unittest.mock import patch

from test_core import temporary_workspace, cleanup_workspace, config, completed, FakeRuntime
from dcac_agent.agent import AgentService, PARAMS
from dcac_agent.store import Store
from dcac_agent.design import DesignSpec, MODEL_STAGES, BASELINE, stage_options


class ModelStageTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_workspace()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "state")
        self.sid = self.store.create()["id"]
        self.agent = AgentService(config(), self.store, FakeRuntime())
        self.patch = patch("dcac_agent.agent.OUTPUTS", self.root / "outputs")
        self.patch.start()

    def tearDown(self):
        self.agent.pool.shutdown(wait=True)
        self.patch.stop()
        cleanup_workspace(self.temp)

    def test_all_stage_exports_and_reload(self):
        for stage in MODEL_STAGES:
            job = completed(self.agent, self.agent.submit(self.sid, "选择阶段并导出", "export", {"model_fidelity": stage}))
            self.assertEqual(job["status"], "completed", job.get("error"))
            run = self.store.snapshot(self.sid)["runs"][-1]
            folder = self.root / "outputs" / self.sid / run["id"]
            request = json.loads((folder / "request.json").read_text())
            manifest = json.loads((folder / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(request["electrical"]["model_fidelity"], stage)
            self.assertEqual(request["electrical"]["steps_per_switching_period"], 100 if stage == BASELINE else 400)
            self.assertEqual(request["electrical"]["closed_loop_dead_time_compensation"], stage == "sps_device_closed_loop")
            self.assertEqual(manifest["fidelity"], stage)
            self.assertEqual(run["status"], "exported")
            self.assertFalse((folder / "dcac_inverter.slx").exists())
        restored = Store(self.root / "state").snapshot(self.sid)
        self.assertEqual([r["spec"]["model_fidelity"] for r in restored["runs"]], list(MODEL_STAGES))
        self.assertEqual(restored["spec"]["output_power"], 500)

    def test_old_session_and_invalid_stage(self):
        self.store.get(self.sid)["spec"].pop("model_fidelity")
        self.store.save()
        self.assertEqual(DesignSpec(**self.store.snapshot(self.sid)["spec"]).model_fidelity, BASELINE)
        self.assertEqual(stage_options(self.store.snapshot(self.sid)["spec"])["model_fidelity"], BASELINE)
        with self.assertRaises(ValueError):
            self.store.update_spec(self.sid, {"model_fidelity": "unknown"})
        self.assertEqual(self.store.snapshot(self.sid)["revision"], 0)
        self.assertEqual(PARAMS["model_fidelity"]["enum"], list(MODEL_STAGES))

    def test_device_resolution_and_closed_loop_margin(self):
        with self.assertRaises(ValueError):
            DesignSpec(model_fidelity="sps_device_open_loop", switching_frequency=5000).validate()
        with self.assertRaises(ValueError):
            DesignSpec(model_fidelity="sps_device_closed_loop", input_voltage=330).validate()

    def test_rule_closed_loop_build_without_simulation(self):
        job = completed(self.agent, self.agent.submit(self.sid, "切换为电压闭环模型，保持当前参数，先生成模型，不运行仿真。"))
        self.assertEqual(job["status"], "completed", job.get("error"))
        run = self.store.snapshot(self.sid)["runs"][-1]
        self.assertEqual(run["action"], "build")
        self.assertEqual(run["spec"]["model_fidelity"], "sps_device_closed_loop")
        self.assertIn("电压闭环模型", job["answer"])
