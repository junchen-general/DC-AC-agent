"""Conditional E70 750 W loss/temperature frontier from unit FE responses.

The sum of separate source maxima bounds the peak of their linear thermal
superposition. All losses and thermal boundaries remain candidate assumptions.
"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
ALPHA = 0.00393
AMBIENT_C = 40.0
SCENARIO_LIMIT_C = 100.0


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def temperature(p20, theta_w, theta_c, p_ac, p_core):
    gain = ALPHA * theta_w * p20
    assert gain < 1
    rise = (theta_w * (p20 * (1 + ALPHA * (AMBIENT_C - 20)) + p_ac)
            + theta_c * p_core) / (1 - gain)
    return AMBIENT_C + rise


def main():
    electrical = read(OUT / "electrical_reference_400_E70FE68_750W/handoff_local.json")
    unit = read(OUT / "unit_response_e70/metrics.json")
    ripple = read(OUT / "e70_switching_ripple.json")
    assert electrical["ok"] and len(unit) == 4 and len(ripple) == 2
    assert unit[1]["source"] == "winding" and unit[2]["source"] == "core"
    assert unit[1]["h_W_m2K"] == unit[2]["h_W_m2K"] == 10
    assert unit[1]["hmax_m"] == unit[2]["hmax_m"]
    p20 = electrical["metrics"]["winding_loss"]
    tw = unit[1]["peak_temperature_rise_K_per_W"]
    tc = unit[2]["peak_temperature_rise_K_per_W"]
    dc_at_limit = p20 * (1 + ALPHA * (SCENARIO_LIMIT_C - 20))
    remaining_K = SCENARIO_LIMIT_C - AMBIENT_C - tw * dc_at_limit
    winding_intercept = remaining_K / tw
    core_intercept = remaining_K / tc
    assert winding_intercept > 0 and core_intercept > 0
    rows = []
    for p_core in (0, .25, .5, 1.0, 1.25):
        rows.append({
            "assumed_core_loss_W": p_core,
            "remaining_AC_winding_loss_for_100C_scenario_W": (remaining_K - tc*p_core)/tw,
            "modeled_hotspot_C_if_AC_winding_loss_0p5W": temperature(p20, tw, tc, .5, p_core),
        })
    result = {
        "schema_version": "c-e70-loss-frontier/0.1",
        "status": "conditional_h10_linear_FE_temperature_frontier_not_loss_prediction_or_rating",
        "case_name": ripple[1]["case_name"],
        "ambient_C": AMBIENT_C,
        "scenario_hotspot_limit_C": SCENARIO_LIMIT_C,
        "assumed_h_W_m2K": 10,
        "R20_fixed_current_loss_W": p20,
        "copper_resistance_alpha20_1_K": ALPHA,
        "winding_source_peak_K_per_W": tw,
        "core_source_peak_K_per_W": tc,
        "copper_DC_loss_at_100C_under_fixed_RMS_current_W": dc_at_limit,
        "copper_only_hotspot_C": temperature(p20, tw, tc, 0, 0),
        "additional_AC_winding_loss_intercept_W": winding_intercept,
        "core_loss_intercept_W": core_intercept,
        "frontier": "theta_w*P_ac_winding + theta_c*P_core <= Tlimit-Tambient-theta_w*Pdc(Tlimit)",
        "rows": rows,
        "ripple_B_pp_p95_linear_proxy_T": ripple[1]["B_pp_p95_T"],
        "limitations": [
            "P_core and P_ac are unknown; output is a thermal measurement target, not estimated losses",
            "Fixed RMS current and uniform copper temperature feedback; changing R is not fed back into circuit",
            "Unit source maxima are added as a sufficient upper-bound test for linear thermal FE, not a solved two-source field",
            "Assumed bonded winding pack, adiabatic faces and perimeter h=10; no actual mounting or contact resistance",
            "100C is an illustrative scenario limit, not a verified part rating",
            "Ripple B is a linear envelope, not a measured minor loop or core loss",
        ],
    }
    (OUT / "e70_loss_budget.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"At h=10: core-only intercept {core_intercept:.3f} W; AC-winding-only intercept {winding_intercept:.3f} W")


if __name__ == "__main__":
    main()
