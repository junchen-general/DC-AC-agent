# 数值证据

`study_summary.json` 汇总求解指标、输入参数、候选比较和验证结果。`waveform_audit/metrics.json` 包含电压/电流谐波及步长复核；`electrical_refinement/` 保存三次加密运行的请求与交接摘要。`all_figures/` 收录全部 29 张结果图。

发布版 JSON 删除了仅供预览的稀疏 `waveforms` 数组，保留计算指标，并将运行机器的绝对路径改为仓库相对路径。数值未重新计算。这些 JSON 不是完整波形，不能用它们替代 `simulation.mat` 或 `signals.csv` 做 FFT。

`c_study_manifest.json` 是原计算目录的文件哈希清单，保留原记录；它用于对照本地工件，不是发布版文件的校验表。原始大文件由代码复现，未放入 Git。`metrics.json` 与 `mesh_check.json` 为 E70 组合热—力工况及网格复核，图片的使用顺序见上一层的完整图集。
