# 子任务 B 精简交付工件

本目录用于 GitHub 交付，来源为 MATLAB R2023b Update 7 的真实交互式编译与仿真，不是示例数据。

- `models/`：四个保真度阶段的可编辑 Simulink `.slx`。
- `cases/`：闭环额定、半载和额定到半载的可复现请求、波形、指标、manifest 与损耗依据。
- `raw_windows/`：三个工况各自最后一个完整 50 Hz 周期；保持 0.125 μs 原始固定步长、160,000 点、无降采样，包含完整电感电流、桥臂/输出/电感端电压、门极、直流侧和负载信号。可由这些主通道及参数直接恢复的重复派生数组不再保存。
- `summaries/`：24 次仿真和两档步长比较的机器可读汇总。
- `artifact_index.json`：数据来源、窗口和文件索引。

完整 0.24 s 原始 MAT 每份约 150 MB，保留在 B 原工作包的 `outputs/b_final/`（本次未复制到仓库工作目录），不直接提交 Git。需要全时域数据时，可使用对应 case 的 `request.json` 和 `matlab/dcac_execute.m` 重跑生成。GitHub 数据窗不是网页降采样曲线，适合 C 的代表性磁场/伏秒分析；启动和负载突变全过程则应使用完整本地 MAT 重现。

在已有完整 MAT 的机器上运行 `python tools/export_b_handoff.py` 可重建本目录；该可选导出脚本需要 NumPy 和 SciPy，不是 Agent 运行时依赖。

结果口径、符号和限制见 [`docs/B_TO_C_ELECTRICAL_DATA.md`](../../docs/B_TO_C_ELECTRICAL_DATA.md) 与 [`VALIDATION.md`](../../VALIDATION.md)。

原manifest中的哈希对应原始运行文件；精简交付文件以package_checksums.json为准。B历史验证细节见[验证记录](../../docs/B_VALIDATION_RESULTS.md)。
