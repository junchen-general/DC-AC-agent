"""Apply TDK's nominal E-core DC-bias 10% AL-drop formula as a screen.

The circuit waveform is AC, so this does not establish saturation or actual L(i,T).
"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
CORE_URL = "https://www.tdk-electronics.tdk.com/inf/80/db/fer/e_55_28_21.pdf"
GENERAL_URL = "https://www.tdk-electronics.tdk.com/download/540150/449506bb84194c3510018ae82f66b4cc/pdf-ecoresgeneralinformation.pdf"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def screen():
    magnetic = read(OUT / "magnetic/metrics.json")
    # E55/28/21 N87 nominal AL, valid formula range 180--1799 nH.
    vendor_al_nh = {64: 496, 74: 364, 83: 292}
    vendor_gap_m = {64: 0.001, 74: 0.0015, 83: 0.002}
    k = {"25C": (800, -0.796), "100C": (765, -0.873)}
    rows = []
    for item in magnetic:
        n = item["turns"]
        if (n not in vendor_al_nh or item["gap_m"] != vendor_gap_m[n]
                or item["hmax_m"] != 0.0012 or item["air_half_size_m"] != 0.1):
            continue
        folder = OUT / f"electrical_reference_400_candidate{n}"
        circuit = read(folder / "handoff_local.json")
        assert circuit["ok"]
        assert abs(circuit["spec"]["inductance"] / item["L_energy_H"] - 1) < 1e-10
        al = vendor_al_nh[n]
        thresholds = {
            temp: (100 / n) * (0.9 * al / k3) ** (1 / k4)
            for temp, (k3, k4) in k.items()
        }
        peak = circuit["full_run_peak_A"]
        rows.append({
            "turns": n,
            "gap_mm": 1000 * item["gap_m"],
            "vendor_nominal_AL_nH": al,
            "two_D_FE_L_mH": 1000 * item["L_energy_H"],
            "ideal_circuit_full_run_current_peak_A": peak,
            "vendor_10pct_AL_drop_DC_bias_current_25C_A": thresholds["25C"],
            "vendor_10pct_AL_drop_DC_bias_current_100C_A": thresholds["100C"],
            "peak_over_100C_DC_bias_threshold_ratio": peak / thresholds["100C"],
            "note": "AC crest compared to nominal DC-bias criterion as a warning only; no validated hot nonlinear L(i,T)",
        })
    assert len(rows) == 3
    rows.sort(key=lambda row: row["turns"])
    result = {
        "schema_version": "c-vendor-dc-bias-screen/0.1",
        "status": "screening_warning_not_component_rating",
        "formula": "I_10pct_for_N_turns = (100/N) * (0.9*AL_nH/K3) ** (1/K4)",
        "vendor_measurement": "N=100, 10 kHz, B<=0.25 mT, zero-bias AL at 25C; 10% AL drop under DC bias",
        "temperature_rule": "Use 25C zero-bias AL also with 100C K3/K4",
        "sources": [CORE_URL, GENERAL_URL],
        "limitations": [
            "50 Hz AC with 20 kHz ripple is not the specified DC-bias test",
            "catalog AL is nominal and is 6.6% above 74-turn 2D FE AL-equivalent",
            "actual part geometry, thermal state and hot incremental inductance are unknown",
        ],
        "candidates": rows,
    }
    (OUT / "vendor_bias_screen.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    for row in screen()["candidates"]:
        print(row["turns"], row["ideal_circuit_full_run_current_peak_A"],
              row["vendor_10pct_AL_drop_DC_bias_current_100C_A"],
              row["peak_over_100C_DC_bias_threshold_ratio"])
