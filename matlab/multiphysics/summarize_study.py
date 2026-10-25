"""Summarize persisted solver outputs without inventing missing results."""
from pathlib import Path
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def change(a, b):
    return 100 * abs(a - b) / abs(b)

def main():
    magnetic = read(OUT / "magnetic/metrics.json")
    unit = read(OUT / "unit_response/metrics.json")
    verification = read(OUT / "verification/metrics.json")
    assert verification["status"] == "passed"
    assert all(r["energy_identity_relative_error"] < 1e-8 for r in magnetic)
    assert all(r["heat_balance_relative_error"] < 0.01 for r in unit)
    electrical = []
    for steps in (100, 200, 400, 800, 1600):
        folder = "electrical_reference" + (f"_{steps}" if steps != 100 else "")
        r = read(OUT / folder / "handoff_local.json")
        assert r["ok"]
        electrical.append({"time_subdivisions": steps, "metrics": r["metrics"],
                           "full_run_peak_A": r["full_run_peak_A"], "folder": folder})
    candidate = read(OUT / "electrical_reference_400_candidate74/handoff_local.json")
    assert candidate["ok"]
    flux = read(OUT / "flux_linkage_check.json")
    ripple = read(OUT / "switching_ripple.json")
    bias = read(OUT / "vendor_bias_screen.json")
    thermal_copper = read(OUT / "thermal_copper_sensitivity.json")
    gap_sweep = read(OUT / "catalog_gap_turn_sweep.json")
    e70 = read(OUT / "e70_catalog_comparison.json")
    e70_unit = read(OUT / "unit_response_e70/metrics.json")
    e70_ripple = read(OUT / "e70_switching_ripple.json")
    e70_loss_budget = read(OUT / "e70_loss_budget.json")
    e70_combined = read(OUT / "e70_combined_scenarios/metrics.json")
    e70_combined_mesh = read(OUT / "e70_combined_scenarios/mesh_check.json")
    power_stress = [
        {"turns": turns, "report": read(OUT / f"electrical_reference_400_candidate{turns}_750W/handoff_local.json")}
        for turns in (74, 83)
    ]
    assert len(flux) == 3
    assert ripple["switching_periods_analyzed"] == 1600
    assert len(bias["candidates"]) == 3
    assert len(thermal_copper["scenarios"]) == 24
    assert len(e70["circuit_comparison"]) == 2
    assert len(e70_unit) == 4 and all(x["heat_balance_relative_error"] < 0.01 for x in e70_unit)
    assert len(e70_ripple) == 2 and e70_ripple[1]["switching_periods_analyzed"] == 1600
    assert e70_loss_budget["case_name"] == e70_ripple[1]["case_name"]
    assert len(e70_combined) == 2 and all(x["thermal_mesh_matching_verified"] and x["structural_mesh_matching_verified"] for x in e70_combined)
    assert e70_combined_mesh["peak_temperature_change_percent"] < 0.1
    assert e70_combined_mesh["max_displacement_change_percent"] < 1
    assert e70_combined_mesh["probe_stress_change_percent"] < 1
    assert all(x["report"]["ok"] and x["report"]["spec"]["output_power"] == 750 for x in power_stress)
    candidate_flux = flux[2]
    assert candidate_flux["case_name"] == "electrical_reference_400_candidate74"
    assert abs(candidate_flux["L_circuit_H"] / magnetic[2]["L_energy_H"] - 1) < 1e-10
    turns = magnetic[2]["turns"]
    assert turns == candidate_flux["turns_only_for_candidate"]
    winding = read(ROOT / "material_assumptions.json")["winding_screening"]
    ae_m2 = winding["catalog_effective_core_area_m2"]
    window_m2 = winding["catalog_winding_window_area_m2"]
    wire_d_m = winding["bare_wire_diameter_m"]
    copper_rho_20_ohm_m = winding["copper_resistivity_20C_ohm_m"]
    mu0_h_m = 4 * math.pi * 1e-7
    fsw_hz = candidate["spec"]["switching_frequency"]
    peak_a = candidate["metrics"]["inductor_peak"]
    assert abs(peak_a - candidate["full_run_peak_A"]) / peak_a < 0.001
    candidate_screening = {
        "status": "conditional_linear_screening_not_saturation_or_loss_validation",
        "ae_catalog_m2": ae_m2,
        "candidate_lambda_peak_Wb_turn": candidate_flux["lambda_state_peak_Wb_turn"],
        "candidate_B_average_from_Li_over_NAe_T": candidate_flux["candidate_flux_peak_Wb"] / ae_m2,
        "candidate_B_bulk_linear_FE_at_peak_T": magnetic[2]["bulk_center_leg_B_T"] * peak_a,
        "bare_copper_window_fill_fraction": turns * math.pi * (wire_d_m / 2)**2 / window_m2,
        "skin_depth_20kHz_20C_mm": 1000 * math.sqrt(copper_rho_20_ohm_m / (math.pi * fsw_hz * mu0_h_m)),
        "wire_radius_mm": 1000 * wire_d_m / 2,
        "copper_only_peak_rise_K_at_h10_fixed_DC_loss": candidate["metrics"]["winding_loss"] * unit[1]["peak_temperature_rise_K_per_W"],
        "copper_only_peak_rise_status": "assumed geometry, fixed DC R, zero core/AC loss; not actual operating temperature",
        "flux_integral_rmse_percent_of_peak_at_400steps": candidate_flux["lambda_reconstruction_rmse_percent_of_peak"],
        "flux_integral_rmse_percent_of_peak_at_800steps_baseline": flux[1]["lambda_reconstruction_rmse_percent_of_peak"],
        "flux_integral_method_note": "trapezoidal samples miss PWM switching events; cross-step residual must not be interpreted as physical core loss",
    }
    summary = {
        "schema_version": "c-study-summary/0.1",
        "date": "2026-10-23",
        "status": "candidate_study_not_final_component_validation",
        "electrical": electrical,
        "candidate_electrical": {"spec": candidate["spec"], "metrics": candidate["metrics"],
                                 "full_run_peak_A": candidate["full_run_peak_A"]},
        "flux_linkage_checks": flux,
        "switching_ripple": ripple,
        "waveform_harmonic_audit": read(OUT / 'waveform_audit/metrics.json'),
        "vendor_dc_bias_screen": bias,
        "power_stress_750W": power_stress,
        "thermal_copper_sensitivity": thermal_copper,
        "catalog_gap_turn_sweep": gap_sweep,
        "e70_catalog_comparison": e70,
        "e70_unit_thermal_structural_response": e70_unit,
        "e70_switching_ripple": e70_ripple,
        "e70_conditional_loss_temperature_frontier": e70_loss_budget,
        "e70_combined_thermal_structural_scenarios": e70_combined,
        "e70_combined_mesh_check": e70_combined_mesh,
        "e70_unit_winding_h10_mesh_peak_change_percent": change(e70_unit[0]["peak_temperature_rise_K_per_W"],e70_unit[1]["peak_temperature_rise_K_per_W"]),
        "candidate_screening": candidate_screening,
        "electrical_last_refinement_changes_percent": {
            key: change(electrical[-2]["metrics"][key], electrical[-1]["metrics"][key])
            for key in ("output_rms", "inductor_rms", "inductor_peak", "winding_loss", "thd_percent")
        },
        "thd_last_refinement_percentage_point_change": abs(electrical[-2]["metrics"]["thd_percent"] - electrical[-1]["metrics"]["thd_percent"]),
        "magnetic_mesh_L_change_percent": change(magnetic[1]["L_energy_H"], magnetic[2]["L_energy_H"]),
        "magnetic_air_domain_L_change_percent": change(magnetic[2]["L_energy_H"], magnetic[3]["L_energy_H"]),
        "catalog_vs_2D_L_difference_percent": change(magnetic[2]["L_energy_H"], 364e-9 * 74**2),
        "thermal_mesh_T_change_percent": change(unit[1]["peak_temperature_rise_K_per_W"],unit[6]["peak_temperature_rise_K_per_W"]),
        "structural_mesh_displacement_change_percent": change(unit[1]["max_displacement_m_per_W"],unit[6]["max_displacement_m_per_W"]),
        "cooling_h10_to_h15_peak_reduction_percent": 100*(1-unit[4]["peak_temperature_rise_K_per_W"]/unit[1]["peak_temperature_rise_K_per_W"]),
        "verification": verification,
        "not_computed": {"core_loss_W": None, "total_winding_AC_loss_W": None,
                         "actual_operating_temperature_C": None, "saturation_margin": None,
                         "strength_safety_factor": None},
    }
    (OUT / "study_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    inputs = list(ROOT.glob("*.m")) + list(ROOT.glob("*.py")) + list(ROOT.glob("*.md")) + [ROOT / "material_assumptions.json"]
    inputs += list((ROOT / "source_snapshot").glob("*.m")) + list((ROOT / "compatibility").glob("*.m"))
    artifacts = list(OUT.rglob("*.mat")) + list(OUT.rglob("*.json")) + list(OUT.rglob("*.slx")) + list(OUT.rglob("*.png"))
    records=[]
    for path in sorted(inputs + artifacts):
        if path.name == "c_study_manifest.json":
            continue
        digest=hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024*1024),b""):
                digest.update(block)
        records.append({"path":path.relative_to(ROOT).as_posix(),"bytes":path.stat().st_size,"sha256":digest.hexdigest()})
    manifest={"schema_version":"c-study-manifest/0.1", "not_shared_A_contract":True,
              "matlab_release":"R2023b Update 7", "source_blob_sha":"95e8af6ae07d6abdb75505c292cc45e3bc754c62", "files":records}
    (OUT / "c_study_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in summary.items() if k not in ("electrical","candidate_electrical","flux_linkage_checks","vendor_dc_bias_screen","power_stress_750W","thermal_copper_sensitivity","catalog_gap_turn_sweep","e70_catalog_comparison","e70_unit_thermal_structural_response","e70_switching_ripple","e70_conditional_loss_temperature_frontier","e70_combined_thermal_structural_scenarios")},ensure_ascii=False,indent=2))

if __name__ == "__main__":
    main()
