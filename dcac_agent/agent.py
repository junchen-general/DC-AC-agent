from __future__ import annotations

import copy
import json
import threading
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .config import OUTPUTS
from .design import DesignSpec, extract_parameters
from .runtime import MatlabRuntime
from .store import Store, now
from .contracts import write_manifest, read_multiphysics


SYSTEM = """你是DC/AC Agent，一个单相逆变器设计与仿真助手，使用中文。
当前唯一模板为理想单相全桥开关函数+LC状态方程、单极性SPWM、开环、40ms软启动。
支持参数修改、真实Simulink自动建模、运行、结果检查与历史比较。磁热力有限元、闭环、器件损耗尚未实现。
不得声称已实现尚未实现的功能。用户提出不支持的拓扑/控制/分析时解释边界。
只有工具返回成功才可声称已生成模型或仿真成功。禁止编造波形、指标、文件。
用户让你构建/仿真时应调用相应工具，不能仅提供指导。先读取当前设计；需求有变则设置参数。
参数全部采用SI单位。Vin为直流，Vout为交流有效值。未提供项沿用当前设计并说明。
run_simulation自动重新生成本次模型。它会返回真实结果或错误，不需先create_model。
同一轮最多运行三次仿真。不要擅自把失败的外部环境问题归因于电路设计。
THD为最后四个完整周期的2-40次谐波；只计算给定绕组电阻损耗，不计算总效率。
修改L后不代表磁芯设计已完成。更改输出功率意味着按额定电压重新计算电阻负载。
工具返回结果可用于后续决策；把设计假设、计算值和仿真值区分清楚。
"""


def function_tool(name: str, description: str, properties: dict | None = None, required: list | None = None):
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties or {}, "required": required or [], "additionalProperties": False}}}


PARAMS = {k: {"type": "boolean" if k == "load_step" else "number"} for k in DesignSpec().to_dict()}
TOOLS = [
    function_tool("get_multiphysics_results", "读取当前会话指定电气运行的磁热力交接结果；缺失时返回未运行，不执行求解。", {"run_id": {"type": "string"}}, ["run_id"]),
    function_tool("get_design", "读取当前设计参数、派生计算、功能边界和已完成运行。"),
    function_tool("set_parameters", "校验并更新当前设计。只传需要更改的参数；数值采用SI单位。", {"updates": {"type": "object", "properties": PARAMS, "additionalProperties": False}}, ["updates"]),
    function_tool("inspect_environment", "检测MATLAB路径、连接方式和已实现能力；不宣称许可证已验证。"),
    function_tool("create_model", "通过本机MATLAB真实生成并编译检查可编辑的.slx模型，不运行时域仿真。"),
    function_tool("export_model_script", "导出完整建模和仿真脚本供用户在已打开的MATLAB中执行；不声称模型或仿真已完成。"),
    function_tool("run_simulation", "基于当前参数生成模型并执行真实Simulink仿真，返回有效值、THD和工件链接。"),
    function_tool("compare_runs", "比较当前会话最近两次真实仿真结果。"),
]


