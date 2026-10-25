"""Real Nanobot loop with explicit provider double; no external LLM/solver claims."""
import asyncio
import json
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from test_core import temporary_workspace, cleanup_workspace, config, FakeRuntime, completed
from dcac_agent.agent import AgentService
from dcac_agent.store import Store
from dcac_agent.contracts import read_multiphysics
from dcac_agent.nanobot_app import runtime_status


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_workspace()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "store")
        self.session = self.store.create()
        self.run = {"id": "a" * 12, "revision": 0}
        self.data = {"schema_version": "1.0", "session_id": self.session["id"],
            "parent_run_id": self.run["id"], "revision": 0, "evidence": "test",
            "component_version": "test", "material_version": "test", "boundary_version": "test",
            "solver": "TEST_DOUBLE", "verification": {"mesh": "test only"},
            "domains": {k: {"status": "not_run", "metrics": {}, "artifacts": []} for k in ("magnetic", "thermal", "structural")}}

    def tearDown(self):
        cleanup_workspace(self.temp)

    def write(self):
        (self.root / "multiphysics_result.json").write_text(json.dumps(self.data), encoding="utf-8")

    def test_missing_and_stale(self):
        self.assertEqual(read_multiphysics(self.root, self.session, self.run)["status"], "not_run")
        self.write()
        self.session["revision"] = 1
        self.assertTrue(read_multiphysics(self.root, self.session, self.run)["stale"])

    def test_wrong_session_and_unsafe_path_rejected(self):
        self.data["session_id"] = "b" * 12
        self.write()
        with self.assertRaises(ValueError):
            read_multiphysics(self.root, self.session, self.run)
        self.data["session_id"] = self.session["id"]
        self.data["domains"]["magnetic"]["artifacts"] = ["../sessions.json"]
        self.write()
        with self.assertRaises(ValueError):
            read_multiphysics(self.root, self.session, self.run)

    def test_nonfinite_metric_rejected(self):
        self.data["domains"]["thermal"].update(status="completed", metrics={"temperature": {"value": float("nan"), "unit": "K"}})
        self.write()
        with self.assertRaises(ValueError):
            read_multiphysics(self.root, self.session, self.run)


@unittest.skipUnless(runtime_status()["supported"], "requires optional nanobot-ai==0.3.5")
class NanobotTests(unittest.TestCase):
    setUp = ContractTests.setUp
    tearDown = ContractTests.tearDown

    def test_cancel_while_provider_waits(self):
        from nanobot.providers.base import LLMProvider
        entered = threading.Event()

        class WaitingProvider(LLMProvider):
            def get_default_model(self):
                return "test-only"
            async def chat(self, **kwargs):
                entered.set()
                await asyncio.sleep(60)

        settings = config()
        settings["llm"].update(enabled=True, backend="nanobot", api_key="test-only", model="test-only")
        agent = AgentService(settings, self.store, FakeRuntime())
        try:
            with patch("nanobot.providers.factory.make_provider", return_value=WaitingProvider(provider_name="test-double")), patch("dcac_agent.nanobot_app.WORK", self.root / "work"):
                job = agent.submit(self.session["id"], "测试取消")
                self.assertTrue(entered.wait(20))
                agent.cancel(job["id"])
                self.assertEqual(completed(agent, job)["status"], "cancelled")
        finally:
            for job in agent.jobs.values():
                job["cancel"].set()
            agent.pool.shutdown(wait=True)

    def test_real_loop_tools_and_export(self):
        from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest

        class ProviderDouble(LLMProvider):
            calls = 0
            seen = []
            def get_default_model(self):
                return "test-only"
            async def chat(self, messages, tools=None, **kwargs):
                self.seen.append(messages)
                self.calls += 1
                if self.calls == 1:
                    return LLMResponse(content=None, tool_calls=[ToolCallRequest("t1", "set_parameters", {"updates": {"switching_frequency": 25000}})])
                if self.calls == 2:
                    return LLMResponse(content=None, tool_calls=[ToolCallRequest("t2", "export_model_script", {})])
                return LLMResponse(content="测试服务：仅导出，未求解。")

        provider = ProviderDouble(provider_name="test-double")
        settings = config()
        settings["llm"].update(enabled=True, backend="nanobot", api_key="test-secret-only", model="test-only")
        agent = AgentService(settings, self.store, FakeRuntime())
        try:
            with patch("nanobot.providers.factory.make_provider", return_value=provider), patch("dcac_agent.nanobot_app.WORK", self.root / "work"), patch("dcac_agent.agent.OUTPUTS", self.root / "outputs"):
                submitted = agent.submit(self.session["id"], "测试：修改开关频率并导出")
                for _ in range(600):
                    job = agent.snapshot(submitted["id"])
                    if job["status"] not in {"queued", "running", "cancelling"}:
                        break
                    time.sleep(.05)
                else:
                    agent.cancel(submitted["id"])
                    self.fail("Nanobot test timed out")
            self.assertEqual(job["status"], "completed", job.get("error"))
            self.assertEqual(provider.calls, 3)
            self.assertTrue(any(message.get("role") == "tool" for message in provider.seen[-1]))
            mode = next(e for e in job["events"] if e["title"] == "Nanobot 0.3.5 工具调用")
            self.assertNotIn("exec", mode["data"]["tools"])
            row = self.store.snapshot(self.session["id"])
            self.assertEqual(row["spec"]["switching_frequency"], 25000)
            self.assertEqual(row["runs"][0]["status"], "exported")
            self.assertTrue(any(e["kind"] == "tool" and e["title"] == "export_model_script" for e in job["events"]))
            for file in (self.root / "work").rglob("*.json"):
                self.assertNotIn("test-secret-only", file.read_text(encoding="utf-8"))
        finally:
            agent.pool.shutdown(wait=True)

