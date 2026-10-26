"""Three meshes at identical excitation, followed by nine prescribed-heat cases."""
import argparse
import hashlib
import json
import shutil
import sys
import threading
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dcac_agent.runtime import MatlabRuntime
from dcac_agent.multiphysics import digest,write_json


def metrics(result):
    d=result['domains']
    return dict(L_H=d['magnetic']['metrics']['candidate_inductance']['value'],
        B_T=d['magnetic']['metrics']['bulk_peak_flux_density']['value'],
        temperature_rise_K=d['thermal']['metrics']['peak_temperature']['value']-result['input_summary']['options']['ambient_c'],
        displacement_m=d['structural']['metrics']['max_displacement']['value'],
        probe_stress_Pa=d['structural']['metrics']['core_probe_tensile_stress']['value'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matlab',required=True)
    args=parser.parse_args()
    study=ROOT/'outputs/field_acceptance_20261026';study.mkdir(parents=True,exist_ok=True)
    lr=json.loads((ROOT/'outputs/lr_alignment_20261026/iteration.json').read_text(encoding='utf-8'))
    case=lr['scenarios']['rated'];run=case['candidate']['run']
    parent=ROOT/'outputs/lr_alignment_20261026/runs'/case['session_id']/run['id']
    hashes={name:digest(parent/name) for name in ('result.json','electrical_raw_v1.mat')}
    assert hashes==run['source_sha256']
    source_root=ROOT/'matlab/multiphysics'
    sources=[source_root/name for name in ('dcac_multiphysics.m','dcac_field_mesh.m','solve_magnetic_e70.m',
        'solve_unit_e70_thermal_structural.m','plane_stress_cte_adapter.m','verify_plane_stress_backend.m')]
    source_hashes={p.name:digest(p) for p in sources}
    fingerprint=hashlib.sha256(b''.join(p.name.encode()+p.read_bytes() for p in sorted(sources))).hexdigest()
    runtime=MatlabRuntime(dict(matlab_executable=args.matlab,matlab_timeout_seconds=7200))
    report=dict(status='running',source_run_id=run['id'],source_session_id=case['session_id'],source_sha256=hashes,
        solver_source_sha256=fingerprint,solver_files_sha256=source_hashes,
        criteria_percent=dict(L_H=2,B_T=2,temperature_rise_K=2,displacement_m=2,probe_stress_Pa=5),meshes=[])
    def emit(*args): pass
    for label,hmax in [('coarse',.003),('medium',.002),('fine',.001)]:
        folder=study/label;folder.mkdir(exist_ok=True)
        q=dict(session_id=case['session_id'],parent_run_id=run['id'],revision=run['revision'],spec=run['spec'],
            parent_dir=parent.as_posix(),options=case['candidate']['fields']['input_summary']['options'],
            source_sha256=hashes,mesh=dict(magnetic_hmax_m=hmax,thermal_hmax_m=hmax))
        receipt=dict(request=q,solver_source_sha256=fingerprint)
        receipt_path=folder/'receipt.json'
        cached=receipt_path.exists() and json.loads(receipt_path.read_text(encoding='utf-8')).get('request')==q
        cached=cached and all((folder/name).is_file() and digest(folder/name)==sha for name,sha in source_hashes.items())
        if cached and (folder/'result.json').exists():
            result=json.loads((folder/'result.json').read_text(encoding='utf-8-sig'))
            cached=result.get('ok') is True and (folder/'fields.mat').exists()
        if not cached:
            for source in sources: shutil.copy2(source,folder/source.name)
            write_json(folder/'field_request.json',q);write_json(receipt_path,receipt)
            print(f'BEGIN mesh {label}: {hmax*1000:g} mm',flush=True)
            result=runtime.execute_fields(folder,threading.Event(),emit)
        assert result['status']=='completed'
        report['meshes'].append(dict(label=label,hmax_m=hmax,metrics=metrics(result),
            input=result['input_summary'],verification=result['verification'],
            corner_max_stress_Pa=result['domains']['structural']['metrics']['corner_sensitive_max_tensile_stress']['value']))
        write_json(study/'summary.json',report)
        print(f'DONE mesh {label}: '+json.dumps(metrics(result)),flush=True)
    report['comparisons']=[]
    for coarse,fine in zip(report['meshes'][:-1],report['meshes'][1:]):
        errors={k:100*abs(coarse['metrics'][k]-fine['metrics'][k])/abs(fine['metrics'][k]) for k in report['criteria_percent']}
        report['comparisons'].append(dict(pair=[coarse['label'],fine['label']],errors_percent=errors,
            passed=all(errors[k]<v for k,v in report['criteria_percent'].items())))
    report['mesh_passed']=report['comparisons'][-1]['passed']
    # Reuse the finest solved basis. This is not nine independent FE solves.
    fine=study/'fine';sensitivity=study/'sensitivity';sensitivity.mkdir(exist_ok=True)
    shutil.copy2(source_root/'dcac_heat_sensitivity.m',fine/'dcac_heat_sensitivity.m')
    report['sensitivity_source_sha256']=digest(source_root/'dcac_heat_sensitivity.m')
    quote=lambda p:p.as_posix().replace("'","''")
    expression=f"addpath('{quote(fine)}'); dcac_heat_sensitivity('{quote(fine/'fields.mat')}','{quote(sensitivity)}');"
    runtime._batch(expression,sensitivity,threading.Event(),emit,'sensitivity')
    report['sensitivity']=json.loads((sensitivity/'sensitivity.json').read_text(encoding='utf-8'))
    assert all(digest(parent/k)==v for k,v in hashes.items())
    report['status']='completed' if report['mesh_passed'] else 'mesh_threshold_not_met'
    write_json(study/'summary.json',report)
    print('FIELD_ACCEPTANCE '+report['status'],flush=True)


if __name__=='__main__':main()
