"""Tests use temporary folders and explicit doubles, never seed website demo results."""
import json
import math
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from dcac_agent.agent import AgentService
from dcac_agent.config import ROOT, public_config
from dcac_agent.design import DesignSpec, extract_parameters
from dcac_agent.runtime import MatlabRuntime
from dcac_agent.store import Store
from dcac_agent.web_app import Application, make_handler

TEST_ROOT = (ROOT / "work" / "tests").resolve()
TEST_ROOT.mkdir(parents=True, exist_ok=True)


def temporary_workspace():
    return tempfile.TemporaryDirectory(dir=TEST_ROOT, prefix="unit-")


def cleanup_workspace(temp):
    # All recursive temporary cleanup is constrained to this project's test area.
    if not Path(temp.name).resolve().is_relative_to(TEST_ROOT):
        raise AssertionError("refuse cleanup outside the test workspace")
    temp.cleanup()


def config():
    return {"host": "127.0.0.1", "port": 0, "matlab_executable": "", "matlab_timeout_seconds": 2,
            "llm": {"enabled": False, "base_url": "https://example.invalid/v1", "model": "", "api_key": "", "max_iterations": 4}}


class FakeRuntime:
    """Test double: deliberately no realistic numeric waveforms or FEA."""
    def status(self):
        return {"installed": False, "note": "test double"}

    def execute(self, spec, action, outdir, cancel, emit):
        if cancel.is_set():
            raise InterruptedError("cancelled")
        result = {"ok": True, "action": action, "source": "TEST_DOUBLE_ONLY", "spec": spec}
        if action == "simulate":
            result["metrics"] = {"output_rms": 1, "voltage_error_percent": 1, "output_power": 1,
                                 "thd_percent": 1, "inductor_rms": 1, "inductor_peak": 1, "winding_loss": 1}
            result["checks"] = {"voltage": True, "thd": True}
        (outdir / "result.json").write_text(json.dumps(result), encoding="utf-8")
        return result


def completed(agent, job):
    for _ in range(500):
        snapshot = agent.snapshot(job["id"])
        if snapshot["status"] not in {"queued", "running", "cancelling"}:
            return snapshot
        time.sleep(.01)
    raise AssertionError("test job timeout")


