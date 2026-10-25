# C 分工：滤波电感磁、热、力分析

本目录整理 C 的计算结果，供 A、B 审阅。计算对象是输出滤波电感及等效安装结构，采用 MATLAB R2023b Update 7、Simulink 和 PDE Toolbox。

建议先读 [课程报告](C课程报告.md)，再看 [完整图集](C研究结果全图.md) 和 [波形与谐波复核](波形与谐波复核.md)。[交接说明](C仿真交接.md) 列出与 A/B 对接时的数据要求；[研究说明](研究说明.md) 保留候选方案和方法检查过程，其中早期单股绕组方案已由课程报告中的多股截面积方案更新。

## 本次内容

- E55 的 64/74/83 匝候选与 E70 的 68 匝改进方案。
- 二维磁场计算、电感回填和 500/750 W 电气复验。
- 单位热源、铜阻温度反馈、组合温度场、热位移和拉主应力。
- 磁场及热结构网格检查，电气步长检查和电压、电流谐波分析。
- 29 张结果图，以及可复核的 JSON 数值摘要。

最终组合场对应 E70、68 匝、FE 电感 1.909 mH 和 400 步电气运行；800 步结果用作复核，未混用不同运行的输入。额外绕组热和磁芯热各取 0.5 W，温度和应力结论适用于报告给出的热源、材料与边界条件。

## 文件位置

| 内容 | 位置 |
|---|---|
| 求解与后处理代码 | [matlab/multiphysics](../../matlab/multiphysics/README.md) |
| 汇总结果 | [study_summary.json](evidence/study_summary.json) |
| 谐波及步长数据 | [waveform_audit/metrics.json](evidence/waveform_audit/metrics.json) |
| 组合场网格检查 | [mesh_check.json](evidence/mesh_check.json) |
| 原始运行工件清单 | [c_study_manifest.json](evidence/c_study_manifest.json) |
| 图片 | [完整图集](C研究结果全图.md) |

文中 `outputs/...` 指在 `matlab/multiphysics/` 下运行脚本后生成的相对路径。Git 中的现有图片和摘要保存在本目录的 `evidence/`；全采样率 CSV、MAT、SLX 不随仓库提交。工件清单记录原计算目录的文件哈希，不表示清单中的大文件都已上传。

C 代码目前独立运行。A 可据交接说明接入工具和展示，B 可核对 L、R、电流及工况；原有网页、Agent 和电气核心文件没有在本次提交中修改。
