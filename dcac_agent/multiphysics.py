"""Run-local C solver adapter. No arbitrary paths or code from model input."""
import hashlib
import json
import math
import shutil
import uuid
from pathlib import Path

from .config import ROOT
from .contracts import read_multiphysics
from .store import now

DEFAULT_OPTIONS = dict(ambient_c=40.0, convection_w_m2k=10.0,
                       extra_winding_heat_w=0.5, core_heat_w=0.5)


def field_options(updates=None):
    if updates is not None and not isinstance(updates, dict):
        raise ValueError("磁热力边界条件必须为对象。")
    if set(updates or {}) - DEFAULT_OPTIONS.keys():
        raise ValueError("未知磁热力边界参数。")
    result = {**DEFAULT_OPTIONS, **(updates or {})}
    bounds = dict(ambient_c=(-20, 100), convection_w_m2k=(5, 50),
                  extra_winding_heat_w=(0, 20), core_heat_w=(0, 20))
    for key, (lo, hi) in bounds.items():
        v = result[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
            raise ValueError(f"{key}须为{lo}至{hi}之间的有限数值。")
    return result


def write_json(path, data):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temp.replace(path)


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def execute_multiphysics(runtime, folder, session, run, cancel, emit, options=None):
    options = field_options(options)
    if run['status'] != 'completed' or run['action'] != 'simulate':
        raise ValueError('磁热力求解需要成功的电气仿真。')
    if run['revision'] != session['revision'] or run['spec'] != session['spec']:
        raise ValueError('电气结果属于旧修订，请先重新仿真当前设计。')
    parent_path = folder / 'result.json'
    parent = json.loads(parent_path.read_text(encoding='utf-8-sig'))
    if not parent.get('ok') or parent.get('source') != 'MATLAB/Simulink' or parent.get('spec') != run['spec']:
        raise ValueError('父电气结果不是匹配的真实MATLAB仿真。')
    if parent.get('action') != 'simulate':
        raise ValueError('父结果没有执行时域仿真。')
    context = parent.get('run_context', {})
    for key, expected in [('session_id', session['id']), ('run_id', run['id']), ('design_revision', run['revision'])]:
        if context.get(key) != expected:
            raise ValueError('电气运行缺少匹配的身份记录；请重新运行电气仿真。')
    raw_path = folder / 'electrical_raw_v1.mat'
    if not raw_path.is_file():
        raise ValueError('缺少完整采样electrical_raw_v1.mat；请重新运行电气仿真，不可使用网页抽样波形。')
    if cancel.is_set():
        raise InterruptedError('任务已取消。')
    attempt = uuid.uuid4().hex[:12]
    relative = Path('fields') / attempt
    out = folder / relative
    out.mkdir(parents=True)
    status = dict(status='running', parent_run_id=run['id'], revision=run['revision'], attempt_id=attempt, started_at=now())
    status_path = folder / 'multiphysics_status.json'
    write_json(status_path, status)
    try:
        src = ROOT / 'matlab' / 'multiphysics'
        for name in ['dcac_multiphysics.m', 'solve_magnetic_e70.m', 'solve_unit_e70_thermal_structural.m',
                     'plane_stress_cte_adapter.m', 'verify_plane_stress_backend.m', 'material_assumptions.json']:
            shutil.copyfile(src / name, out / name)
        request = dict(session_id=session['id'], parent_run_id=run['id'], revision=run['revision'],
                       spec=run['spec'], parent_dir=folder.resolve().as_posix(), options=options,
                       source_sha256={p.name: digest(p) for p in (parent_path, raw_path)})
        write_json(out / 'field_request.json', request)
        (out / 'run_fields_in_matlab.m').write_text(
            "taskDir=fileparts(mfilename('fullpath')); addpath(taskDir);\n"
            "dcac_multiphysics(fullfile(taskDir,'field_request.json'));\n", encoding='utf-8')
        emit('run', '执行E70候选磁热力求解（单向耦合）', {'parent_run_id': run['id'], 'attempt_id': attempt, 'options': options})
        result = runtime.execute_fields(out, cancel, emit)
        if cancel.is_set():
            raise InterruptedError('任务已取消。')
        for domain in result['domains'].values():
            domain['artifacts'] = [(relative / name).as_posix() for name in domain.get('artifacts', [])]
        result['attempt_id'] = attempt
        result['source_sha256'] = request['source_sha256']
        result['completed_at'] = now()
        if any(digest(folder / name) != expected for name, expected in request['source_sha256'].items()):
            raise ValueError('求解过程中电气源文件发生变化，拒绝发布结果。')
        # The running status hides the staged result until schema validation passes.
        published = folder / 'multiphysics_result.json'
        previous = published.read_bytes() if published.exists() else None
        write_json(published, result)
        try:
            checked = read_multiphysics(folder, session, run, ignore_status=True)
        except Exception:
            if previous is not None:
                published.write_bytes(previous)
            else:
                published.unlink(missing_ok=True)
            raise
        status.update(status='completed', finished_at=now())
        write_json(status_path, status)
        return checked
    except Exception as exc:
        status.update(status='cancelled' if cancel.is_set() or isinstance(exc, InterruptedError) else 'failed',
                      message=str(exc), finished_at=now())
        write_json(status_path, status)
        raise
