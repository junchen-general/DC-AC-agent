from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

from .config import ROOT, WORK
from .design import stage_options


class MatlabRuntime:
    """Version-independent batch bridge; serial execution and owned-process cancellation."""

    def __init__(self, config: dict):
        self.config = config
        self.lock = threading.Lock()

    def status(self) -> dict:
        executable = self.config.get("matlab_executable") or shutil.which("matlab") or ""
        found = bool(executable and Path(executable).is_file())
        return {"installed": found, "executable": executable, "bridge": "MATLAB -batch",
                "connection": "not_tested", "busy": self.lock.locked(),
                "note": "检测到安装路径不代表许可证或仿真已经验证；运行任务后查看真实日志。",
                "capabilities": {"model_build": True, "electrical_simulation": True,
                                 "magnetic_fea": True, "thermal_fea": True, "structural_fea": True},
                "capability_status_v1": {
                    "model_build": {"supported": True, "verified": False},
                    "electrical_simulation": {"supported": True, "verified": False},
                    "multiphysics": {"supported": True, "verified": False, "requires": "Partial Differential Equation Toolbox", "scope": "conditional E70 candidate, linear 2D fields"},
                    "device_bridge": {"supported": True, "verified": False,
                                      "requires": "Simscape Electrical Specialized Power Systems"}}}

    @staticmethod
    def prepare(spec: dict, action: str, outdir: Path, *, electrical: dict | None = None,
                context: dict | None = None) -> None:
        outdir.mkdir(parents=True, exist_ok=True)
        load_step = bool(spec.get("load_step"))
        final_ratio = float(spec.get("load_final_ratio", 0.5))
        scenario = "rated"
        if load_step:
            scenario = "rated_to_half" if abs(final_ratio - 0.5) < 1e-12 else "load_step"
        electrical_request = {
            "schema_version": "dcac.electrical.request/1.0",
            "model_fidelity": "baseline_ideal_switching_open_loop",
            "scenario_id": scenario,
            "steps_per_switching_period": 100,
            "dead_time_s": 1e-6,
            "closed_loop_dead_time_compensation": False,
            "soft_start_s": 0.04,
        }
        electrical_request.update(stage_options(spec))
        if electrical:
            electrical_request.update(electrical)
        inferred = {
            "session_id": outdir.parent.name if len(outdir.parent.name) == 12 else "",
            "run_id": outdir.name or uuid.uuid4().hex[:12],
            "design_revision": None,
            "component_revision_id": "",
            "parent_component_revision_id": "",
            "comparison_group_id": "",
            "comparison_peer_run_ids": [],
        }
        if context:
            inferred.update(context)
        request_data = {"schema_version": "dcac.request/1.1", "action": action, "spec": spec,
                        "electrical": electrical_request, "run_context": inferred,
                        "output_dir": outdir.as_posix()}
        (outdir / "request.json").write_text(json.dumps(request_data, ensure_ascii=False, indent=2), encoding="utf-8")
        shutil.copyfile(ROOT / "matlab" / "dcac_execute.m", outdir / "dcac_execute.m")
        support = ROOT / "matlab" / "electrical"
        if support.is_dir():
            for source in sorted(support.iterdir()):
                if source.is_file() and source.suffix.lower() in {".m", ".json", ".md"}:
                    shutil.copyfile(source, outdir / source.name)
        (outdir / "run_in_matlab.m").write_text(
            "% Run this file in an already-open MATLAB R2023b or newer session.\n"
            "% It builds an editable .slx model and executes a real Simulink simulation.\n"
            "taskDir = fileparts(mfilename('fullpath'));\n"
            "addpath(taskDir);\n"
            "request = jsondecode(fileread(fullfile(taskDir,'request.json')));\n"
            "request.output_dir = taskDir;\n"
            "manualRequest = fullfile(taskDir,'manual_request.json');\n"
            "fid = fopen(manualRequest,'w','n','UTF-8');\n"
            "fprintf(fid,'%s',jsonencode(request)); fclose(fid);\n"
            "dcac_execute(manualRequest);\n"
            "open_system(fullfile(taskDir,'dcac_inverter.slx'));\n", encoding="utf-8")

    def execute(self, spec: dict, action: str, outdir: Path, cancel: threading.Event, emit) -> dict:
        if action not in {"build", "simulate"}:
            raise ValueError("Unsupported MATLAB action")
        executable = self.status()["executable"]
        if not executable or not Path(executable).is_file():
            raise RuntimeError("未找到MATLAB。请在设置中填写 matlab.exe 完整路径。")
        # AgentService currently prepares recovery files before calling execute.
        # Preserve any additive electrical/context fields from that request instead
        # of overwriting them during the second, defensive prepare call.
        existing_electrical = None
        existing_context = None
        existing_request = outdir / "request.json"
        if existing_request.is_file():
            try:
                prepared = json.loads(existing_request.read_text(encoding="utf-8-sig"))
                existing_electrical = prepared.get("electrical")
                existing_context = prepared.get("run_context")
            except (OSError, UnicodeError, json.JSONDecodeError):
                pass
        self.prepare(spec, action, outdir, electrical=existing_electrical, context=existing_context)
        request = outdir / "request.json"
        escape = lambda p: str(p).replace("'", "''").replace("\\", "/")
        expression = f"addpath('{escape(ROOT / 'matlab')}'); dcac_execute('{escape(request)}');"
        return self._batch(expression, outdir, cancel, emit, action)

    def execute_fields(self, outdir: Path, cancel: threading.Event, emit) -> dict:
        escape = lambda p: str(p).replace("'", "''").replace("\\", "/")
        expression = f"addpath('{escape(outdir)}'); dcac_multiphysics('{escape(outdir / 'field_request.json')}');"
        return self._batch(expression, outdir, cancel, emit, "multiphysics")

    def _batch(self, expression, outdir, cancel, emit, action):
        executable = self.status()["executable"]
        if not executable or not Path(executable).is_file():
            raise RuntimeError("未找到MATLAB。请在设置中填写 matlab.exe 完整路径。")
        logfile = outdir / "matlab.log"
        env = os.environ.copy()
        # An explicit override is useful in restricted workspaces. Ordinary launches
        # retain the user's normal MATLAB preference/license environment.
        if env.get("DCAC_MATLAB_PREFDIR"):
            preference = Path(env["DCAC_MATLAB_PREFDIR"])
            preference.mkdir(parents=True, exist_ok=True)
            env["MATLAB_PREFDIR"] = str(preference)
        emit("matlab", "启动MATLAB批处理进程", {"action": action})
        WORK.mkdir(parents=True, exist_ok=True)
        with self.lock, (outdir / "process.log").open("wb") as stream:
            if cancel.is_set():
                raise InterruptedError("任务已取消。")
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            process = subprocess.Popen([executable, "-batch", expression, "-logfile", str(logfile)],
                                       cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                       creationflags=flags)
            started = time.monotonic()
            while process.poll() is None:
                timed_out = time.monotonic() - started > int(self.config.get("matlab_timeout_seconds", 300))
                if cancel.is_set() or timed_out:
                    self._terminate(process)
                    raise InterruptedError("任务已取消。" if cancel.is_set() else "MATLAB运行超时；请检查许可证服务及任务日志。")
                time.sleep(0.25)
            result_file = outdir / "result.json"
            if not result_file.exists():
                tail = self.log_tail(outdir)
                if "5201" in tail:
                    reason = "MATLAB启动失败：无法与MathWorks服务通信（5201）。请在本机正常启动MATLAB确认许可证/服务可用，再重试。"
                    raise RuntimeError(reason + "\n完整启动输出已保存在文件区的matlab.log和process.log；也可导出脚本在已打开的MATLAB中执行。")
                elif "PrefdirNotWritable" in tail or "预设项文件夹" in tail:
                    reason = "MATLAB首选项目录不可写。请在本机正常启动，或配置 DCAC_MATLAB_PREFDIR 为可写目录。"
                    raise RuntimeError(reason + "\n完整启动输出已保存在文件区的matlab.log和process.log。")
                else:
                    reason = "MATLAB未生成结果文件；请查看真实启动日志。"
                raise RuntimeError(reason + "\n" + tail[-2500:])
            result = json.loads(result_file.read_text(encoding="utf-8-sig"))
            if process.returncode or not result.get("ok"):
                phase = result.get("phase")
                detail = result.get("error") or f"MATLAB退出码 {process.returncode}"
                if phase:
                    detail = f"MATLAB阶段 {phase} 失败：{detail}"
                raise RuntimeError(detail)
            return result

    @staticmethod
    def _terminate(process):
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
        else:
            process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    @staticmethod
    def log_tail(outdir: Path) -> str:
        parts = []
        for name in ("matlab.log", "process.log"):
            path = outdir / name
            if path.exists():
                with path.open("rb") as stream:
                    stream.seek(max(0, path.stat().st_size - 7000))
                    raw = stream.read()
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    text = raw.decode("gb18030", errors="replace")
                if text.strip():
                    parts.append(f"[{name}]\n{text}")
        return "\n".join(parts)