class AgentService:
    def __init__(self, config: dict, store: Store, runtime: MatlabRuntime):
        self.config, self.store, self.runtime = config, store, runtime
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dcac-worker")
        self.jobs = {}
        self.lock = threading.RLock()

    def submit(self, sid: str, message: str, action: str = "chat", updates: dict | None = None) -> dict:
        self.store.get(sid)
        if action not in {"chat", "build", "simulate", "parameters", "compare", "export"}:
            raise ValueError("未知任务动作。")
        message = str(message).strip()
        if len(message) > 6000 or (not message and action == "chat"):
            raise ValueError("请输入1至6000字的需求。")
        with self.lock:
            if any(j["session_id"] == sid and j["status"] in {"queued", "running", "cancelling"} for j in self.jobs.values()):
                raise ValueError("当前会话已有任务，请等待完成或先取消。")
            jid = uuid.uuid4().hex[:12]
            job = {"id": jid, "session_id": sid, "status": "queued", "created_at": now(),
                   "events": [], "answer": "", "result": None, "error": "", "cancel": threading.Event()}
            self.jobs[jid] = job
            self.store.message(sid, "user", message or {"build": "生成当前设计的Simulink模型", "simulate": "运行当前设计的Simulink仿真", "parameters": "更新设计参数", "compare": "比较最近两次结果"}.get(action, ""))
            # Freeze provider settings for this job; never expose the key in job snapshots.
            llm = copy.deepcopy(self.config.get("llm", {}))
            self.pool.submit(self._work, job, message, action, updates, llm)
            return self.snapshot(jid)

    def snapshot(self, jid: str) -> dict:
        with self.lock:
            if jid not in self.jobs:
                raise KeyError("任务不存在。")
            return copy.deepcopy({k: v for k, v in self.jobs[jid].items() if k != "cancel"})

    def session_job(self, sid: str) -> dict | None:
        with self.lock:
            matches = [j for j in self.jobs.values() if j["session_id"] == sid]
            return self.snapshot(matches[-1]["id"]) if matches else None

    def cancel(self, jid: str) -> dict:
        with self.lock:
            job = self.jobs[jid]
            if job["status"] in {"queued", "running"}:
                job["cancel"].set()
                job["status"] = "cancelling"
            return self.snapshot(jid)

    def _emit(self, job: dict, kind: str, title: str, data=None):
        with self.lock:
            job["events"].append({"kind": kind, "title": title, "data": data, "at": now()})

    def _work(self, job, message, action, updates, llm):
        try:
            with self.lock:
                job["status"] = "running"
            self._emit(job, "plan", "读取当前设计并检查功能范围")
            if job["cancel"].is_set():
                raise InterruptedError("任务已取消。")
            if action != "chat":
                if updates is not None:
                    self._tool(job, "set_parameters", {"updates": updates})
                tool = {"build": "create_model", "simulate": "run_simulation", "parameters": "get_design", "compare": "compare_runs", "export": "export_model_script"}[action]
                result = self._tool(job, tool, {})
                answer = self._describe(result, tool)
            elif llm.get("enabled"):
                if not llm.get("api_key") or not llm.get("model"):
                    raise ValueError("已启用大模型，但API Key或模型名称未配置。可在设置中补充，或关闭大模型使用规则模式。")
                self._emit(job, "mode", "大模型工具调用模式", {"model": llm["model"]})
                if llm.get("backend", "legacy") == "nanobot":
                    from .nanobot_app import run_nanobot
                    answer = run_nanobot(self, job, message, llm)
                else:
                    answer = self._llm(job, message, llm)
            else:
                self._emit(job, "mode", "本地规则模式（未调用大模型）")
                answer = self._rules(job, message)
            if job["cancel"].is_set():
                raise InterruptedError("任务已取消。")
            with self.lock:
                job["answer"], job["status"], job["finished_at"] = answer, "completed", now()
            self.store.message(job["session_id"], "assistant", answer, job_id=job["id"])
        except Exception as exc:
            cancelled = isinstance(exc, InterruptedError) or job["cancel"].is_set()
            # Never write provider credentials to the user-visible trace.
            message = str(exc)
            if llm.get("api_key"):
                message = message.replace(llm["api_key"], "[redacted]")
            with self.lock:
                job["error"] = message
                job["status"] = "cancelled" if cancelled else "failed"
                job["answer"] = ("任务已取消。" if cancelled else "任务未完成：" + message)
                job["finished_at"] = now()
            self._emit(job, "error", job["answer"])
            self.store.message(job["session_id"], "assistant", job["answer"], job_id=job["id"])
        finally:
            durable = self.snapshot(job["id"])
            durable["result"] = None  # large waveform data is already in the run's result.json
            self.store.save_job(job["session_id"], durable)

    def _tool(self, job: dict, name: str, args: dict) -> dict:
        if job["cancel"].is_set():
            raise InterruptedError("任务已取消。")
        if not isinstance(args, dict):
            raise ValueError("工具参数必须为对象。")
        allowed = {"get_multiphysics_results": {"run_id"}, "set_parameters": {"updates"}, "get_design": set(), "inspect_environment": set(),
                   "create_model": set(), "run_simulation": set(), "compare_runs": set(), "export_model_script": set()}
        if name not in allowed or set(args) - allowed[name]:
            raise ValueError(f"不支持的工具或参数：{name}")
        sid = job["session_id"]
        self._emit(job, "tool", name, args)
        if name == "get_multiphysics_results":
            row = self.store.snapshot(sid)
            run = next((r for r in row["runs"] if r["id"] == args.get("run_id")), None)
            if not run:
                raise ValueError("当前会话不存在该运行。")
            result = read_multiphysics(OUTPUTS / sid / run["id"], row, run)
        elif name == "get_design":
            row = self.store.snapshot(sid)
            result = {"spec": row["spec"], "derived": DesignSpec(**row["spec"]).derived(),
                      "revision": row["revision"], "runs": [{k: r[k] for k in ("id", "status", "action", "revision")} for r in row["runs"]],
                      "limitations": "开环理想开关函数模型；磁热力有限元、闭环、死区与器件损耗尚未实现。"}
        elif name == "set_parameters":
            result = self.store.update_spec(sid, args.get("updates", {}))
        elif name == "inspect_environment":
            result = self.runtime.status()
        elif name == "compare_runs":
            row = self.store.snapshot(sid)
            runs = [r for r in row["runs"] if r["status"] == "completed" and r.get("metrics")]
            if len(runs) < 2:
                result = {"ok": False, "message": "至少需要两次成功的真实仿真，才能比较结果。"}
            else:
                left, right = runs[-2:]
                result = {"ok": True, "before": left, "after": right,
                          "delta": {k: right["metrics"][k] - left["metrics"][k] for k in ("output_rms", "thd_percent", "inductor_rms", "winding_loss")}}
        else:
            count = sum(e["kind"] == "run" for e in job["events"])
            if count >= 3:
                raise ValueError("每轮最多运行三次MATLAB任务；请查看结果后继续对话。")
            row = self.store.snapshot(sid)
            spec = DesignSpec(**row["spec"]).validate()
            run_id = uuid.uuid4().hex[:12]
            outdir = OUTPUTS / sid / run_id
            outdir.mkdir(parents=True)
            run = {"id": run_id, "action": "build" if name == "create_model" else "simulate",
                   "revision": row["revision"], "spec": spec.to_dict(), "status": "running", "created_at": now()}
            self._emit(job, "run", "生成本次独立模型与参数快照", {"run_id": run_id, "revision": row["revision"]})
            try:
                output = {}
                MatlabRuntime.prepare(spec.to_dict(), run["action"], outdir)
                if name == "export_model_script":
                    output = {"ok": True, "exported": True, "message": "仅已导出脚本；尚未运行MATLAB。", "directory": str(outdir)}
                    run.update(status="exported", metrics=None, checks=None, finished_at=now())
                else:
                    output = self.runtime.execute(spec.to_dict(), run["action"], outdir, job["cancel"],
                        lambda kind, title, data=None: self._emit(job, kind, title, data))
                    run.update(status="completed", metrics=output.get("metrics"), checks=output.get("checks"), finished_at=now())
                run["files"] = self._artifacts(sid, run_id, outdir)
                output["run_id"], output["revision"], output["files"] = run_id, run["revision"], run["files"]
                output.pop("model_path", None)
                if not output.get("exported"):
                    with self.lock:
                        job["result"] = output
                result = {k: v for k, v in output.items() if k not in {"waveforms", "harmonics"}}
            except Exception as exc:
                run.update(status="cancelled" if job["cancel"].is_set() else "failed", error=str(exc), finished_at=now())
                run["files"] = self._artifacts(sid, run_id, outdir)
                raise
            finally:
                write_manifest(outdir, sid, run, output.get("source"))
                run["files"] = self._artifacts(sid, run_id, outdir)
                (outdir / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
                self.store.add_run(sid, run)
        self._emit(job, "result", name + " 完成", result)
        return result

    @staticmethod
    def _artifacts(sid, rid, directory):
        return [{"name": p.name, "url": f"/artifacts/{sid}/{rid}/{p.name}", "bytes": p.stat().st_size}
                for p in sorted(directory.iterdir()) if p.is_file() and p.name != "run.json"]

    def _rules(self, job, text):
        if any(word in text for word in ("三相", "并网", "闭环", "PID", "pid", "热应力", "磁场", "温度场", "有限元", "热仿真", "力仿真", "效率")):
            return "当前版本支持单相全桥开环电气仿真。闭环、三相、并网、器件总损耗与磁热力有限元尚未实现。可以先输入‘建立500 W、输入380 V、输出220 V的逆变器并运行仿真’，获得真实模型、波形和THD结果。"
        updates = extract_parameters(text)
        result = None
        if updates:
            result = self._tool(job, "set_parameters", {"updates": updates})
        if "脚本" in text and any(word in text for word in ("导出", "生成", "下载")):
            name = "export_model_script"
        elif any(word in text for word in ("先查看", "只查看", "不要运行", "不运行")):
            name = "get_design"
        elif any(word in text.lower() for word in ("对比", "比较", "compare")):
            name = "compare_runs"
        elif any(word in text.lower() for word in ("仿真", "运行", "simulate", "run")) and "不要仿真" not in text and "不运行" not in text:
            name = "run_simulation"
        elif any(word in text.lower() for word in ("搭建", "建立", "生成模型", "创建模型", "build")):
            name = "create_model"
        elif any(word in text for word in ("环境", "连接", "安装")):
            name = "inspect_environment"
        elif updates or any(word in text for word in ("参数", "设计", "查看")):
            name = "get_design"
        else:
            return ("当前使用本地规则模式，无需API Key。可以直接说：\n"
                    "• 建立500 W、输入380 V、输出220 V的逆变器并运行仿真\n"
                    "• 将开关频率改为25 kHz，重新仿真\n"
                    "• 电感改为3 mH，电容改为6.8 uF\n"
                    "• 加入负载突变并运行仿真\n"
                    "• 比较最近两次结果\n"
                    "在设置中启用兼容工具调用的大模型接口后，可进行更开放的需求理解与结果讨论。")
        result = self._tool(job, name, {})
        return self._describe(result, name)

    @staticmethod
    def _describe(result, name):
        if name == "get_design":
            s, d = result["spec"], result["derived"]
            return (f"当前设计：{s['input_voltage']:g} V直流 → {s['output_voltage']:g} V交流有效值，"
                    f"{s['output_power']:g} W，{s['output_frequency']:g} Hz。\n"
                    f"开关频率{s['switching_frequency']/1000:g} kHz，L={s['inductance']*1000:g} mH，C={s['capacitance']*1e6:g} μF。\n"
                    f"计算值：负载{d['load_resistance']:.2f} Ω，调制度{d['modulation_index']:.3f}，LC谐振频率{d['resonant_frequency']:.0f} Hz。\n"
                    "这些是设计计算值。点击运行仿真可获得真实Simulink结果。")
        if name == "create_model":
            return "已通过MATLAB生成并编译检查可编辑的Simulink模型。可在文件区下载.slx文件。模型为开环理想全桥开关函数＋LC状态方程，尚未执行时域仿真。"
        if name == "export_model_script":
            return ("已导出完整建模与仿真脚本，目前尚未运行MATLAB，也尚未生成.slx或仿真结果。\n"
                    "在正常打开的MATLAB命令窗口执行：\nrun('" + result["directory"].replace("\\", "/") + "/run_in_matlab.m')\n"
                    "执行成功后会打开模型并生成真实结果。回到网页刷新，即可读取原目录下的结果。脚本、参数均可在文件区查看。")
        if name == "run_simulation":
            m = result["metrics"]
            passed = all(result["checks"].values())
            return (f"真实Simulink仿真已完成。\n输出电压 {m['output_rms']:.2f} Vrms（目标偏差{m['voltage_error_percent']:+.2f}%），"
                    f"输出功率{m['output_power']:.2f} W，电压THD（2–40次）{m['thd_percent']:.3f}%。\n"
                    f"电感电流有效值{m['inductor_rms']:.3f} A，峰值{m['inductor_peak']:.3f} A。\n"
                    + ("通过当前电压偏差±5%、THD<5%的检查。" if passed else "部分指标超出当前检查限值，可调整参数后复验。")
                    + "\n分析窗口为末尾4个完整基波周期。当前没有计算总效率和磁热力有限元结果。")
        if name == "compare_runs":
            if not result.get("ok"):
                return result["message"]
            d = result["delta"]
            return (f"最近两次真实仿真对比：\n输出电压变化{d['output_rms']:+.3f} V；"
                    f"THD变化{d['thd_percent']:+.3f}个百分点；电感电流有效值变化{d['inductor_rms']:+.3f} A；"
                    f"给定绕组电阻损耗变化{d['winding_loss']:+.3f} W。\n参数快照与原始结果保存在各自运行目录中。")
        if name == "inspect_environment":
            return ("已找到MATLAB安装路径。" if result["installed"] else "尚未找到MATLAB，请在设置中填写路径。") + "采用批处理连接，不依赖Python版MATLAB Engine。许可证与仿真状态需通过实际运行验证。"
        return json.dumps(result, ensure_ascii=False)

    def _llm(self, job, text, config):
        session = self.store.snapshot(job["session_id"])
        history = [{"role": m["role"], "content": m["content"]} for m in session["messages"][-16:]]
        messages = [{"role": "system", "content": SYSTEM + "\n当前设计：" + json.dumps(session["spec"], ensure_ascii=False)}] + history
        for _ in range(min(12, max(1, int(config.get("max_iterations", 8))))):
            if job["cancel"].is_set():
                raise InterruptedError("任务已取消。")
            payload = {"model": config["model"], "messages": messages, "tools": TOOLS, "tool_choice": "auto"}
            request = urllib.request.Request(config["base_url"].rstrip("/") + "/chat/completions",
                data=json.dumps(payload).encode("utf-8"), headers={"Authorization": "Bearer " + config["api_key"], "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    raw = response.read(4_000_001)
                    if len(raw) > 4_000_000:
                        raise ValueError("大模型响应超过大小限制。")
                    message = json.loads(raw)["choices"][0]["message"]
            except urllib.error.HTTPError as exc:
                raise RuntimeError(f"大模型接口HTTP {exc.code}；请检查服务地址、模型、Key及工具调用支持。") from None
            calls = message.get("tool_calls") or []
            if not calls:
                return message.get("content") or "本轮未返回文本。请查看执行记录。"
            messages.append({k: message[k] for k in ("role", "content", "tool_calls") if k in message})
            for call in calls:
                name = call["function"]["name"]
                try:
                    result = self._tool(job, name, json.loads(call["function"]["arguments"]))
                except InterruptedError:
                    raise
                except Exception as exc:
                    result = {"ok": False, "error": str(exc)}
                    self._emit(job, "error", name + " 失败", result)
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result, ensure_ascii=False)})
        return "已达到本轮工具调用次数限制。请查看执行记录和已生成的结果，再继续提出下一步需求。"
