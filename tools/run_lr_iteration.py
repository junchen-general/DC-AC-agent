"""Explicit cold-L/R revision study, using real solvers and immutable run folders.

Run with Python >=3.10 from the repository root. Default coarse/fine pairs
follow B's existing resolution evidence, but every new pair is recomputed.
"""
import argparse
import hashlib
import json
import shutil
import sys
import threading
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dcac_agent.store import Store,now
from dcac_agent.runtime import MatlabRuntime
from dcac_agent.multiphysics import execute_multiphysics,digest,write_json
from dcac_agent.contracts import write_manifest,read_multiphysics
from dcac_agent.candidate_revision import apply_candidate_revision


def compare(a,b):
    criteria={'output_rms':.2,'inductor_rms':.5,'inductor_peak':1.0}
    errors={k:100*abs(a[k]-b[k])/max(abs(b[k]),sys.float_info.epsilon) for k in criteria}
    errors['thd_percentage_points']=abs(a['thd_percent']-b['thd_percent'])
    return dict(errors=errors,converged=all(errors[k]<v for k,v in criteria.items())
                and errors['thd_percentage_points']<.1,
                criteria={**criteria,'thd_percentage_points':.1})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matlab',required=True)
    parser.add_argument('--study',default='lr_alignment_20261026')
    parser.add_argument('--scenarios',nargs='+',choices=['rated','half_load','rated_to_half'],
                        default=['rated','half_load','rated_to_half'])
    args=parser.parse_args()
    if not args.study.replace('_','').isalnum(): raise ValueError('Study name must be alphanumeric/underscore')
    root=ROOT/'outputs'/args.study; root.mkdir(parents=True,exist_ok=True)
    store=Store(root/'store'); outputs=root/'runs'
    runtime=MatlabRuntime(dict(matlab_executable=args.matlab,matlab_timeout_seconds=7200))
    cancel=threading.Event()
    fingerprint=hashlib.sha256()
    for p in sorted(list((ROOT/'matlab').rglob('*.m'))+[ROOT/'matlab/multiphysics/material_assumptions.json']):
        fingerprint.update(p.relative_to(ROOT).as_posix().encode());fingerprint.update(p.read_bytes())
    source=fingerprint.hexdigest()
    state_path=root/'iteration.json'
    state=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else dict(
        schema_version='dcac.lr-iteration/1.0',created_at=now(),solver_source_sha256=source,
        resistance_basis='cold_R20',resistance_reference_temperature_c=20,scenarios={})
    if state['solver_source_sha256']!=source: raise ValueError('Solver changed: use a new study name')
    state['status']='running'
    def persist(): write_json(state_path,state)
    def emit(kind,title,data=None): print(title,flush=True)
    def manifest(folder,sid,run):
        data=write_manifest(folder,sid,run,'MATLAB/Simulink')
        request=json.loads((folder/'request.json').read_text(encoding='utf-8'))
        data['electrical']=request['electrical']
        data['operating_point']=run['scenario']
        data['candidate_updates']=[u for u in store.snapshot(sid).get('candidate_updates',[])
                                   if u['target_revision']<=run['revision']]
        write_json(folder/'run_manifest.json',data)
    def electrical(sid,scenario,steps):
        session=store.snapshot(sid); revision=session['revision']
        existing=next((r for r in reversed(session['runs']) if r.get('scenario')==scenario
            and r.get('steps')==steps and r['revision']==revision and r['status']=='completed'),None)
        if existing:
            folder=outputs/sid/existing['id']
            if all((folder/k).exists() and digest(folder/k)==v for k,v in existing.get('source_sha256',{}).items()) and existing.get('source_sha256'):
                manifest(folder,sid,existing)
                return existing
            raise ValueError('Saved electrical data changed; start a new study')
        if shutil.disk_usage(root).free<5*1024**3: raise RuntimeError('Less than 5 GiB free before simulation')
        rid=uuid.uuid4().hex[:12];folder=outputs/sid/rid
        run=dict(id=rid,action='simulate',revision=revision,spec=session['spec'],status='running',
                 scenario=scenario,steps=steps,created_at=now())
        store.add_run(sid,run)
        MatlabRuntime.prepare(session['spec'],'simulate',folder,electrical=dict(
            scenario_id=scenario,steps_per_switching_period=steps,export_full_csv=False,
            export_legacy_csv=False,export_legacy_mat=False),context=dict(
            session_id=sid,run_id=rid,design_revision=revision,comparison_group_id=f'{scenario}_rev{revision}'))
        print(f'BEGIN electrical {scenario} revision={revision} steps={steps} run={rid}',flush=True)
        try:
            result=runtime.execute(session['spec'],'simulate',folder,cancel,emit)
            run.update(status='completed',metrics=result['metrics'],checks=result.get('checks'),finished_at=now(),
                       source_sha256={k:digest(folder/k) for k in ['result.json','electrical_raw_v1.mat']})
            manifest(folder,sid,run)
        except BaseException as exc:
            run.update(status='failed',error=str(exc));raise
        finally:
            with store.lock:
                stored=next(r for r in store.get(sid)['runs'] if r['id']==rid)
                stored.update(run);store.save();write_json(folder/'run.json',run)
        print(f'DONE electrical {scenario} {steps}: {json.dumps(run["metrics"])}',flush=True)
        return run
    def fields(sid,run):
        folder=outputs/sid/run['id'];session=store.snapshot(sid)
        if (folder/'multiphysics_result.json').exists():
            saved=read_multiphysics(folder,session,run)
            if saved.get('status')=='completed' and not saved.get('stale'):
                if saved.get('source_sha256')!=run['source_sha256']: raise ValueError('C source hash mismatch')
                return saved
        print(f'BEGIN fields {run["scenario"]} revision={run["revision"]}',flush=True)
        result=execute_multiphysics(runtime,folder,session,run,cancel,emit)
        print(f'DONE fields {run["scenario"]} revision={run["revision"]}',flush=True)
        return result
    def resolve(sid,scenario,phase):
        steps=400 if scenario=='rated' else 1600
        coarse=electrical(sid,scenario,steps)
        comparisons=[]
        while steps<3200:
            fine=electrical(sid,scenario,steps*2)
            comparison=compare(coarse['metrics'],fine['metrics'])
            comparison.update(coarse_run_id=coarse['id'],fine_run_id=fine['id'],coarse_steps=steps,fine_steps=steps*2)
            comparisons.append(comparison)
            state['scenarios'][scenario][phase]=dict(status='step_check',comparisons=comparisons);persist()
            if comparison['converged']:
                field=fields(sid,fine)
                row=dict(status='completed',run=fine,fields=field,comparisons=comparisons)
                state['scenarios'][scenario][phase]=row;persist();return row
            coarse=fine;steps*=2
        raise RuntimeError('Original convergence criteria not met at 3200 steps; retained failed pairs')
    for scenario in args.scenarios:
        case=state['scenarios'].get(scenario)
        if case is None:
            sid=store.create()['id']
            store.update_spec(sid,dict(model_fidelity='sps_device_closed_loop',load_step=scenario=='rated_to_half'))
            case=state['scenarios'][scenario]=dict(session_id=sid);persist()
        sid=case['session_id']
        for phase in ('baseline','candidate'):
            saved=case.get(phase,{})
            if saved.get('status')=='completed':
                run=saved['run']; folder=outputs/sid/run['id']
                if any(not (folder/k).is_file() or digest(folder/k)!=v
                       for k,v in run['source_sha256'].items()):
                    raise ValueError('Saved electrical data changed; start a new study')
                checked=read_multiphysics(folder,store.snapshot(sid),run)
                if checked.get('status')!='completed' or checked.get('source_sha256')!=run['source_sha256']:
                    raise ValueError('Saved field evidence is no longer valid')
                manifest(folder,sid,run)
        if case.get('baseline',{}).get('status')!='completed': resolve(sid,scenario,'baseline')
        if 'parameter_update' not in case:
            session=store.snapshot(sid)
            if session.get('candidate_updates'):
                case['parameter_update']=session['candidate_updates'][-1]
            else:
                updated=apply_candidate_revision(store,outputs,sid,case['baseline']['run']['id'])
                case['parameter_update']=updated['candidate_update']
            persist()
        if case.get('candidate',{}).get('status')!='completed': resolve(sid,scenario,'candidate')
        c=case['candidate']; summary=c['fields']['input_summary']
        # The revision must reproduce the selected source parameters exactly.
        # A newly generated FE mesh can produce a slightly different L; retain
        # that numerical repeatability difference instead of changing the design.
        selected=case['parameter_update']['new_parameters']
        assert all(c['run']['spec'][key]==value for key,value in selected.items())
        assert abs(summary['R_difference_percent'])<1e-10
        case['recomputed_L_difference_percent']=summary['L_difference_percent']
        case['alignment_verified']=True;persist()
    state['status']='completed' if all(c.get('alignment_verified') for c in state['scenarios'].values()) else 'incomplete'
    persist();print('ITERATION_DONE '+str(state_path),flush=True)


if __name__=='__main__': main()
