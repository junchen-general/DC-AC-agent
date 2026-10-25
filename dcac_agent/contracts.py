"""Versioned integration boundary; independent of B/C solver implementations."""
from __future__ import annotations

import json
import math
from pathlib import Path

SCHEMA_VERSION = "1.0"
DOMAINS = ("magnetic", "thermal", "structural")


def write_manifest(folder: Path, sid: str, run: dict, source: str | None = None):
    manifest = {
        "schema_version": SCHEMA_VERSION, "session_id": sid,
        "run_id": run["id"], "revision": run["revision"], "spec": run["spec"],
        "domain": "electrical", "status": run["status"], "action": run["action"],
        "evidence": "test" if source == "TEST_DOUBLE_ONLY" else
                    "numerical" if source == "MATLAB/Simulink" and run["status"] == "completed" else "unverified",
        "source": source, "fidelity": "ideal_switching_function_open_loop",
        "operating_point": "load_step" if run["spec"].get("load_step") else "rated_resistive",
        "metrics": run.get("metrics"), "error": run.get("error"),
        "artifacts": [p.name for p in sorted(folder.iterdir()) if p.is_file() and p.name not in {"run_manifest.json", "run.json"}],
        "handoff": {"status": "not_ready", "reason": "B需补充原始波形列映射、采样窗口和损耗依据；C需提供部件参数。"},
    }
    (folder / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return manifest


def read_multiphysics(folder: Path, session: dict, run: dict) -> dict:
    """Read only a fixed, run-local result; never execute paths supplied by a model."""
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
