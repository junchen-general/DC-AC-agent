"""Create the compact, full-sample-rate B-to-C GitHub handoff artifacts.

The authoritative 0.24 s validation MAT files remain under the ignored
``outputs/`` tree.  This exporter selects the manifest-defined
``magnetic_representative`` window (one complete 50 Hz period) without
decimation and writes a compressed MATLAB v5 file suitable for GitHub.
"""
from __future__ import annotations

import json
import shutil
import csv
from pathlib import Path

try:
    import numpy as np
    from scipy.io import loadmat, savemat
except ModuleNotFoundError as error:  # optional artifact-export dependency
    raise SystemExit("Install scipy and numpy to regenerate the compact handoff MAT files.") from error


ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "outputs" / "b_final" / "baseline_build" / "validation"
DESTINATION = ROOT / "artifacts" / "b_final"
SCENARIOS = ("rated", "half_load", "rated_to_half")
STAGES = (
    "baseline_ideal_switching_open_loop",
    "sps_device_open_loop",
    "sps_device_lossy_open_loop",
    "sps_device_closed_loop",
)

# Keep the full sample rate while excluding arrays that are algebraically
# recoverable from these primary channels (for example winding voltage,
# capacitor current, conductance and instantaneous winding loss).
HANDOFF_SIGNALS = (
    "time_s",
    "sample_index_0based",
    "v_out_V",
    "i_inductor_A",
    "i_load_A",
    "v_bridge_V",
    "v_inductor_terminal_V",
    "gate_a_upper",
    "gate_a_lower",
    "gate_b_upper",
    "gate_b_lower",
    "i_dc_A",
    "v_dc_V",
)


def matlab_value(value):
    """Convert scipy ``mat_struct`` values into savemat-compatible objects."""
    if hasattr(value, "_fieldnames"):
        return {name: matlab_value(getattr(value, name)) for name in value._fieldnames}
    if isinstance(value, np.ndarray) and value.dtype == object:
        return np.array([matlab_value(item) for item in value], dtype=object)
    return value


def select_window(windows, window_id: str):
    candidates = np.atleast_1d(windows)
    for window in candidates:
        if str(window.id) == window_id:
            return window
    raise RuntimeError(f"Window {window_id!r} not found")


def export_case(scenario: str) -> dict:
    case_name = f"sps_device_closed_loop__{scenario}__n400"
    source_dir = VALIDATION / case_name
    source_mat = source_dir / "electrical_raw_v1.mat"
    data = loadmat(source_mat, squeeze_me=True, struct_as_record=False)
    window = select_window(data["windows"], "magnetic_representative")
    start = int(window.start_index_0based)
    stop = int(window.end_index_exclusive_0based)
    signals = data["signals"]
    selected_signals = {
        name: np.asarray(getattr(signals, name))[start:stop]
        for name in HANDOFF_SIGNALS
    }
    package = {
        "schema_version": "dcac.electrical.github_handoff/1.0",
        "data_origin": "real_simulation_window_no_decimation",
        "source_case": case_name,
        "source_full_run_file": str(source_mat.relative_to(ROOT)).replace("\\", "/"),
        "signals": selected_signals,
        "window": matlab_value(window),
        "meta": matlab_value(data["meta"]),
        "spec": matlab_value(data["s"]),
        "electrical_request": matlab_value(data["e"]),
        "run_context": matlab_value(data["context"]),
        "metrics": matlab_value(data["metrics"]),
        "electrical_metrics": matlab_value(data["electricalMetrics"]),
        "dynamic": matlab_value(data["dynamic"]),
        "losses": matlab_value(data["losses"]),
    }
    raw_dir = DESTINATION / "raw_windows"
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_mat = raw_dir / f"{scenario}_magnetic_representative_n400.mat"
    savemat(output_mat, package, do_compression=True, long_field_names=True)

    case_dest = DESTINATION / "cases" / scenario
    case_dest.mkdir(parents=True, exist_ok=True)
    for name in ("waveforms.png", "run_manifest.json", "loss_basis_v1.json"):
        shutil.copy2(source_dir / name, case_dest / name)
    result = json.loads((source_dir / "result.json").read_text(encoding="utf-8"))
    result["model_path"] = "artifacts/b_final/models/sps_device_closed_loop.slx"
    (case_dest / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    request = json.loads((source_dir / "request.json").read_text(encoding="utf-8"))
    request["output_dir"] = f"outputs/reproduced/{case_name}"
    (case_dest / "request.json").write_text(
        json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "scenario": scenario,
        "source_case": case_name,
        "sample_count": stop - start,
        "fixed_step_s": float(data["meta"].sampling.fixed_step_s),
        "start_time_s": float(window.start_time_s),
        "end_time_exclusive_s": float(window.end_time_exclusive_s),
        "mat": str(output_mat.relative_to(ROOT)).replace("\\", "/"),
        "bytes": output_mat.stat().st_size,
    }


def main() -> None:
    model_dir = DESTINATION / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    stage_root = ROOT / "outputs" / "b_final" / "baseline_build" / "model_stages"
    for stage in STAGES:
        shutil.copy2(stage_root / stage / "dcac_inverter.slx", model_dir / f"{stage}.slx")

    runs = [export_case(scenario) for scenario in SCENARIOS]
    summary_root = ROOT / "outputs" / "b_final" / "baseline_build"
    summary_dir = DESTINATION / "summaries"
    summary_dir.mkdir(parents=True, exist_ok=True)
    study = json.loads((summary_root / "time_step_study_v1.json").read_text(encoding="utf-8"))
    for run in study["runs"]:
        run["result_path"] = f"outputs/reproduced/{run['run_id']}"
    (summary_dir / "time_step_study_v1.json").write_text(
        json.dumps(study, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with (summary_root / "time_step_runs_v1.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as source:
        reader = csv.DictReader(source)
        rows = list(reader)
        fieldnames = reader.fieldnames
    for row in rows:
        row["result_path"] = f"outputs/reproduced/{row['run_id']}"
    with (summary_dir / "time_step_runs_v1.csv").open(
        "w", encoding="utf-8", newline=""
    ) as destination:
        writer = csv.DictWriter(destination, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    shutil.copy2(
        summary_root / "time_step_comparison_v1.csv",
        summary_dir / "time_step_comparison_v1.csv",
    )

    index = {
        "schema_version": "dcac.electrical.github_artifacts/1.0",
        "data_origin": "real_interactive_matlab_simulation",
        "source_environment": "MATLAB R2023b Update 7",
        "window_policy": "one complete final 50 Hz period, full n400 sample rate, no decimation",
        "full_run_policy": (
            "The 0.24 s MAT files are intentionally excluded from Git. "
            "Regenerate them with the case request.json and dcac_execute.m."
        ),
        "runs": runs,
    }
    (DESTINATION / "artifact_index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