class DesignTests(unittest.TestCase):
    def test_rated_calculation(self):
        d = DesignSpec().validate().derived()
        self.assertAlmostEqual(d["load_resistance"], 96.8)
        self.assertAlmostEqual(d["modulation_index"], math.sqrt(2)*220/380)

    def test_chinese_parameters_and_si_units(self):
        self.assertEqual(extract_parameters("输入380 V、输出220 V、500 W、50 Hz"),
                         {"input_voltage": 380, "output_voltage": 220, "output_power": 500, "output_frequency": 50})
        updates = extract_parameters("开关频率改为25000 Hz，电感3 mH，电容6.8 uF")
        self.assertNotIn("output_frequency", updates)
        self.assertEqual(updates["switching_frequency"], 25000)
        self.assertAlmostEqual(updates["inductance"], .003)
        self.assertAlmostEqual(updates["capacitance"], 6.8e-6)
        self.assertEqual(extract_parameters("1 kW")['output_power'], 1000)

    def test_reject_unphysical_or_injected_values(self):
        for updates in ({"input_voltage": 100}, {"capacitance": -1}, {"output_power": float("nan")},
                        {"inductance": "system('bad')"}, {"unknown": 1}, {"load_step": 1}):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                DesignSpec().updated(updates)

    def test_analysis_window_after_load_step(self):
        DesignSpec(load_step=True).validate()
        with self.assertRaises(ValueError):
            DesignSpec(load_step=True, stop_time=.18).validate()

    def test_key_never_returned(self):
        c = config(); c["llm"]["api_key"] = "test-secret"
        self.assertNotIn("test-secret", json.dumps(public_config(c)))
        self.assertEqual(c["llm"]["api_key"], "test-secret")


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = temporary_workspace()
        self.root = Path(self.tmp.name)
        self.output_patch = patch("dcac_agent.agent.OUTPUTS", self.root / "outputs")
        self.output_patch.start()
        self.store = Store(self.root / "state")
        self.sid = self.store.create()["id"]
        self.agent = AgentService(config(), self.store, FakeRuntime())

    def tearDown(self):
        self.agent.pool.shutdown(wait=True)
        self.output_patch.stop()
        cleanup_workspace(self.tmp)

    def test_rule_parameter_update_without_matlab(self):
        job = completed(self.agent, self.agent.submit(self.sid, "将开关频率改为25 kHz，先查看参数"))
        self.assertEqual(job["status"], "completed")
        self.assertEqual(self.store.get(self.sid)["spec"]["switching_frequency"], 25000)
        self.assertEqual(self.store.get(self.sid)["runs"], [])

    def test_invalid_design_is_atomic(self):
        before = self.store.snapshot(self.sid)
        job = completed(self.agent, self.agent.submit(self.sid, "输入改为100 V"))
        self.assertEqual(job["status"], "failed")
        self.assertEqual(before["spec"], self.store.get(self.sid)["spec"])
        self.assertEqual(before["revision"], self.store.get(self.sid)["revision"])

    def test_export_is_not_reported_as_simulation(self):
        job = completed(self.agent, self.agent.submit(self.sid, "导出建模脚本", "export"))
        self.assertEqual(job["status"], "completed")
        self.assertIsNone(job["result"])
        run = self.store.get(self.sid)["runs"][-1]
        self.assertEqual(run["status"], "exported")
        self.assertIsNone(run["metrics"])
        files = {f["name"] for f in run["files"]}
        self.assertTrue({"dcac_execute.m", "run_in_matlab.m", "request.json"}.issubset(files))
        self.assertNotIn("dcac_inverter.slx", files)

    def test_simulation_records_revision_and_comparison(self):
        first = completed(self.agent, self.agent.submit(self.sid, "运行仿真"))
        self.assertEqual(first["status"], "completed")
        self.store.update_spec(self.sid, {"switching_frequency": 25000})
        second = completed(self.agent, self.agent.submit(self.sid, "运行仿真"))
        self.assertEqual(second["result"]["revision"], 1)
        runs = self.store.get(self.sid)["runs"]
        self.assertNotEqual(runs[0]["spec"], runs[1]["spec"])
        compare = completed(self.agent, self.agent.submit(self.sid, "比较最近两次结果"))
        self.assertIn("变化", compare["answer"])

    def test_missing_matlab_failure_has_recovery_files(self):
        missing = config(); missing["matlab_executable"] = str(self.root / "not-installed" / "matlab.exe")
        self.agent.runtime = MatlabRuntime(missing)
        job = completed(self.agent, self.agent.submit(self.sid, "运行仿真"))
        self.assertEqual(job["status"], "failed")
        self.assertIsNone(job["result"])
        run = self.store.get(self.sid)["runs"][-1]
        self.assertEqual(run["status"], "failed")
        self.assertIn("run_in_matlab.m", [f["name"] for f in run["files"]])

    def test_unknown_tools_cannot_execute_commands(self):
        with self.assertRaises(ValueError):
            self.agent._tool({"cancel": threading.Event()}, "eval", {"code": "bad"})

    def test_cancel_running_job(self):
        started = threading.Event()
        class BlockingRuntime(FakeRuntime):
            def execute(inner, spec, action, outdir, cancel, emit):
                started.set()
                if cancel.wait(3):
                    raise InterruptedError("cancelled")
                raise AssertionError("cancel failed")
        self.agent.runtime = BlockingRuntime()
        job = self.agent.submit(self.sid, "运行仿真")
        self.assertTrue(started.wait(2))
        self.agent.cancel(job["id"])
        self.assertEqual(completed(self.agent, job)["status"], "cancelled")

    def test_persistence(self):
        self.store.update_spec(self.sid, {"inductance": .003})
        self.store.save_job(self.sid, {"id": "test", "status": "completed", "events": [{"kind": "tool", "title": "get_design"}]})
        reloaded = Store(self.root / "state")
        self.assertEqual(reloaded.get(self.sid)["spec"]["inductance"], .003)
        self.assertEqual(reloaded.get(self.sid)["last_job"]["events"][0]["title"], "get_design")

    def test_manual_result_import_requires_matching_parameters(self):
        completed(self.agent, self.agent.submit(self.sid, "导出脚本", "export"))
        run = self.store.get(self.sid)["runs"][-1]
        directory = self.root / "outputs" / self.sid / run["id"]
        data = {"ok": True, "source": "MATLAB/Simulink", "spec": {**run["spec"], "output_power": 999}, "metrics": {"test_only": 1}}
        (directory / "result.json").write_text(json.dumps(data), encoding="utf-8")
        app = Application(config=config(), store=self.store)
        try:
            with patch("dcac_agent.web_app.OUTPUTS", self.root / "outputs"):
                app.sync_manual_runs(self.sid)
                self.assertEqual(run["status"], "exported")
                data["spec"] = run["spec"]
                data["run_context"] = {"session_id": self.sid, "run_id": "wrong-run", "design_revision": run["revision"]}
                (directory / "result.json").write_text(json.dumps(data), encoding="utf-8")
                app.sync_manual_runs(self.sid)
                self.assertEqual(run["status"], "exported")
                data["run_context"]["run_id"] = run["id"]
                data["action"] = "build"
                (directory / "result.json").write_text(json.dumps(data), encoding="utf-8")
                app.sync_manual_runs(self.sid)
                self.assertEqual(run["status"], "exported")
                data["action"] = "simulate"
                run["error"] = "previous failed attempt"
                (directory / "result.json").write_text(json.dumps(data), encoding="utf-8")
                app.sync_manual_runs(self.sid)
                self.assertEqual(run["status"], "completed")
                self.assertEqual(run["execution"], "manual_matlab")
                self.assertNotIn("error", run)
                self.assertIn("finished_at", run)
        finally:
            app.agent.pool.shutdown(wait=True)

    def test_llm_calls_tools_and_observes_results(self):
        requests = []
        class Provider(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(inner):
                payload = json.loads(inner.rfile.read(int(inner.headers["Content-Length"])))
                requests.append(payload)
                if len(requests) == 1:
                    message = {"role": "assistant", "content": None, "tool_calls": [{"id": "test_call", "type": "function", "function": {"name": "get_design", "arguments": "{}"}}]}
                else:
                    message = {"role": "assistant", "content": "测试：已读取工具返回的设计参数。"}
                body = json.dumps({"choices": [{"message": message}]}).encode()
                inner.send_response(200); inner.send_header("Content-Length", str(len(body))); inner.end_headers(); inner.wfile.write(body)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            self.agent.config["llm"].update(enabled=True, api_key="TEST_ONLY", model="test-tool-model", base_url=f"http://127.0.0.1:{server.server_port}/v1")
            job = completed(self.agent, self.agent.submit(self.sid, "读取设计参数"))
            self.assertEqual(job["status"], "completed")
            self.assertEqual(len(requests), 2)
            self.assertEqual(requests[1]["messages"][-1]["role"], "tool")
            self.assertIn("380.0", requests[1]["messages"][-1]["content"])
            self.assertNotIn("TEST_ONLY", json.dumps(job))
        finally:
            server.shutdown(); server.server_close(); thread.join()


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = temporary_workspace()
        self.app = Application(config=config(), store=Store(Path(self.tmp.name)))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.app))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.app.agent.pool.shutdown(wait=True)
        cleanup_workspace(self.tmp)

    def request(self, path, data=None, token=True, headers=None):
        h = {"Content-Type": "application/json"}
        if token: h["X-CSRF-Token"] = self.app.csrf
        h.update(headers or {})
        return urllib.request.urlopen(urllib.request.Request(self.base+path, data=None if data is None else json.dumps(data).encode(), headers=h), timeout=3)

    def test_real_http_page_state_and_chat(self):
        with self.request("/") as page:
            self.assertIn("DC/AC Agent".encode(), page.read())
        with self.request("/api/state") as response:
            state = json.load(response)
        with self.request("/api/chat", {"session_id": state["session"]["id"], "message": "电感改为3 mH"}) as response:
            job = json.load(response)
            self.assertEqual(response.status, 202)
        completed(self.app.agent, job)
        with self.request("/api/state") as response:
            self.assertEqual(json.load(response)["session"]["spec"]["inductance"], .003)

    def test_cross_origin_and_missing_token_rejected(self):
        for kwargs in ({"token": False}, {"headers": {"Origin": "https://example.invalid"}}):
            with self.subTest(kwargs=kwargs), self.assertRaises(urllib.error.HTTPError) as err:
                self.request("/api/sessions", {}, **kwargs)
            self.assertEqual(err.exception.code, 403)
            err.exception.close()

    def test_path_traversal_is_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as err:
            self.request("/artifacts/../config.json")
        self.assertEqual(err.exception.code, 404)
        err.exception.close()


if __name__ == "__main__":
    unittest.main()
