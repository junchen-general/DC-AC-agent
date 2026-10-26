# C 多物理场计算脚本

报告和已有结果见 [C 分工说明](../../docs/c_multiphysics/README.md)。本目录包含求解器、参数与复现脚本，运行产生的 `outputs/` 不纳入 Git。

已运行环境为 MATLAB R2023b Update 7、Simulink、PDE Toolbox。`plane_stress_cte_adapter.m` 处理该版本平面应力热膨胀接口的差异；当前适配器在每个进程先运行 verify_plane_stress_backend，以自由膨胀和全约束应力解析基准选择处理方式；任一材料泊松比验证失败即阻止结构求解，不能直接套用修正系数。Python 后处理使用 NumPy、SciPy、Matplotlib，可通过 `python -m pip install -r requirements-analysis.txt` 安装；网页应用本身不依赖这些包。

## 重现 E70 课程算例

在 MATLAB 中进入本目录，依次执行：

```matlab
verify_field_methods
run_magnetic_e70_study
run_e70_fe_500
run_e70_fe_recheck
run_e70_unit_response
run_e70_core_mesh_check
analyze_e70_switching_ripple
run_e70_combined_scenarios
```

这组命令生成 500/750 W 电气数据、磁场、组合温度/位移/应力以及网格复核。完整 E55 对照、基准步长和汇总的前置运行顺序见 [研究说明](../../docs/c_multiphysics/研究说明.md#7-文件与复现) 与 [波形复核](../../docs/c_multiphysics/波形与谐波复核.md)。`summarize_study.py` 需要这些前置结果齐全，不能只运行 E70 后就生成完整研究摘要。

`compatibility/dcac_execute.m` 是本地电气复现副本，`source_snapshot/` 保留其上游来源。本目录的运行入口自动设置兼容副本路径，不替换仓库的 `matlab/dcac_execute.m`。MATLAB 运行应串行执行，避免同名 Simulink 模型冲突。

## 数据与绘图

`simulation.mat` 保存完整时间和信号，CSV 列依次为时间、输出电压、电感电流、负载电流、桥臂电压。THD 采用最后四个完整工频周期，电压和电流分别统计。JSON 的稀疏瞬时预览可能发生混叠，不能代替原始数据作分析。

`refresh_electrical_figures` 从已有完整数据重绘波形，保留每个开关周期的真实最小/最大值和局部全速曲线。`audit_waveform_harmonics.py` 检查频谱、步长及磁链残差，生成 `outputs/waveform_audit/`；`write_waveform_review.py` 在本目录生成复核文稿，发布时应将图像链接转换为文档证据目录。

网页接入入口为dcac_multiphysics.m；读取指定父运行的electrical_raw_v1.mat，独立求解当前电流驱动的E70候选。协议与限制见../../docs/C_AGENT_INTEGRATION.md。
