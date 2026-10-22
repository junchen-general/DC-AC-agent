from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .config import ROOT, WORK


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
                                 "magnetic_fea": False, "thermal_fea": False, "structural_fea": False}}

    @staticmethod
    def prepare(spec: dict, action: str, outdir: Path) -> None:
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "request.json").write_text(json.dumps({"action": action, "spec": spec, "output_dir": outdir.as_posix()}, ensure_ascii=False), encoding="utf-8")
        shutil.copyfile(ROOT / "matlab" / "dcac_execute.m", outdir / "dcac_execute.m")
        (outdir / "run_in_matlab.m").write_text(
            "% Run this file in an already-open MATLAB R2025a session.\n"
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
        self.prepare(spec, action, outdir)
        request = outdir / "request.json"
        escape = lambda p: str(p).replace("'", "''").replace("\\", "/")
        expression = f"addpath('{escape(ROOT / 'matlab')}'); dcac_execute('{escape(request)}');"
        logfile = outdir / "matlab.log"
        env = os.environ.copy()
        # An explicit override is useful in restricted workspaces. Ordinary launches
        # retain the user's normal MATLAB preference/license environment.
        if env.get("DCAC_MATLAB_PREFDIR"):
            preference = Path(env["DCAC_MATLAB_PREFDIR"])
            preference.mkdir(parents=True, exist_ok=True)
            env["MATLAB_PREFDIR"] = str(preference)
        emit("matlab", "启动MATLAB批处理进程", {"action": action, "request": request.name})
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
                raise RuntimeError(result.get("error") or f"MATLAB退出码 {process.returncode}")
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
