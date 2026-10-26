"""Summarize real B audit runs using the unchanged convergence thresholds."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

LIMITS = {"output_rms_relative_percent": .2, "thd_absolute_percentage_points": .1,
          "inductor_rms_relative_percent": .5, "inductor_peak_relative_percent": 1.}


def compare(a, b):
    result = {"stage": a["stage"], "scenario": a["scenario"],
              "coarse_steps": a["steps"], "fine_steps": b["steps"],
              "status": "incomplete", "converged": False}
    if not (a.get("ok") and b.get("ok")):
        return dict(result, failed_criteria=["missing_or_failed_run"])
    import math
    x, y = a["metrics"], b["metrics"]
    keys = ("output_rms", "thd_percent", "inductor_rms", "inductor_peak")
    if not all(math.isfinite(m[k]) for m in (x, y) for k in keys):
        return dict(result, failed_criteria=["nonfinite_metrics"])
    rel = lambda key: 100 * abs(x[key] - y[key]) / max(abs(y[key]), 1e-15)
    delta = {"output_rms_relative_percent": rel("output_rms"),
             "thd_absolute_percentage_points": abs(x["thd_percent"] - y["thd_percent"]),
             "inductor_rms_relative_percent": rel("inductor_rms"),
             "inductor_peak_relative_percent": rel("inductor_peak")}
    failed = [key for key, value in delta.items() if value >= LIMITS[key]]
    return dict(result, **delta, status="complete", converged=not failed, failed_criteria=failed)


def summarize(rows):
    comparisons = []
    for stage, scenario in sorted({(r["stage"], r["scenario"]) for r in rows}):
        pair = sorted([r for r in rows if (r["stage"], r["scenario"]) == (stage, scenario)],
                      key=lambda r: r["steps"])
        if len(pair) < 2:
            comparisons.append(dict(stage=stage, scenario=scenario, status="incomplete",
                                    converged=False, failed_criteria=["missing_peer"]))
        else:
            if len({r["steps"] for r in pair}) != len(pair):
                raise ValueError("Duplicate resolution for one stage/scenario")
            comparisons.extend(compare(a, b) for a, b in zip(pair, pair[1:]))
    return dict(criteria=LIMITS, completed_runs=sum(bool(r.get("ok")) for r in rows),
                runs=rows, comparisons=comparisons, source_environment="MATLAB R2025a",
                scope="20 kHz, four stages and three load conditions; adjacent resolutions; unchanged thresholds")


def main():
    root = Path(__file__).resolve().parents[1]
    default = root / "outputs" / "b_convergence_audit_20261026"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=default / "progress.json")
    parser.add_argument("--output", type=Path, default=default / "audit_summary.json")
    args = parser.parse_args()
    result = summarize(json.loads(args.input.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    for c in result["comparisons"]:
        print(c["stage"], c["scenario"], c.get("coarse_steps"), c.get("fine_steps"),
              c["converged"], ",".join(c["failed_criteria"]))
    print("Successful runs:", result["completed_runs"])


if __name__ == "__main__":
    main()
