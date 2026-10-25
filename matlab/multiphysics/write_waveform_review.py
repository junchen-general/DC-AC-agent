"""Write the waveform review from verified numerical results."""
from pathlib import Path
import json

root=Path(__file__).resolve().parent
rows=json.loads((root/'outputs/waveform_audit/metrics.json').read_text(encoding='utf-8'))
by={r['case']:r for r in rows}
lines=['# 波形与谐波复核','',
'原波形图将 0.24 s 内的数据直接抽取为 3200 点。显示采样率约为 13.33 kHz，低于表示开关纹波所需的采样率，因此电感电流出现了缓慢起伏的假包络。检查最后四个工频周期的原始数据后，对应开关周期的平均电流重合，没有发现图中所暗示的逐周期幅值变化。', '',
'现有电气波形图已重新绘制：阴影表示每个开关周期内的最小值和最大值，实线表示周期平均值，第三幅图保留四个开关周期的全部采样点。平均曲线用于看工频变化，阴影和局部图用于看纹波。图中 THD 明确标为输出电压的指标。JSON 中沿用的稀疏瞬时预览不能用于频谱计算或判断纹波包络。', '',
'## 频谱计算', '',
'计算采用最后四个完整的 50 Hz 周期，去掉重复的右端点，直接对原始等间隔数据作 FFT。基波位于第 4 个频率间隔，频率分辨率为 12.5 Hz。2—40 次 THD 为这些谐波的合成有效值与基波有效值之比；不包含开关频段。宽带非基波比例去除直流和基波，保留至各自采样奈奎斯特频率的剩余分量。另列统一的 2—200 kHz 电流比例，便于不同步长之间比较。两者分母均为电流基波有效值。', '',
'| 工况 | 每开关周期步数 | 电压 THD 2—40 次 | 电流 THD 2—40 次 | 电流宽带非基波比例 | 电流 2—200 kHz 比例 |',
'|---|---:|---:|---:|---:|---:|']
for r in rows:
    label='基准模型'
    if 'candidate74' in r['case']: label='E55，74 匝，500 W'
    if 'E70FE68_' in r['case']: label='E70，'+r['case'].split('E70FE68_')[1].replace('W',' W')
    lines.append(f"| {label} | {r['samples_per_switch']} | {r['voltage_thd_2_40_percent']:.4f}% | {r['current_thd_2_40_percent']:.4f}% | {r['current_nonfundamental_to_nyquist_percent']:.3f}% | {r['current_2kHz_to_200kHz_percent']:.3f}% |")
lines += ['', '低次电流谐波较小，但电感电流的高频纹波仍然明显。电压 THD 较低，并不意味着绕组和磁芯承受的高频激励可以忽略。本模型负载为电阻，负载电流与输出电压同形；电感电流还包含流入滤波电容的电流，因此两种电流不能混为一谈。', '',
'## 步长复核', '',
'| 对比 | 电压有效值变化 | 电感电流有效值变化 | 电感峰值变化 | Rdc 铜损变化 | 电压 THD 变化（百分点） |',
'|---|---:|---:|---:|---:|---:|']
pairs=[('基准 800→1600','electrical_reference_800','electrical_reference_1600')]
for power in (500,750):
    pairs.append((f'E70 {power} W，400→800',f'electrical_reference_400_E70FE68_{power}W',f'electrical_reference_800_E70FE68_{power}W'))
for label,a,b in pairs:
    a,b=by[a],by[b]
    changes=[100*abs(a[k]-b[k])/abs(b[k]) for k in ['output_rms_V','current_rms_A','current_peak_A','winding_Rdc_loss_W']]
    delta=abs(a['voltage_thd_2_40_percent']-b['voltage_thd_2_40_percent'])
    lines.append('| '+label+' | '+' | '.join(f'{v:.4f}%' for v in changes)+f' | {delta:.5f} |')
lines += ['', '这里同时列出有效值、峰值和 THD，避免用某一个指标代替全部数值精度。THD 很小时，较小的绝对差也可能对应较大的相对变化。因此只把较细步长结果作为当前模型的数值参考，不将它当作已经排除所有开关事件误差的极限值。现有热—力组合场仍引用 400 步电气运行，800 步用于检查其输入变化，未混用两次运行的数值。', '',
'## 磁链与磁通纹波图', '',
'磁链图比较 Li 与电感电压的时间积分。积分中扣除了绕组电阻压降，并对齐积分常数。残差反映两种数值计算的差异，不代表磁芯损耗，也不是电流 THD。', '',
'| 基准步数 | 残差 RMS / 磁链峰值 | 残差最大绝对值 |', '|---|---:|---:|']
for step in (400,800,1600):
    r=by[f'electrical_reference_{step}']
    lines.append(f"| {step} | {r['flux_residual_rms_percent_of_peak']:.4f}% | {r['flux_residual_max_mWb_turn']:.5f} mWb·turn |")
lines += ['', '桥臂电压存在跳变，采样后作梯形积分与求解器内部积分并不完全一致。残差随步长缩小的变化见上表；这项检查只用于线性电路的一致性分析，不能代替非线性磁芯验证。', '',
'74 匝候选图下方表示每个开关周期内的 ΔB 峰峰值，由 B=Li/(N Ae) 换算。它不是瞬时磁通密度曲线，因此不要求呈正弦形，也不能把该值当作总磁通峰值用于判断饱和。其最大值约 93.4 mT，对应最大电流纹波约 1.314 A。', '',
'## 对热—力结果的影响', '',
'此前 Rdc 铜损由完整电流的均方值计算，已经包含高频纹波对固定电阻损耗的贡献，绘图抽点不会改变这一数值。不过，这不包含频率相关的集肤、邻近及气隙边缘场附加损耗。组合场中的额外绕组热 0.5 W 和磁芯热 0.5 W 仍是课程算例的热源输入，不能从电压 THD 反推这些损耗。温度和应力结论适用于报告列出的热源与边界条件。', '',
'## 图与复现', '',
'![抽点影响与真实纹波](outputs/waveform_audit/sampling_audit.png)', '',
'![全采样率频谱](outputs/waveform_audit/full_rate_spectrum.png)', '',
'![步长复核](outputs/waveform_audit/step_refinement.png)', '',
'在原有运行结果齐全时，MATLAB 中运行 `run_electrical_reference(1600)`、`run_waveform_refinement`、`analyze_flux_linkage`、`analyze_switching_ripple`；随后运行 `python audit_waveform_harmonics.py`、`python write_waveform_review.py` 和 `python summarize_study.py`。Python 后处理需要 NumPy、SciPy 和 Matplotlib。FFT 计算检查了频域与时域能量一致性，并与原电压 THD 结果逐项核对。', '',
'降采样原理参考：[MathWorks downsample 文档](https://www.mathworks.com/help/signal/ref/downsample.html)。']
(root/'波形与谐波复核.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('Written 波形与谐波复核.md')
