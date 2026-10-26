"""Real Chrome + local HTTP + MATLAB acceptance, with no external LLM calls."""
import argparse
import copy
import json
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dcac_agent.config import load_config,OUTPUTS
from dcac_agent.store import Store
from dcac_agent.web_app import Application,make_handler
from dcac_agent.multiphysics import write_json,digest
from playwright.sync_api import sync_playwright


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matlab',required=True)
    parser.add_argument('--chrome',default='C:/Program Files/Google/Chrome/Application/chrome.exe')
    parser.add_argument('--port',type=int,default=7864)
    args=parser.parse_args()
    folder=ROOT/'work/browser_acceptance_20261026';folder.mkdir(parents=True,exist_ok=True)
    pictures=folder/'screenshots';pictures.mkdir(exist_ok=True)
    config=load_config();config.update(matlab_executable=args.matlab,matlab_timeout_seconds=1800)
    config['llm'].update(enabled=False,api_key='',model='')
    store=Store(folder/'store');app=Application(config,store)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),make_handler(app))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    receipt=folder/'acceptance.json'
    report=json.loads(receipt.read_text(encoding='utf-8')) if receipt.exists() else dict(
        status='running',mode='real_browser_rules_real_matlab',external_llm='deferred_by_user',steps={},runs={})
    sid=report.get('session_id')
    if sid is None:
        sid=store.create()['id'];report['session_id']=sid
    if report.get('error'):
        report.setdefault('recovered_errors',[]).append(report.pop('error'))
    report['status']='running';write_json(receipt,report)
    page_errors=[]
    def save():write_json(receipt,report)
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path=args.chrome,headless=True)
            context=browser.new_context(viewport=dict(width=1600,height=1000),device_scale_factor=1,accept_downloads=True)
            page=context.new_page();page.on('pageerror',lambda error:page_errors.append(str(error)))
            report['browser_version']=browser.version
            url=f'http://127.0.0.1:{server.server_port}'
            page.goto(url);page.wait_for_function('() => state !== null')
            def select_session(target):
                if page.evaluate('selectedSession')!=target:
                    index=page.evaluate('id => state.sessions.findIndex(s=>s.id===id)',target)
                    assert index>=0
                    page.locator('.session-item').nth(index).click()
                    page.wait_for_function('id => selectedSession === id',arg=target)
            select_session(sid)

            def screenshot(name):
                page.screenshot(path=str(pictures/(name+'.png')),full_page=False)

            def wait_job(job,label,expected='completed'):
                started=time.monotonic()
                while job['status'] in ('queued','running','cancelling'):
                    if time.monotonic()-started>1900:raise TimeoutError(label)
                    page.wait_for_timeout(1000)
                    job=page.request.get(url+'/api/jobs/'+job['id']).json()
                clean=copy.deepcopy(job);clean.pop('result',None)
                write_json(folder/(label+'_job.json'),clean)
                assert job['status']==expected,(label,job['status'],job.get('error'))
                page.wait_for_function('id => state?.job?.id === id && !busyStates.has(state.job.status) && !document.getElementById("simulateButton").disabled',arg=job['id'],timeout=30000)
                report['steps'][label]=dict(status='job_completed',job_id=job['id'],job_status=job['status'])
                save();print('DONE browser '+label,flush=True)
                return job

            def action(label,click,expected='completed'):
                if report['steps'].get(label,{}).get('status')=='job_completed':
                    job=json.loads((folder/(label+'_job.json')).read_text(encoding='utf-8'))
                    assert job['status']==expected
                    return job
                print('BEGIN browser '+label,flush=True)
                with page.expect_response(lambda r:r.url.endswith('/api/chat') and r.request.method=='POST') as pending:
                    click()
                response=pending.value;assert response.status==202
                return wait_job(response.json(),label,expected)

            def chat(label,text,expected='completed'):
                page.locator('#messageInput').fill(text)
                return action(label,lambda:page.locator('#sendButton').click(),expected)

            def pending(label):
                return report['steps'].get(label,{}).get('status')!='passed'

            def verified(label):
                report['steps'][label]['status']='passed';save()

            def collect_run(phase):
                run=next(r for r in reversed(store.snapshot(sid)['runs']) if r['action']=='simulate' and r['status']=='completed')
                result=json.loads((OUTPUTS/sid/run['id']/'result.json').read_text(encoding='utf-8-sig'))
                assert result['source']=='MATLAB/Simulink' and result['ok']
                report['runs'][phase]=dict(run_id=run['id'],revision=run['revision'],spec=run['spec'],metrics=result['metrics'],
                    source_sha256={n:digest(OUTPUTS/sid/run['id']/n) for n in ('result.json','electrical_raw_v1.mat')})
                save();return run

            def check_images(prefix):
                page.locator('[data-tab="results"]').click()
                page.wait_for_function('() => document.querySelectorAll(".physics-image").length===4 && [...document.querySelectorAll(".physics-image")].every(x=>x.complete && x.naturalWidth>0)',timeout=30000)
                for index,img in enumerate(page.locator('.physics-image').all()):
                    img.screenshot(path=str(pictures/f'{prefix}_field_{index+1}.png'))
                page.locator('.inspector').evaluate('(x)=>x.scrollTop=0')
                screenshot(prefix)

            if pending('parameters'):
                if 'parameters' not in report['steps']:
                    page.locator('#editSpec').click()
                    page.locator('#modelStage').select_option('sps_device_closed_loop')
                    page.locator('#param-switching_frequency').fill('20')
                    page.locator('#param-output_power').fill('500')
                action('parameters',lambda:page.locator('#specForm button[type="submit"]').click())
                assert store.snapshot(sid)['spec']['model_fidelity']=='sps_device_closed_loop'
                screenshot('01_parameters')
                verified('parameters')
            if pending('baseline_electrical'):
                action('baseline_electrical',lambda:page.locator('#simulateButton').click())
                collect_run('baseline');page.locator('[data-tab="results"]').click()
                page.wait_for_function('() => result?.solver?.steps_per_switching_period===400')
                assert '400 步/开关周期' in page.locator('#resultSummary').inner_text()
                screenshot('02_electrical')
                verified('baseline_electrical')
            if pending('baseline_fields'):
                page.locator('[data-tab="results"]').click()
                action('baseline_fields',lambda:page.locator('#fieldsButton').click())
                check_images('03_baseline_fields')
                verified('baseline_fields')
            if pending('apply_candidate'):
                chat('apply_candidate','回填候选参数')
                assert store.snapshot(sid)['candidate_updates']
                page.locator('[data-tab="results"]').click()
                assert page.locator('#staleNotice').is_visible();screenshot('04_stale_revision')
                verified('apply_candidate')
            if pending('stale_rejected'):
                job=action('stale_rejected',lambda:page.locator('#fieldsButton').click(),'failed')
                assert '旧修订' in job['error'];screenshot('05_stale_rejected')
                verified('stale_rejected')
            if pending('candidate_electrical'):
                action('candidate_electrical',lambda:page.locator('#simulateButton').click())
                collect_run('candidate')
                selected=store.snapshot(sid)['candidate_updates'][-1]['new_parameters']
                assert all(report['runs']['candidate']['spec'][k]==v for k,v in selected.items())
                verified('candidate_electrical')
            if pending('candidate_fields'):
                page.locator('[data-tab="results"]').click()
                action('candidate_fields',lambda:page.locator('#fieldsButton').click())
                check_images('06_candidate_fields')
                verified('candidate_fields')
            latest=report['runs']['candidate']['run_id'];old=report['runs']['baseline']['run_id']
            page.locator('[data-tab="results"]').click()
            page.locator('#runSelect').select_option(old)
            page.wait_for_function('id => currentRun?.id === id && result?.run_context?.run_id === id',arg=old)
            assert page.locator('#staleNotice').is_visible();screenshot('07_history')
            page.reload();page.wait_for_function('() => state !== null')
            # Reload chooses the most recently updated session. A prior cancellation
            # checkpoint may have created a newer session; reselect our test session.
            refresh_session=page.evaluate('selectedSession');select_session(sid)
            page.wait_for_function('id => currentRun?.id === id && result?.run_context?.run_id === id',arg=latest)
            assert not page.locator('#staleNotice').is_visible();check_images('08_refreshed')
            report['steps']['history_refresh']=dict(status='passed',history_run=old,refresh_default=latest,
                initial_session_after_reload=refresh_session,scenario_session=sid);save()
            if pending('compare'):
                action('compare',lambda:page.locator('#compareButton').click());verified('compare')
            if 'download' not in report['steps']:
                page.locator('[data-tab="files"]').click()
                link=page.locator(f'a[href="/artifacts/{sid}/{latest}/dcac_inverter.slx"]')
                with page.expect_download() as download:link.click()
                target=folder/'downloaded_model.slx';download.value.save_as(target)
                assert digest(target)==digest(OUTPUTS/sid/latest/'dcac_inverter.slx')
                report['steps']['download']=dict(status='passed',sha256=digest(target));save()
            if pending('missing_raw_rejected'):
                raw=(OUTPUTS/sid/latest/'electrical_raw_v1.mat').resolve()
                assert raw.is_relative_to(OUTPUTS.resolve())
                backup=raw.with_suffix('.mat.acceptance_hold');assert not backup.exists()
                raw.rename(backup)
                try:
                    page.locator('[data-tab="results"]').click()
                    job=action('missing_raw_rejected',lambda:page.locator('#fieldsButton').click(),'failed')
                    assert '缺少完整采样' in job['error'];screenshot('09_missing_raw_rejected')
                finally:backup.rename(raw)
                assert digest(raw)==report['runs']['candidate']['source_sha256']['electrical_raw_v1.mat']
                verified('missing_raw_rejected')
            if pending('cancel') and report['steps'].get('cancel',{}).get('status')!='job_completed':
                page.locator('#newSession').click();page.wait_for_function('id => selectedSession !== id',arg=sid)
                report['cancel_session_id']=page.evaluate('selectedSession');save()
                with page.expect_response(lambda r:r.url.endswith('/api/chat') and r.request.method=='POST') as pending:
                    page.locator('#simulateButton').click()
                job=pending.value.json()
                deadline=time.monotonic()+30
                while not any(e['kind']=='matlab' for e in job['events']):
                    assert time.monotonic()<deadline
                    page.wait_for_timeout(500);job=page.request.get(url+'/api/jobs/'+job['id']).json()
                page.wait_for_timeout(1500);page.locator('#cancelTask').click()
                wait_job(job,'cancel','cancelled');screenshot('10_cancelled')
                verified('cancel')
            elif pending('cancel'):
                index=page.evaluate('id => state.sessions.findIndex(s=>s.id===id)',report['cancel_session_id'])
                assert index>=0
                page.locator('.session-item').nth(index).click()
                page.wait_for_function('id => selectedSession===id',arg=report['cancel_session_id'])
                assert report['steps']['cancel']['job_status']=='cancelled'
                screenshot('10_cancelled');verified('cancel')
            # Deliberately hostile display text is an explicit UI test, not model output.
            chat('safe_markdown','验收格式测试：**粗体** `<script>alert(1)</script>` [坏链接](javascript:alert(1)) <img src=x onerror=alert(1)>')
            assert page.locator('.message-content img, .message-content script, .message-content iframe').count()==0
            assert page.locator('.message-content strong').count()>0
            assert page.locator('.message-content a[href^="javascript:"]').count()==0
            screenshot('11_markdown')
            verified('safe_markdown')
            page.set_viewport_size(dict(width=390,height=844));page.wait_for_timeout(500)
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth+1')
            screenshot('12_mobile');report['steps']['mobile']=dict(status='passed',width=390)
            assert not page_errors,page_errors
            assert all(step['status']=='passed' for step in report['steps'].values())
            report['page_errors']=page_errors;report['status']='completed';save()
            browser.close()
    except Exception as error:
        report['status']='failed';report['error']=str(error);save();raise
    finally:
        with app.agent.lock:
            for job in app.agent.jobs.values():job['cancel'].set()
        server.shutdown();server.server_close();app.agent.pool.shutdown(wait=True,cancel_futures=True)
    print('BROWSER_ACCEPTANCE_PASS '+str(receipt),flush=True)


if __name__=='__main__':main()
