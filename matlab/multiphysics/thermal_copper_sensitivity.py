"""Copper-only lumped feedback sensitivity using the assumed unit heat response.

This holds the simulated RMS current fixed and omits core/AC winding losses.
It is an input scenario for the next coupled analysis, not an operating rating.
"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
NIST_URL = "https://nvlpubs.nist.gov/nistpubs/Legacy/hb/nbshandbook100.pdf"
ALPHA_20_PER_K = 0.00393


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    units = read(OUT / "unit_response/metrics.json")
    e70_units = read(OUT / "unit_response_e70/metrics.json")
    theta_by_core = {
        "E55": {10: units[1]["peak_temperature_rise_K_per_W"],
                 15: units[4]["peak_temperature_rise_K_per_W"]},
        "E70": {10: e70_units[1]["peak_temperature_rise_K_per_W"],
                 15: e70_units[3]["peak_temperature_rise_K_per_W"]},
    }
    assert all(x["heat_balance_relative_error"] < 0.01 for x in e70_units)
    rows = []
    cases = [("E55", turns, watts,
              f"candidate{turns}" + ("_750W" if watts == 750 else ""))
             for turns in (74,83) for watts in (500,750)]
    cases += [("E70",68,500,"E70FE68_500W"),
              ("E70",68,750,"E70FE68_750W")]
    for core, turns, nominal_w, suffix in cases:
        report = read(OUT / f"electrical_reference_400_{suffix}/handoff_local.json")
        assert report["ok"]
        p20 = report["metrics"]["winding_loss"]
        for ambient_c in (25, 40):
            for h in (10, 15):
                th = theta_by_core[core][h]
                loop_gain = ALPHA_20_PER_K * th * p20
                assert loop_gain < 1
                p_hot = p20 * (1 + ALPHA_20_PER_K * (ambient_c - 20)) / (1 - loop_gain)
                rise = th * p_hot
                rows.append({
                    "core_family": core,
                    "electrical_case_tag": suffix,
                    "turns": turns,
                    "nominal_output_power_W": nominal_w,
                    "ambient_C": ambient_c,
                    "assumed_h_W_m2K": h,
                    "R20_fixed_model_loss_W": p20,
                    "assumed_copper_only_hot_loss_W": p_hot,
                    "assumed_copper_only_hotspot_rise_K": rise,
                    "assumed_copper_only_hotspot_C": ambient_c + rise,
                    "feedback_loop_gain": loop_gain,
                })
    result = {
        "schema_version": "c-copper-thermal-sensitivity/0.1",
        "status": "conditional_fixed_current_copper_only_scenario_not_actual_temperature",
        "equation": "P_hot=P20*(1+alpha20*(Tamb-20))/(1-alpha20*theta_peak*P20); T_hot=Tamb+theta_peak*P_hot",
        "alpha20_1_K": ALPHA_20_PER_K,
        "alpha_source": NIST_URL,
        "limitations": [
            "RMS current held fixed although actual circuit would respond to changing resistance",
            "hotspot rise applied to uniform copper R, a one-node approximation",
            "assumed bonded geometry, adiabatic front/back, h only at outer perimeter",
            "core loss, AC copper loss, contact resistance and varying material properties absent",
        ],
        "scenarios": rows,
    }
    # Hypothetical extra loss placed entirely in the winding pack.
    # This is a sensitivity target for measuring AC/core loss, not an actual allowance.
    e70_p20 = next(row["R20_fixed_model_loss_W"] for row in rows
                   if row["core_family"] == "E70" and row["nominal_output_power_W"] == 750)
    result["E70_750W_40C_extra_winding_heat_budget_to_100C_W"] = {
        str(h): 60*(1-ALPHA_20_PER_K*th*e70_p20)/th
                -e70_p20*(1+ALPHA_20_PER_K*20)
        for h, th in theta_by_core["E70"].items()
    }
    result["extra_heat_budget_note"] = (
        "All unknown extra heat hypothetically placed in winding pack; "
        "100C target is a scenario, not an actual component rating or measured loss")
    (OUT / "thermal_copper_sensitivity.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for row in rows:
        if row["ambient_C"] == 40 and row["assumed_h_W_m2K"] == 10:
            print(row["core_family"],row["turns"], row["nominal_output_power_W"],
                  round(row["assumed_copper_only_hotspot_C"], 2))


if __name__ == "__main__":
    main()
