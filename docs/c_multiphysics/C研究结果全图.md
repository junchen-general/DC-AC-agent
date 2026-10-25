# C 分工仿真结果全图

本图集收录本地 `C_research/outputs/` 的全部 **29 张 PNG**。它们是 MATLAB/Simulink 数值仿真图，不是实物实验照片。前六张对应最终 E70 课程算例；后续为 E55 对比、目录参数对照、步长检查及已替代的中间方案。图中单位热源以 K/W、µm/W 标示，不能与工作温度和位移混读。

## 最终 E70 方案：统一用二维 FE 电感的 500/750 W 工况

1. 500 W 输出电压与电感电流。![E70 FE 500 W 波形](evidence/all_figures/electrical_reference_400_E70FE68_500W/waveforms.png)
2. 750 W 输出电压与电感电流。![E70 FE 750 W 波形](evidence/all_figures/electrical_reference_400_E70FE68_750W/waveforms.png)
3. E70 二维磁场，图示为 1 A 线性求解。![E70 磁场](evidence/all_figures/magnetic_e70/magnetic_section.png)
4. E70 单位绕组热源的温升和位移响应。![E70 单位热力响应](evidence/all_figures/unit_response_e70/unit_response.png)
5. E70 500 W 的组合温度、位移、拉主应力场。![E70 500 W 组合场](evidence/all_figures/e70_combined_scenarios/E70FE68_500W.png)
6. E70 750 W 的组合温度、位移、拉主应力场。![E70 750 W 组合场](evidence/all_figures/e70_combined_scenarios/E70FE68_750W.png)

## E55 候选与方法检查

7. E55 二维磁场。![E55 磁场](evidence/all_figures/magnetic/magnetic_section.png)
8. E55 单位热—力响应。![E55 单位响应](evidence/all_figures/unit_response/unit_response.png)
9. E55 热场和结构场细节。![E55 热力场](evidence/all_figures/unit_response/thermal_structural_fields.png)
10. 64 匝/1.0 mm 气隙候选电气波形。![E55 64 匝](evidence/all_figures/electrical_reference_400_candidate64/waveforms.png)
11. 74 匝/1.5 mm 气隙候选 500 W 波形。![E55 74 匝 500 W](evidence/all_figures/electrical_reference_400_candidate74/waveforms.png)
12. 83 匝/2.0 mm 气隙候选 500 W 波形。![E55 83 匝 500 W](evidence/all_figures/electrical_reference_400_candidate83/waveforms.png)
13. 74 匝 750 W 波形。![E55 74 匝 750 W](evidence/all_figures/electrical_reference_400_candidate74_750W/waveforms.png)
14. 83 匝 750 W 波形。![E55 83 匝 750 W](evidence/all_figures/electrical_reference_400_candidate83_750W/waveforms.png)
15. 电路磁链 `Li` 与端口电压积分核对；差值包含采样/开关事件重构误差。![磁链核对](evidence/all_figures/flux_linkage_check.png)
16. 74 匝候选开关周期纹波与线性磁通范围。![开关周期纹波](evidence/all_figures/switching_ripple.png)

## 电气步长与 E70 目录参数对照

17. 基准 100 步/开关周期。![基准 100 步](evidence/all_figures/electrical_reference/waveforms.png)
18. 基准 200 步/开关周期。![基准 200 步](evidence/all_figures/electrical_reference_200/waveforms.png)
19. 基准 400 步/开关周期。![基准 400 步](evidence/all_figures/electrical_reference_400/waveforms.png)
20. 基准 800 步/开关周期。![基准 800 步](evidence/all_figures/electrical_reference_800/waveforms.png)
21. E70 厂商目录电感 500 W 对照波形。![E70 目录 500 W](evidence/all_figures/electrical_reference_400_E70catalog68_500W/waveforms.png)
22. E70 厂商目录电感 750 W 对照波形。![E70 目录 750 W](evidence/all_figures/electrical_reference_400_E70catalog68_750W/waveforms.png)
23. 早期 E70 目录电感 500 W 组合场，已由第 5 图的统一 FE 电感方案替代。![E70 目录组合场旧版](evidence/all_figures/e70_combined_scenarios/E70catalog68_500W.png)

图像的数值来源与限制见 [C课程报告](C课程报告.md)、`evidence/study_summary.json` 和本地原始运行目录。最终报告推荐引用第 1—6 图及 E55 比较中的第 7—9 图；其余保留为分析与复核过程。

## 本次补充：波形与步长复核

原电气图已用周期平均值和真实纹波范围重新绘制。新增基准 1600 步、E70 800 步以及频谱和绘图检查。数值解释见 [波形与谐波复核](波形与谐波复核.md)。

![electrical_reference_1600 / waveforms](evidence/all_figures/electrical_reference_1600/waveforms.png)

![electrical_reference_800_E70FE68_500W / waveforms](evidence/all_figures/electrical_reference_800_E70FE68_500W/waveforms.png)

![electrical_reference_800_E70FE68_750W / waveforms](evidence/all_figures/electrical_reference_800_E70FE68_750W/waveforms.png)

![waveform_audit / full_rate_spectrum](evidence/all_figures/waveform_audit/full_rate_spectrum.png)

![waveform_audit / sampling_audit](evidence/all_figures/waveform_audit/sampling_audit.png)

![waveform_audit / step_refinement](evidence/all_figures/waveform_audit/step_refinement.png)
