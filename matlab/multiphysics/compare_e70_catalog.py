"""Compare E70 catalog candidate with E55 83-turn reference at 500/750 W.

The catalog circuit uses AL*N²; independent linear 2D magnetic and unit thermal FE
provide candidate cross-checks, not hardware validation.
"""
from pathlib import Path
import json
import math

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
E70_URL = "https://www.tdk-electronics.tdk.com/inf/80/db/fer/e_70_33_32.pdf"
GENERAL_URL = "https://www.tdk-electronics.tdk.com/download/540150/449506bb84194c3510018ae82f66b4cc/pdf-ecoresgeneralinformation.pdf"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    assumption = read(ROOT / "material_assumptions.json")
    e = assumption["e70_alternative_screening"]
    cu = assumption["winding_screening"]
    al = e["catalog_AL_nH"]
    n = e["turns"]
    l = al*1e-9*n*n
    a_wire = math.pi*(e["assumed_equal_copper_area_solid_wire_diameter_m"]/2)**2
    a_strands = e["selected_strand_count"] * math.pi * (e["selected_strand_bare_diameter_m"]/2)**2
    assert abs(a_strands/a_wire-1) < 1e-12
    r20 = cu["copper_resistivity_20C_ohm_m"]*n*e["catalog_mean_turn_length_m"]/a_wire
    threshold_hot = (100/n)*(0.9*al/1438)**(1/-0.873)
    threshold_cold = (100/n)*(0.9*al/1485)**(1/-0.796)
    fe = read(OUT / "magnetic_e70/metrics.json")
    fe_run = read(OUT / "electrical_reference_400_E70FE68_750W/handoff_local.json")
    assert len(fe) == 2 and fe_run["ok"]
    assert all(x["energy_identity_relative_error"] < 1e-8 for x in fe)
    assert abs(fe_run["spec"]["inductance"]/fe[1]["L_energy_H"] - 1) < 1e-12
    rows = []
    for nominal_w in (500,750):
        e70 = read(OUT / f"electrical_reference_400_E70catalog68_{nominal_w}W/handoff_local.json")
        e55_tag = "candidate83" + ("_750W" if nominal_w == 750 else "")
        e55 = read(OUT / f"electrical_reference_400_{e55_tag}/handoff_local.json")
        assert e70["ok"] and e55["ok"]
        assert abs(e70["spec"]["inductance"]/l-1) < 1e-12
        assert abs(e70["spec"]["winding_resistance"]/r20-1) < 1e-12
        rows.append({
            "nominal_output_power_W": nominal_w,
            "E70_catalog_candidate_peak_A": e70["full_run_peak_A"],
            "E70_catalog_candidate_R20_ohmic_loss_W": e70["metrics"]["winding_loss"],
            "E70_peak_over_100C_DC_threshold_ratio": e70["full_run_peak_A"]/threshold_hot,
            "E70_catalog_B_average_at_peak_T": l*e70["full_run_peak_A"]/(n*e["catalog_Ae_m2"]),
            "E55_83turn_FE_candidate_peak_A": e55["full_run_peak_A"],
            "E55_83turn_R20_ohmic_loss_W": e55["metrics"]["winding_loss"],
        })
    result = {
        "schema_version": "c-e70-catalog-comparison/0.1",
        "status": "catalog_and_linear_2D_FE_candidate_screen_not_hardware_validation",
        "E70_N87_core": "E70/33/32, one 2.5 mm gapped half plus one ungapped half",
        "E70_nominal_catalog_L_H": l,
        "E70_assumed_R20_ohm": r20,
        "E70_bare_copper_fill_fraction": n*a_wire/e["catalog_winding_window_area_m2"],
        "E70_winding_bundle_window_fraction": n*math.pi*(e["winding_bundle_envelope_diameter_m_for_window_screen"]/2)**2/e["catalog_winding_window_area_m2"],
        "E70_selected_64strand_copper_area_m2": a_strands,
        "E70_vendor_DC_10pct_AL_drop_25C_A": threshold_cold,
        "E70_vendor_DC_10pct_AL_drop_100C_A": threshold_hot,
        "E70_catalog_Ae_m2": e["catalog_Ae_m2"],
        "E70_2D_FE": {
            "mesh_nodes_coarse_fine": [fe[0]["nodes"],fe[1]["nodes"]],
            "L_coarse_fine_mH": [1000*fe[0]["L_energy_H"],1000*fe[1]["L_energy_H"]],
            "mesh_change_percent": 100*abs(fe[0]["L_energy_H"]/fe[1]["L_energy_H"]-1),
            "fine_FE_vs_catalog_L_difference_percent": 100*abs(fe[1]["L_energy_H"]/l-1),
            "bulk_center_leg_B_per_A_T_per_A": fe[1]["bulk_center_leg_B_T"],
            "full_run_750W_current_peak_A": fe_run["full_run_peak_A"],
            "full_run_750W_fixed_R20_loss_W": fe_run["metrics"]["winding_loss"],
            "full_run_750W_peak_over_vendor_100C_DC_threshold": fe_run["full_run_peak_A"]/threshold_hot,
            "bulk_center_leg_B_at_750W_peak_T": fe[1]["bulk_center_leg_B_T"]*fe_run["full_run_peak_A"],
            "model_note": "Rectangularized 2D linear section from TDK dimensions; centered gap and assumed winding blocks; not calibrated 3D nonlinear hardware",
        },
        "core_set_mass_g_E70_vs_E55": [514,215],
        "sources": [E70_URL,GENERAL_URL],
        "limitations": [
            "Catalog comparison mixes E70 catalog AL with E55 simplified 2D FE; a separate E70 2D FE circuit recheck is included",
            "E70 winding uses assumed equivalent 1.2 mm solid copper area; no insulation or winding layout verification",
            "DC-bias 10% AL-drop point cannot establish 50 Hz AC plus 20 kHz ripple nonlinear behavior",
            "E70 magnetic and unit thermal-structural FE are 2D linear assumed models; AC winding/core loss and real assembly validation remain unavailable",
        ],
        "circuit_comparison": rows,
    }
    (OUT / "e70_catalog_comparison.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for row in rows:
        print(row["nominal_output_power_W"],round(row["E70_catalog_candidate_peak_A"],3),
              round(row["E70_catalog_candidate_R20_ohmic_loss_W"],3),
              round(row["E70_peak_over_100C_DC_threshold_ratio"],3))


if __name__ == "__main__":
    main()
