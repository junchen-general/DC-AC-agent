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
from .design import DesignSpec, extract_parameters, MODEL_STAGES, BASELINE, stage_options
from .runtime import MatlabRuntime
from .store import Store, now
from .contracts import write_manifest, read_multiphysics
from .multiphysics import execute_multiphysics, DEFAULT_OPTIONS, field_options
from .candidate_revision import apply_candidate_revision


SYSTEM = """你是DC/AC Agent，一个单相逆变器设计与仿真助手，使用中文。
支持四阶段模型：基础开环、器件级开环、含损耗开环、电压闭环。
使用set_parameters的model_fidelity枚举切换阶段，其他参数保持不变。切换产生新修订。
基础阶段每开关周期100步；器件阶段400步、1微秒死区；闭环为PR控制并开启死区补偿。
器件阶段需要Simscape Electrical Specialized Power Systems。运行成功不代表步长收敛，不能宣称已验证总效率。
run_multiphysics读取当前修订的真实全采样电气数据并执行E70候选磁热力求解；没有电气结果时自动先仿真。可选run_id仅用于当前修订。结果为单向耦合候选，必须说明L/R差异和指定热源假设，不宣称饱和、强度或整机效率已验证。
用户要求采用候选电感或回填L/R时，用apply_candidate_parameters读取成功C结果的准确L和20°C电阻，创建新修订，然后重新运行电气和磁热力。不要抄写图中四舍五入数值，不自动反复迭代。
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
PARAMS["model_fidelity"] = {"type": "string", "enum": list(MODEL_STAGES), "description": "选择模型阶段；其他参数不变"}
TOOLS = [
    function_tool("apply_candidate_parameters", "将当前修订成功C结果中的精确L和20°C绕组电阻回填为新修订，保留原结果；之后需重新仿真。", {"run_id": {"type": "string"}}, ["run_id"]),
    function_tool("run_multiphysics", "读取完整电气电流，运行E70候选磁场、稳态热场和平面应力；无当前电气结果时先仿真。默认40°C、h=10、额外绕组与磁芯热各0.5W（指定假设）。不自动回填L/R。",
                  {"run_id": {"type": "string"}, "options": {"type": "object", "properties": {k: {"type": "number"} for k in DEFAULT_OPTIONS}, "additionalProperties": False}}),
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

    def submit(self, sid: str, message: str, action: str = "chat", updates: dict | None = None, run_id: str | None = None) -> dict:
        self.store.get(sid)
        if action not in {"chat", "build", "simulate", "parameters", "compare", "export", "multiphysics"}:
            raise ValueError("未知任务动作。")
        message = str(message).strip()
        if len(message) > 6000 or (not message and action == "chat"):
            raise ValueError("请输入1至6000字的需求。")
        with self.lock:
            if any(j["session_id"] == sid and j["status"] in {"queued", "running", "cancelling"} for j in self.jobs.values()):
                raise ValueError("当前会话已有任务，请等待完成或先取消。")
            jid = uuid.uuid4().hex[:12]
            job = {"id": jid, "session_id": sid, "status": "queued", "created_at": now(),
                   "parent_run_id": run_id, "events": [], "answer": "", "result": None, "error": "", "cancel": threading.Event()}
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
                tool = {"build": "create_model", "simulate": "run_simulation", "parameters": "get_design", "compare": "compare_runs", "export": "export_model_script", "multiphysics": "run_multiphysics"}[action]
                result = self._tool(job, tool, {"run_id": job["parent_run_id"]} if action == "multiphysics" and job.get("parent_run_id") else {})
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
        allowed = {"apply_candidate_parameters": {"run_id"}, "run_multiphysics": {"run_id", "options"}, "get_multiphysics_results": {"run_id"}, "set_parameters": {"updates"}, "get_design": set(), "inspect_environment": set(),
                   "create_model": set(), "run_simulation": set(), "compare_runs": set(), "export_model_script": set()}
        if name not in allowed or set(args) - allowed[name]:
            raise ValueError(f"不支持的工具或参数：{name}")
        sid = job["session_id"]
        self._emit(job, "tool", name, args)
        if name == "apply_candidate_parameters":
            result = apply_candidate_revision(self.store, OUTPUTS, sid, args.get("run_id"))
        elif name == "run_multiphysics":
            options = field_options(args.get("options"))
            row = self.store.snapshot(sid)
            if args.get("run_id"):
                run = next((r for r in row["runs"] if r["id"] == args["run_id"]), None)
                if run is None:
                    raise ValueError("当前会话不存在该电气运行。")
            else:
                run = next((r for r in reversed(row["runs"]) if r["status"] == "completed" and r["action"] == "simulate" and r["revision"] == row["revision"]), None)
                if run is None:
                    self._tool(job, "run_simulation", {})
                    row = self.store.snapshot(sid)
                    run = row["runs"][-1]
            if sum(e["kind"] == "run" for e in job["events"]) >= 3:
                raise ValueError("每轮最多三次MATLAB任务。")
            folder = OUTPUTS / sid / run["id"]
            try:
                result = execute_multiphysics(self.runtime, folder, row, run, job["cancel"],
                    lambda kind, title, data=None: self._emit(job, kind, title, data), options)
            finally:
                with self.store.lock:
                    target = next(r for r in self.store.get(sid)["runs"] if r["id"] == run["id"])
                    target["files"] = self._artifacts(sid, run["id"], folder)
                    (folder / "run.json").write_text(json.dumps(target, ensure_ascii=False, indent=2), encoding="utf-8")
                    self.store.save()
        elif name == "get_multiphysics_results":
            row = self.store.snapshot(sid)
            run = next((r for r in row["runs"] if r["id"] == args.get("run_id")), None)
            if not run:
                raise ValueError("当前会话不存在该运行。")
            result = read_multiphysics(OUTPUTS / sid / run["id"], row, run)
        elif name == "get_design":
            row = self.store.snapshot(sid)
            result = {"spec": row["spec"], "derived": DesignSpec(**row["spec"]).derived(),
                      "engineering_review": DesignSpec(**row["spec"]).engineering_review(),
                      "revision": row["revision"], "runs": [{k: r[k] for k in ("id", "status", "action", "revision")} for r in row["runs"]],
                      "model_stages": MODEL_STAGES, "electrical": stage_options(row["spec"]),
                      "candidate_updates": row.get("candidate_updates", []),
                      "limitations": "四阶段可建模与仿真；器件阶段需SPS。单次通过不代表数值收敛，不输出整机效率；支持当前电气数据驱动的E70候选磁热力求解（指定热源、单向耦合）。"}
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
                MatlabRuntime.prepare(
                    spec.to_dict(), run["action"], outdir,
                    electrical=stage_options(spec.to_dict()),
                    context={"session_id": sid, "run_id": run_id,
                             "design_revision": row["revision"]},
                )
                if name == "export_model_script":
                    output = {"ok": True, "exported": True, "message": "仅已导出脚本；尚未运行MATLAB。", "directory": str(outdir)}
                    run.update(status="exported", metrics=None, checks=None, finished_at=now())
                else:
                    output = self.runtime.execute(spec.to_dict(), run["action"], outdir, job["cancel"],
                        lambda kind, title, data=None: self._emit(job, kind, title, data))
                    run.update(status="completed", metrics=output.get("metrics"), checks=output.get("checks"), finished_at=now())
                run["files"] = self._artifacts(sid, run_id, outdir)
                output["model_fidelity"] = spec.model_fidelity
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
        return [{"name": p.relative_to(directory).as_posix(), "url": f"/artifacts/{sid}/{rid}/{p.relative_to(directory).as_posix()}", "bytes": p.stat().st_size}
                for p in sorted(directory.rglob("*")) if p.is_file() and p.name != "run.json"]

    def _rules(self, job, text):
        if any(phrase in text for phrase in ('回填候选参数', '应用候选电感')):
            if any(word in text for word in ('不要', '不执行', '解释', '介绍', '什么意思', '如何', '怎么')):
                return '候选回填会读取当前C结果中的L和20°C电阻，建立新修订；本次未更新参数。'
            row = self.store.snapshot(job['session_id'])
            run = next((r for r in reversed(row['runs']) if r['status']=='completed'
                        and r['action']=='simulate' and r['revision']==row['revision']), None)
            if run is None:
                return '请先完成当前设计的电气与磁热力求解，再回填候选参数。'
            return self._describe(self._tool(job, 'apply_candidate_parameters', {'run_id':run['id']}), 'apply_candidate_parameters')
        if any(word in text for word in ("磁热力", "磁场", "温度场", "热应力", "多物理场")):
            if any(word in text for word in ("不运行", "不要运行", "不要仿真", "只查看", "仅查看", "介绍", "解释", "导出")) or not any(word in text for word in ("运行", "求解", "分析", "计算", "仿真")):
                return "磁热力采用E70候选与当前电气全采样数据，默认环境40°C、h=10，指定额外绕组/磁芯热各0.5 W；本次未执行求解。"
            return self._describe(self._tool(job, "run_multiphysics", {}), "run_multiphysics")
        if any(word in text for word in ("三相", "并网", "PID", "pid", "热应力", "磁场", "温度场", "有限元", "热仿真", "力仿真", "效率")):
            return "支持四阶段单相模型和PR电压闭环；三相、并网、PID尚未接入，不输出完整整机效率。"
        updates = extract_parameters(text)
        result = None
        if updates:
            result = self._tool(job, "set_parameters", {"updates": updates})
        if "脚本" in text and any(word in text for word in ("导出", "生成", "下载")):
            name = "export_model_script"
        elif (any(word in text for word in ("生成模型", "创建模型", "生成当前设计的模型")) and not any(word in text for word in ("运行", "仿真"))) or ("生成" in text and "模型" in text and any(word in text for word in ("不运行", "不要运行", "不仿真"))):
            name = "create_model"
        elif any(word in text for word in ("先查看", "只查看", "不要运行", "不运行", "不要仿真")):
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
        if name == 'apply_candidate_parameters':
            s=result['spec']
            return (f"已建立设计修订{result['revision']}：L={s['inductance']*1000:.9g} mH，"
                    f"R20={s['winding_resistance']:.9g} Ω。计算保留源结果的完整精度。\n"
                    "电路电阻参考温度为20°C；原结果保留。请重新运行电气仿真，再运行磁热力分析。")
        if name == "run_multiphysics":
            d = result["domains"]
            info = result["input_summary"]
            return (f"已完成运行{result['parent_run_id']}的E70候选磁热力求解。\n"
                    f"中心柱截面平均峰值磁密{d['magnetic']['metrics']['bulk_peak_flux_density']['value']:.4f} T；"
                    f"最高温度{d['thermal']['metrics']['peak_temperature']['value']:.2f} °C；"
                    f"最大位移{1e6*d['structural']['metrics']['max_displacement']['value']:.2f} μm。\n"
                    f"候选L与电气L差异{info['L_difference_percent']:+.2f}%；候选R20与电气R差异{info['R_difference_percent']:+.2f}%。\n"
                    "云图、材料与边界依据已关联到该电气运行。本次场求解不自动更新电路参数；可通过候选回填另建修订。采用指定热源和线性场模型，不代表饱和、强度或网格收敛验证完成。")
        if name == "get_design":
            s, d = result["spec"], result["derived"]
            return (f"模型阶段：{MODEL_STAGES[s.get('model_fidelity', BASELINE)]}。\n当前设计：{s['input_voltage']:g} V直流 → {s['output_voltage']:g} V交流有效值，"
                    f"{s['output_power']:g} W，{s['output_frequency']:g} Hz。\n"
                    f"开关频率{s['switching_frequency']/1000:g} kHz，L={s['inductance']*1000:g} mH，C={s['capacitance']*1e6:g} μF。\n"
                    f"计算值：负载{d['load_resistance']:.2f} Ω，调制度{d['modulation_index']:.3f}，LC谐振频率{d['resonant_frequency']:.0f} Hz。\n"
                    "这些是设计计算值。点击运行仿真可获得真实Simulink结果。")
        if name == "create_model":
            return f"已通过MATLAB生成并编译检查{MODEL_STAGES[result.get('model_fidelity', BASELINE)]}。可下载.slx文件；尚未执行时域仿真。"
        if name == "export_model_script":
            return ("已导出完整建模与仿真脚本，目前尚未运行MATLAB，也尚未生成.slx或仿真结果。\n"
                    "在正常打开的MATLAB命令窗口执行：\nrun('" + result["directory"].replace("\\", "/") + "/run_in_matlab.m')\n"
                    "执行成功后会打开模型并生成真实结果。回到网页刷新，即可读取原目录下的结果。脚本、参数均可在文件区查看。")
        if name == "run_simulation":
            m = result["metrics"]
            passed = all(result["checks"].values())
            return (f"{MODEL_STAGES[result.get('model_fidelity', BASELINE)]}真实Simulink仿真已完成。\n输出电压 {m['output_rms']:.2f} Vrms（目标偏差{m['voltage_error_percent']:+.2f}%），"
                    f"输出功率{m['output_power']:.2f} W，电压THD（2–40次）{m['thd_percent']:.3f}%。\n"
                    f"电感电流有效值{m['inductor_rms']:.3f} A，峰值{m['inductor_peak']:.3f} A。\n"
                    + ("通过当前电压偏差±5%、THD<5%的检查。" if passed else "部分指标超出当前检查限值，可调整参数后复验。")
                    + "\n分析窗口为末尾4个完整基波周期。单次指标通过不代表步长收敛；尚无总效率和当前运行的磁热力结果。")
        if name == "compare_runs":
            if not result.get("ok"):
                return result["message"]
            d = result["delta"]
            return (f"最近两次真实仿真对比：{MODEL_STAGES[result['before']['spec'].get('model_fidelity', BASELINE)]} → {MODEL_STAGES[result['after']['spec'].get('model_fidelity', BASELINE)]}（工况与模型差异请结合参数快照解释）。\n输出电压变化{d['output_rms']:+.3f} V；"
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
