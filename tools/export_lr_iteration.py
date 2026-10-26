"""Publish compact evidence from a completed or partially completed L/R study."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser();p.add_argument('--study',default='lr_alignment_20261026');args=p.parse_args()
    if not args.study.replace('_','').isalnum(): raise ValueError('Invalid study name')
    study=ROOT/'outputs'/args.study
    state=json.loads((study/'iteration.json').read_text(encoding='utf-8'))
    out=ROOT/'docs/evidence'/args.study;out.mkdir(parents=True,exist_ok=True)
    published={k:v for k,v in state.items() if k!='scenarios'};published['scenarios']={}
    published['status']='completed' if all(state['scenarios'].get(name,{}).get('alignment_verified')
        for name in ('rated','half_load','rated_to_half')) else 'incomplete'
    versions=set()
    for case in state['scenarios'].values():
        for phase in ('baseline','candidate'):
            row=case.get(phase,{})
            if row.get('status')=='completed':
                path=study/'runs'/case['session_id']/row['run']['id']/'result.json'
                versions.add(json.loads(path.read_text(encoding='utf-8-sig'))['matlab_version'])
    lines=['# 候选电感 L/R 回填复验','',
        '三工况联合复验状态：'+('已完成。' if published['status']=='completed' else '尚未全部完成。'),'',
        '本轮 MATLAB 版本：'+ '；'.join(sorted(versions))+'。执行仓库中的集成求解入口，额定、半载和阶跃分别保留基准与候选修订，完成范围以本页表格和摘要中的状态为准。','',
        '本次将 C 数值求解输出的电感量和 20°C 绕组电阻写入新的电气修订，保留原 2 mH、0.25 Ω 基准。电路使用冷态电阻，热模型继续按最高温度更新铜阻损耗；这是一次显式参数更新，不是自动电热双向迭代。','',
        '电气条件为 380 V 输入、220 V/50 Hz 目标、20 kHz、电压闭环、500 W 额定阻性负载；半载工况对应 250 W。热边界仍为环境 40°C、外周对流 10 W/(m²·K)，附加绕组热与磁芯热各 0.5 W。','',
        '| 工况 | 修订 | L / mH | R20 / Ω | 输出 / Vrms | THD 2—40 次 / % | IL / Arms | IL 峰值 / A | 最高温度 / °C | 中心柱截面平均峰值磁密 / T | 最大位移 / µm | 探针拉应力 / MPa |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    names=dict(rated='额定',half_load='半载',rated_to_half='额定至半载')
    phase_names=dict(baseline='基准',candidate='候选回填')
    for name,case in state['scenarios'].items():
        pub={k:v for k,v in case.items() if k not in ('baseline','candidate')};published['scenarios'][name]=pub
        for phase in ('baseline','candidate'):
            row=case.get(phase,{})
            if row.get('status')!='completed': pub[phase]=row;continue
            run=row['run'];f=row['fields'];d=f['domains'];m=run['metrics'];s=run['spec']
            pub[phase]=dict(status='completed',run=run,comparisons=row['comparisons'],
                field_input=f['input_summary'],field_verification=f['verification'],
                field_metrics={domain:item['metrics'] for domain,item in d.items()},
                source_sha256=f['source_sha256'],attempt_id=f['attempt_id'],
                solver=f['solver'],limitations=f['limitations'])
            for comparison in pub[phase]['comparisons']:
                for side in ('coarse','fine'):
                    path=study/'runs'/case['session_id']/comparison[f'{side}_run_id']/'run.json'
                    record=json.loads(path.read_text(encoding='utf-8'))
                    comparison[f'{side}_metrics']=record['metrics']
                    comparison[f'{side}_source_sha256']=record['source_sha256']
            values=[s['inductance']*1000,s['winding_resistance'],m['output_rms'],m['thd_percent'],m['inductor_rms'],m['inductor_peak'],
                d['thermal']['metrics']['peak_temperature']['value'],d['magnetic']['metrics']['bulk_peak_flux_density']['value'],
                d['structural']['metrics']['max_displacement']['value']*1e6,d['structural']['metrics']['core_probe_tensile_stress']['value']/1e6]
            lines.append('| '+names[name]+' | '+('基准' if phase=='baseline' else '候选回填')+' | '+' | '.join(f'{v:.6g}' for v in values)+' |')
            folder=study/'runs'/case['session_id']/run['id'];dest=out/name/phase;dest.mkdir(parents=True,exist_ok=True)
            electrical=json.loads((folder/'result.json').read_text(encoding='utf-8-sig'))
            pub[phase]['matlab_version']=electrical['matlab_version']
            pub[phase]['electrical_checks']=electrical['checks']
            pub[phase]['dynamic']=electrical['electrical_v1']['dynamic']
            pub[phase]['sampling']=electrical['electrical_v1']['sampling']
            request=json.loads((folder/'request.json').read_text(encoding='utf-8'))
            request['output_dir']=f'outputs/{args.study}/runs/{case["session_id"]}/{run["id"]}'
            (dest/'request.json').write_text(json.dumps(request,ensure_ascii=False,indent=2),encoding='utf-8',newline='\n')
            for artifact in ('magnetic.png','thermal.png','structural.png','displacement.png'):
                shutil.copy2(folder/'fields'/f['attempt_id']/artifact,dest/artifact)
            for artifact in ('matlab.log','process.log'):
                if (folder/artifact).exists():
                    (dest/artifact).write_bytes((folder/artifact).read_bytes().replace(b'\r\n',b'\n'))
            fieldlog=folder/'fields'/f['attempt_id']/'matlab.log'
            if fieldlog.exists():
                (dest/'fields_matlab.log').write_bytes(fieldlog.read_bytes().replace(b'\r\n',b'\n'))
            pub[phase]['published_artifact_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(dest.iterdir()) if p.is_file()}
    rated=state['scenarios'].get('rated',{})
    if all(rated.get(p,{}).get('status')=='completed' for p in ('baseline','candidate')):
        a=rated['baseline'];b=rated['candidate']
        ta=a['fields']['domains']['thermal']['metrics']['peak_temperature']['value']
        tb=b['fields']['domains']['thermal']['metrics']['peak_temperature']['value']
        lines += ['',f'额定下，回填前后最高温度为 {ta:.2f}°C 和 {tb:.2f}°C，变化 {tb-ta:+.3f}°C。电路的固定电阻铜耗随 R20 回填而改变，但两次 C 热场都使用同一候选绕组的 R20 和温度反馈，因此不能直接把电路铜耗的下降解释为温升下降。本次完成参数一致性复验，不把微小变化写成显著优化。']
    lines += ['', '## 步长检查','',
        '相对误差以细步长为分母，沿用 B 的判据：输出电压 <0.2%、电流有效值 <0.5%、电流峰值 <1%，THD 绝对差 <0.1 个百分点。额定从 400/800 步检查；半载和阶跃从 B 已有分辨率证据指向的 1600/3200 步重新计算。改变 L/R 后使用新运行重新判定，不沿用旧工况的通过标记。','',
        '| 工况 | 修订 | 步数 | ΔV / % | ΔIL,rms / % | ΔIL,peak / % | ΔTHD / 百分点 | 通过 |',
        '|---|---|---|---:|---:|---:|---:|---|']
    for name,case in state['scenarios'].items():
        for phase in ('baseline','candidate'):
            for c in case.get(phase,{}).get('comparisons',[]):
                e=c['errors']
                lines.append(f'| {names[name]} | {phase_names[phase]} | {c["coarse_steps"]}/{c["fine_steps"]} | '+
                    ' | '.join(f'{e[k]:.6g}' for k in ['output_rms','inductor_rms','inductor_peak','thd_percentage_points'])+
                    (' | 是 |' if c['converged'] else ' | 否 |'))
    step=published['scenarios'].get('rated_to_half',{})
    if any(step.get(phase,{}).get('dynamic') for phase in ('baseline','candidate')):
        lines += ['', '## 0.12 s 降载响应','',
            '下表使用求解器的一周期 RMS 统计。恢复时间表示此后所有一周期 RMS 点均处于末窗值的 ±2% 内，不能据此声称已分辨出短于一个基波周期的恢复过程。','',
            '| 修订 | 降载后周期 RMS 最小 / V | 最大 / V | 2% 恢复时间 / ms | 瞬态电流峰值 / A | 瞬态电压峰值 / V |',
            '|---|---:|---:|---:|---:|---:|']
        for phase in ('baseline','candidate'):
            dynamic=step.get(phase,{}).get('dynamic',{})
            if not dynamic: continue
            settling=dynamic.get('settling_time_2pct_s')
            settling_text=f'{1000*settling:.6g}' if isinstance(settling,(int,float)) else '未记录'
            lines.append('| '+phase_names[phase]+' | '+ ' | '.join([
                f'{dynamic["one_cycle_rms_min_after_step_V"]:.6g}',
                f'{dynamic["one_cycle_rms_max_after_step_V"]:.6g}',settling_text,
                f'{dynamic["transient_inductor_peak_A"]:.6g}',
                f'{dynamic["transient_output_voltage_peak_V"]:.6g}'])+' |')
    lines += ['', '## 查看场图','',
        '每个工况分别保留基准与回填后的四张图；应力图的角点峰值和表中的磁芯探针值含义不同。','']
    for name,case in state['scenarios'].items():
        for phase in ('baseline','candidate'):
            if case.get(phase,{}).get('status')=='completed':
                prefix=f'evidence/{args.study}/{name}/{phase}'
                lines.append(f'- {names[name]} / {phase_names[phase]}：'+ '、'.join(
                    f'[{label}]({prefix}/{file}.png)' for label,file in
                    [('磁场','magnetic'),('温度','thermal'),('应力','structural'),('位移','displacement')]))
    lines += ['', '## 结果归属与复现','',
        '候选参数由 `apply_candidate_parameters` 从当前成功 C 结果读取，未使用报告中的四舍五入值。回填记录保存原修订、目标修订、父运行和文件 SHA-256。原电气与场结果保留在独立目录。候选重新求解后核对 L/R 差异，不能把旧运行的云图标成新设计。','',
        '验收首先核对电路参数是否与选定的 C 来源值完全相同。重新生成有限元网格时，计算出的电感可能有微小变化；摘要另列该差异，不据此悄悄改写已经选定的设计。阶跃工况表中的电气量和稳态场均取 0.16—0.24 s，即降载后的窗口，不能解释为阶跃过程的瞬态温度或最大热应力。','',
        '源码入口为 `tools/run_lr_iteration.py`，传入本机 `--matlab` 路径运行；支持同一研究目录恢复已完成且源文件未改变的运行。求解代码变化时需指定新的 `--study`，不能复用旧证据。随后运行 `tools/export_lr_iteration.py` 生成本报告和精简证据。使用 Python 3.10 以上及 MATLAB、Simulink、Simscape Electrical SPS、PDE Toolbox。','',
        '```powershell',
        'python tools/run_lr_iteration.py --matlab "C:/Program Files/MATLAB/R2023b/bin/matlab.exe" --study '+args.study,
        'python tools/export_lr_iteration.py --study '+args.study,
        '```','',
        f'实际完成状态及数值见 [summary.json](evidence/{args.study}/summary.json)。大型全采样率 MAT 和可编辑 SLX 保留在本地 `outputs/{args.study}/`，Git 中提供请求、误差表、日志和场图。','',
        '发布的文本统一使用 LF 换行，并单独记录发布文件的 SHA-256；原始 MAT 与结果 JSON 的哈希另行保存。仓库属性保留证据文件的字节，避免不同系统的换行转换影响校验。','',
        '本次检查针对 L/R 回填和电气步长；没有新增三档场网格检查，也没有将指定热源转换为材料损耗预测。温度与应力仍对应所列模型输入，不据此判断实物饱和或强度安全。']
    (out/'summary.json').write_text(json.dumps(published,ensure_ascii=False,indent=2),encoding='utf-8',newline='\n')
    (ROOT/'docs/LR_ALIGNMENT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Exported '+str(out))


if __name__=='__main__': main()
