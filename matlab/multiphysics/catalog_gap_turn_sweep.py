"""Catalog-only gap/turn screening for 2 mH E55/N87 candidates.

This does not replace calibrated 3-D nonlinear FEA or a winding build.
"""
from pathlib import Path
import json
import math

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
CORE_URL = "https://www.tdk-electronics.tdk.com/inf/80/db/fer/e_55_28_21.pdf"
GENERAL_URL = "https://www.tdk-electronics.tdk.com/download/540150/449506bb84194c3510018ae82f66b4cc/pdf-ecoresgeneralinformation.pdf"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    w = read(ROOT / "material_assumptions.json")["winding_screening"]
    high = read(OUT / "electrical_reference_400_candidate83_750W/handoff_local.json")
    unit = read(OUT / "unit_response/metrics.json")
    i_peak = high["full_run_peak_A"]
    i_rms = high["metrics"]["inductor_rms"]
    area = math.pi * (w["bare_wire_diameter_m"] / 2)**2
    theta15 = unit[4]["peak_temperature_rise_K_per_W"]
    rows = []
    for step in range(16, 70):  # 0.80 ... 3.45 mm, inside catalog gap range
        gap_mm = step * 0.05
        al_nh = 496 * gap_mm**(-0.764)
        if not (180 < al_nh < 1799):
            continue
        n = round(math.sqrt(2e6 / al_nh))
        l_mh = n*n*al_nh / 1e6
        if abs(l_mh/2 - 1) > 0.02:
            continue
        r20 = w["copper_resistivity_20C_ohm_m"] * n*w["mean_turn_length_m"]/area
        p20_proxy = i_rms*i_rms*r20
        i_hot = (100/n) * (0.9*al_nh/765)**(1/-0.873)
        # Fixed-current, winding-only, 40 C ambient, h=15 scenario.
        alpha = 0.00393
        p_hot = p20_proxy*(1+alpha*20)/(1-alpha*theta15*p20_proxy)
        t_hot = 40+theta15*p_hot
        rows.append({
            "gap_mm": round(gap_mm, 3), "turns": n,
            "nominal_catalog_AL_nH": al_nh,
            "nominal_catalog_L_mH": l_mh,
            "nominal_100C_DC_10pct_AL_drop_A": i_hot,
            "ratio_of_750W_83turn_peak_to_DC_threshold": i_peak/i_hot,
            "bare_copper_fill_fraction": n*area/w["catalog_winding_window_area_m2"],
            "ideal_R20_ohm": r20,
            "copper_only_750W_40C_h15_hotspot_C_proxy": t_hot,
        })
    assert rows
    best = max(rows, key=lambda x: x["nominal_100C_DC_10pct_AL_drop_A"])
    result = {
        "schema_version": "c-catalog-gap-turn-sweep/0.1",
        "status": "catalog_analytical_screen_not_FE_or_component_design",
        "target_nominal_catalog_L_mH": 2.0,
        "catalog_L_tolerance_for_sweep_percent": 2,
        "gap_grid_mm": "0.80 to 3.45, 0.05 step",
        "vendor_gap_validity_mm": "0.15 < gap < 3.50",
        "vendor_AL_validity_nH": "180 < AL < 1799",
        "comparison_peak_A": i_peak,
        "comparison_peak_source": "83-turn 750 W ideal circuit; other designs would change the peak",
        "optional_screening_margin_percent": 20,
        "optional_20pct_margin_target_A": 1.2*i_peak,
        "maximum_nominal_hot_DC_threshold_on_grid_A": best["nominal_100C_DC_10pct_AL_drop_A"],
        "best_threshold_grid_case": best,
        "any_case_reaches_optional_20pct_margin": any(
            row["nominal_100C_DC_10pct_AL_drop_A"] >= 1.2*i_peak for row in rows),
        "any_case_below_100C_copper_only_proxy_and_above_comparison_peak": any(
            row["copper_only_750W_40C_h15_hotspot_C_proxy"] < 100
            and row["nominal_100C_DC_10pct_AL_drop_A"] > i_peak for row in rows),
        "sources": [CORE_URL, GENERAL_URL],
        "limitations": [
            "AL(g) is nominal catalog formula, while 2D FE disagrees increasingly at large gaps",
            "DC 10% AL-drop criterion is not an AC saturation rating",
            "750 W current taken from the 83-turn circuit, not rerun for each sweep case",
            "40 C thermal proxy uses an assumed bonded 2D assembly and fixed RMS current",
            "actual insulated wire fit, leakage/fringing and AC/core losses remain unknown",
        ],
        "cases": rows,
    }
    (OUT / "catalog_gap_turn_sweep.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in rows:
        if r["gap_mm"] in (1,1.5,2,2.5,3,3.4):
            print(r["gap_mm"],r["turns"],round(r["nominal_100C_DC_10pct_AL_drop_A"],2),
                  round(r["copper_only_750W_40C_h15_hotspot_C_proxy"],1))
    print("max",best["gap_mm"],best["turns"],
          round(result["maximum_nominal_hot_DC_threshold_on_grid_A"],2))


if __name__ == "__main__":
    main()
