"""Publish compact, byte-hashed course evidence; never include MAT, SLX or config."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'docs/evidence/course_acceptance_20261026'


def publish(source, relative):
    target = DEST / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    data = source.read_bytes()
    if source.suffix in ('.json', '.log', '.m'):
        text = data.decode('utf-8-sig', errors='replace').replace('\r\n', '\n')
        # Published copies use portable repository paths; original hashes remain original.
        for root in (ROOT.as_posix(), str(ROOT), str(ROOT).replace('\\', '\\\\')):
            text = text.replace(root, '${REPOSITORY}')
        data = text.encode('utf-8')
    target.write_bytes(data)


def main():
    fields = ROOT / 'outputs/field_acceptance_20261026'
    browser = ROOT / 'work/browser_acceptance_20261026'
    numerical = json.loads((fields / 'summary.json').read_text(encoding='utf-8'))
    ui = json.loads((browser / 'acceptance.json').read_text(encoding='utf-8'))
    assert numerical['status'] == 'completed' and numerical['mesh_passed']
    assert ui['status'] == 'completed' and not ui['page_errors']
    assert ui['external_llm'] == 'deferred_by_user'
    publish(fields / 'summary.json', 'field_summary.json')
    for name in (*numerical['solver_files_sha256'], 'dcac_heat_sensitivity.m'):
        publish(ROOT / 'matlab/multiphysics' / name, 'solver_sources/' + name)
    for level in ('coarse', 'medium', 'fine'):
        for name in ('field_request.json', 'result.json', 'matlab.log', 'process.log',
                     'magnetic.png', 'thermal.png', 'structural.png', 'displacement.png'):
            publish(fields / level / name, f'mesh/{level}/{name}')
    for name in ('sensitivity.json', 'sensitivity.png', 'matlab.log', 'process.log'):
        publish(fields / 'sensitivity' / name, f'sensitivity/{name}')
    publish(browser / 'acceptance.json', 'browser/acceptance.json')
    for source in sorted(browser.glob('*_job.json')):
        publish(source, 'browser/' + source.name)
    for source in sorted((browser / 'screenshots').glob('*.png')):
        publish(source, 'browser/screenshots/' + source.name)
    sid = ui['session_id']
    for phase, run in ui['runs'].items():
        folder = ROOT / 'outputs' / sid / run['run_id']
        for name in ('request.json', 'result.json', 'matlab.log', 'process.log', 'multiphysics_result.json'):
            if (folder / name).is_file():
                publish(folder / name, f'browser/runs/{phase}/{name}')
        result = json.loads((folder / 'multiphysics_result.json').read_text(encoding='utf-8-sig'))
        attempt = folder / 'fields' / result['attempt_id']
        for name in ('field_request.json', 'result.json', 'matlab.log', 'process.log'):
            publish(attempt / name, f'browser/runs/{phase}/fields/{name}')
    manifest = {p.relative_to(DEST).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(DEST.rglob('*')) if p.is_file() and p.name != 'manifest.json'}
    (DEST / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f'Published {len(manifest)} files, {sum(p.stat().st_size for p in DEST.rglob("*") if p.is_file())/1024/1024:.2f} MiB')


if __name__ == '__main__':
    main()
