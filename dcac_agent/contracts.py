"""Versioned integration boundary; independent of B/C solver implementations."""
from __future__ import annotations

import json
import math
from pathlib import Path
from .design import BASELINE, stage_options

SCHEMA_VERSION = "1.0"
DOMAINS = ("magnetic", "thermal", "structural")


def write_manifest(folder: Path, sid: str, run: dict, source: str | None = None):
    # B's standalone MATLAB contract uses the same filename as A's run summary.
    # Preserve the rich handoff before writing the UI-compatible summary.
    handoff = None
    candidate = folder / "run_manifest.json"
    saved_handoff = folder / "electrical_handoff.json"
    if candidate.exists():
        existing = json.loads(candidate.read_text(encoding="utf-8-sig"))
        if existing.get("schema_version") == "dcac.electrical.handoff/1.0":
            saved_handoff.write_bytes(candidate.read_bytes())
    if saved_handoff.exists():
        data = json.loads(saved_handoff.read_text(encoding="utf-8-sig"))
        identity = data.get("identity", {})
        matches = (identity.get("session_id") == sid and identity.get("run_id") == run["id"]
                   and identity.get("design_revision") == run["revision"] and data.get("spec") == run["spec"]
                   and data.get("model", {}).get("stage", BASELINE) == run["spec"].get("model_fidelity", BASELINE))
        handoff = {"status": "available" if matches and data.get("status") == "success"
                   and data.get("data_origin") == "real_simulation" and run["status"] == "completed"
                   and run["action"] == "simulate" and source == "MATLAB/Simulink"
                   else "not_ready", "file": "electrical_handoff.json",
                   "identity_matches": matches,
                   "reason": "电气交接文件保留；损耗依据、收敛状态及部件匹配仍须B/C复核。"}
    manifest = {
        "schema_version": SCHEMA_VERSION, "session_id": sid,
        "run_id": run["id"], "revision": run["revision"], "spec": run["spec"],
        "domain": "electrical", "status": run["status"], "action": run["action"],
        "evidence": "test" if source == "TEST_DOUBLE_ONLY" else
                    "numerical" if source == "MATLAB/Simulink" and run["status"] == "completed" else "unverified",
        "source": source, "fidelity": run["spec"].get("model_fidelity", BASELINE),
        "electrical": stage_options(run["spec"]),
        "operating_point": "load_step" if run["spec"].get("load_step") else "rated_resistive",
        "metrics": run.get("metrics"), "error": run.get("error"),
        "artifacts": [p.name for p in sorted(folder.iterdir()) if p.is_file() and p.name not in {"run_manifest.json", "run.json"}],
        "handoff": {"status": "not_ready", "reason": "B需补充原始波形列映射、采样窗口和损耗依据；C需提供部件参数。"},
    }
    if handoff is not None:
        manifest["handoff"] = handoff
    (folder / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return manifest


def read_multiphysics(folder: Path, session: dict, run: dict, *, ignore_status=False) -> dict:
    """Read only a fixed, run-local result; never execute paths supplied by a model."""
    status_path = folder / "multiphysics_status.json"
    if status_path.exists() and not ignore_status:
        status = json.loads(status_path.read_text(encoding="utf-8-sig"))
        if status.get("status") in {"running", "failed", "cancelled"}:
            return {**status, "run_id": run["id"], "message": status.get("message", "磁热力求解正在运行。")}
    path = folder / "multiphysics_result.json"
    if not path.exists():
        return {"status": "not_run", "message": "C尚未交付此运行的多物理场结果。", "run_id": run["id"]}
    if path.stat().st_size > 2_000_000:
        raise ValueError("多物理场结果文件过大。")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("多物理场协议版本不匹配。")
    for key, expected in (("session_id", session["id"]), ("parent_run_id", run["id"]), ("revision", run["revision"])):
        if data.get(key) != expected:
            raise ValueError("多物理场结果归属不匹配：" + key)
    if data.get("evidence") not in {"test", "numerical", "analytical"}:
        raise ValueError("必须注明结果证据类型。")
    if data["evidence"] == "numerical":
        if run.get("status") != "completed" or run.get("action") != "simulate":
            raise ValueError("数值场结果必须依赖成功的电气仿真。")
        parent = json.loads((folder / "result.json").read_text(encoding="utf-8-sig"))
        if parent.get("source") != "MATLAB/Simulink" or parent.get("spec") != run.get("spec") or not parent.get("ok"):
            raise ValueError("父电气运行的证据或参数不匹配。")
    for key in ("component_version", "material_version", "boundary_version", "solver", "verification"):
        if not data.get(key):
            raise ValueError("多物理场缺少依据：" + key)
    for domain in DOMAINS:
        item = data.get("domains", {}).get(domain, {})
        if item.get("status") not in {"not_run", "failed", "completed"}:
            raise ValueError("物理场状态无效：" + domain)
        metrics = item.get("metrics", {})
        if item["status"] == "completed" and not metrics:
            raise ValueError("成功结果必须包含指标。")
        for metric in metrics.values():
            value = metric.get("value")
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not metric.get("unit"):
                raise ValueError("指标必须为有限数值并注明单位。")
        files = []
        for name in item.get("artifacts", []):
            target = (folder / name).resolve()
            if not target.is_relative_to(folder.resolve()) or not target.is_file():
                raise ValueError("工件不在当前运行目录或不存在。")
            if target.suffix.lower() not in {".png", ".json", ".csv", ".mat", ".pdf", ".m", ".slx"}:
                raise ValueError("工件类型不支持。")
            from urllib.parse import quote
            files.append({"name": name, "url": f"/artifacts/{session['id']}/{run['id']}/{quote(name)}", "image": target.suffix.lower() == ".png"})
        item["files"] = files
    data["stale"] = run["revision"] != session["revision"]
    return data
