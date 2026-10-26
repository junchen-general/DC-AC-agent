"""Apply a solved component's exact cold L/R to a new design revision."""
import copy
import math
import re

from .contracts import read_multiphysics
from .design import DesignSpec
from .multiphysics import digest
from .store import now


def apply_candidate_revision(store, outputs, sid, run_id):
    if not isinstance(run_id,str) or not re.fullmatch(r'[a-f0-9]{12}',run_id):
        raise ValueError('必须提供当前会话的有效电气运行编号。')
    with store.lock:
        session=store.snapshot(sid)
        run=next((r for r in session['runs'] if r['id']==run_id),None)
        if run is None or run['status']!='completed' or run['action']!='simulate':
            raise ValueError('候选回填需要成功的父电气仿真。')
        if run['revision']!=session['revision'] or run['spec']!=session['spec']:
            raise ValueError('候选属于旧修订，请先对当前设计重新求解。')
        folder=outputs/sid/run_id
        result=read_multiphysics(folder,session,run)
        if result.get('status')!='completed' or result.get('evidence')!='numerical' or result.get('stale'):
            raise ValueError('只能回填当前修订的成功数值场结果。')
        for key,value in [('session_id',sid),('parent_run_id',run_id),('revision',session['revision'])]:
            if result.get(key)!=value: raise ValueError('候选来源与父运行不匹配。')
        if any(result.get('domains',{}).get(d,{}).get('status')!='completed'
               for d in ('magnetic','thermal','structural')):
            raise ValueError('候选磁热力求解尚未全部完成。')
        sources=result.get('source_sha256',{})
        for name in ('result.json','electrical_raw_v1.mat'):
            if not (folder/name).is_file() or sources.get(name)!=digest(folder/name):
                raise ValueError('候选输入文件缺失或已改变，请重新求解。')
        summary=result.get('input_summary',{})
        updates={'inductance':summary.get('candidate_L_H'),
                 'winding_resistance':summary.get('candidate_R20_ohm')}
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0
               for v in updates.values()):
            raise ValueError('候选 L/R 必须为正的有限数值。')
        spec=DesignSpec(**session['spec']).updated(updates)
        provenance=dict(source_run_id=run_id,source_attempt_id=result.get('attempt_id'),
            source_revision=session['revision'],target_revision=session['revision']+1,
            component_version=result['component_version'],
            field_result_sha256=digest(folder/'multiphysics_result.json'),source_sha256=sources,
            old_parameters={k:session['spec'][k] for k in updates},new_parameters=updates,
            resistance_reference_temperature_c=20,resistance_basis='cold_R20',
            coupling='explicit_single_parameter_update',created_at=now())
        changed=copy.deepcopy(session)
        changed.update(spec=spec.to_dict(),revision=session['revision']+1,updated_at=now())
        changed.setdefault('candidate_updates',[]).append(provenance)
        previous=store.sessions[sid]
        store.sessions[sid]=changed
        try: store.save()
        except Exception:
            store.sessions[sid]=previous
            raise
        return dict(spec=spec.to_dict(),derived=spec.derived(),revision=changed['revision'],
                    candidate_update=provenance,
                    message='已将候选L和20°C电阻写入新修订；旧结果保留，请重新运行电气与磁热力。')
