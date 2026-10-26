# 候选电感 L/R 回填复验

三工况联合复验状态：已完成。

本轮 MATLAB 版本：23.2.0.2515942 (R2023b) Update 7。执行仓库中的集成求解入口，额定、半载和阶跃分别保留基准与候选修订，完成范围以本页表格和摘要中的状态为准。

本次将 C 数值求解输出的电感量和 20°C 绕组电阻写入新的电气修订，保留原 2 mH、0.25 Ω 基准。电路使用冷态电阻，热模型继续按最高温度更新铜阻损耗；这是一次显式参数更新，不是自动电热双向迭代。

电气条件为 380 V 输入、220 V/50 Hz 目标、20 kHz、电压闭环、500 W 额定阻性负载；半载工况对应 250 W。热边界仍为环境 40°C、外周对流 10 W/(m²·K)，附加绕组热与磁芯热各 0.5 W。

| 工况 | 修订 | L / mH | R20 / Ω | 输出 / Vrms | THD 2—40 次 / % | IL / Arms | IL 峰值 / A | 最高温度 / °C | 中心柱截面平均峰值磁密 / T | 最大位移 / µm | 探针拉应力 / MPa |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 额定 | 基准 | 2 | 0.25 | 219.68 | 1.7007 | 2.3089 | 3.68478 | 71.4025 | 0.146497 | 23.9185 | 4.74812 |
| 额定 | 候选回填 | 1.90907 | 0.216641 | 219.685 | 1.65139 | 2.31081 | 3.7394 | 71.4355 | 0.148669 | 23.9431 | 4.75313 |
| 半载 | 基准 | 2 | 0.25 | 220.017 | 1.61935 | 1.24456 | 2.53414 | 57.8627 | 0.100751 | 13.8366 | 2.69286 |
| 半载 | 候选回填 | 1.90907 | 0.216641 | 220.03 | 1.34533 | 1.2556 | 2.62397 | 57.9572 | 0.104322 | 13.9069 | 2.7072 |
| 额定至半载 | 基准 | 2 | 0.25 | 220.016 | 1.62613 | 1.24504 | 2.54153 | 57.8668 | 0.101045 | 13.8396 | 2.69348 |
| 额定至半载 | 候选回填 | 1.90907 | 0.216641 | 220.027 | 1.34553 | 1.25542 | 2.61675 | 57.9557 | 0.104035 | 13.9058 | 2.70697 |

额定下，回填前后最高温度为 71.40°C 和 71.44°C，变化 +0.033°C。电路的固定电阻铜耗随 R20 回填而改变，但两次 C 热场都使用同一候选绕组的 R20 和温度反馈，因此不能直接把电路铜耗的下降解释为温升下降。本次完成参数一致性复验，不把微小变化写成显著优化。

## 步长检查

相对误差以细步长为分母，沿用 B 的判据：输出电压 <0.2%、电流有效值 <0.5%、电流峰值 <1%，THD 绝对差 <0.1 个百分点。额定从 400/800 步检查；半载和阶跃从 B 已有分辨率证据指向的 1600/3200 步重新计算。改变 L/R 后使用新运行重新判定，不沿用旧工况的通过标记。

| 工况 | 修订 | 步数 | ΔV / % | ΔIL,rms / % | ΔIL,peak / % | ΔTHD / 百分点 | 通过 |
|---|---|---|---:|---:|---:|---:|---|
| 额定 | 基准 | 400/800 | 0.00337876 | 0.00655883 | 0.609029 | 0.026109 | 是 |
| 额定 | 候选回填 | 400/800 | 0.000599406 | 0.0203947 | 0.0144393 | 0.0378005 | 是 |
| 半载 | 基准 | 1600/3200 | 0.000986417 | 0.0689352 | 0.627845 | 0.0101425 | 是 |
| 半载 | 候选回填 | 1600/3200 | 0.00214845 | 0.212079 | 0.5622 | 0.0354459 | 是 |
| 额定至半载 | 基准 | 1600/3200 | 0.00264794 | 0.203052 | 0.338262 | 0.0285288 | 是 |
| 额定至半载 | 候选回填 | 1600/3200 | 0.00377094 | 0.29029 | 0.968978 | 0.0468113 | 是 |

## 0.12 s 降载响应

下表使用求解器的一周期 RMS 统计。恢复时间表示此后所有一周期 RMS 点均处于末窗值的 ±2% 内，不能据此声称已分辨出短于一个基波周期的恢复过程。

| 修订 | 降载后周期 RMS 最小 / V | 最大 / V | 2% 恢复时间 / ms | 瞬态电流峰值 / A | 瞬态电压峰值 / V |
|---|---:|---:|---:|---:|---:|
| 基准 | 220.013 | 220.456 | 20 | 2.62162 | 323.227 |
| 候选回填 | 220.017 | 220.479 | 20 | 2.73663 | 325.79 |

## 查看场图

每个工况分别保留基准与回填后的四张图；应力图的角点峰值和表中的磁芯探针值含义不同。

- 额定 / 基准：[磁场](evidence/lr_alignment_20261026/rated/baseline/magnetic.png)、[温度](evidence/lr_alignment_20261026/rated/baseline/thermal.png)、[应力](evidence/lr_alignment_20261026/rated/baseline/structural.png)、[位移](evidence/lr_alignment_20261026/rated/baseline/displacement.png)
- 额定 / 候选回填：[磁场](evidence/lr_alignment_20261026/rated/candidate/magnetic.png)、[温度](evidence/lr_alignment_20261026/rated/candidate/thermal.png)、[应力](evidence/lr_alignment_20261026/rated/candidate/structural.png)、[位移](evidence/lr_alignment_20261026/rated/candidate/displacement.png)
- 半载 / 基准：[磁场](evidence/lr_alignment_20261026/half_load/baseline/magnetic.png)、[温度](evidence/lr_alignment_20261026/half_load/baseline/thermal.png)、[应力](evidence/lr_alignment_20261026/half_load/baseline/structural.png)、[位移](evidence/lr_alignment_20261026/half_load/baseline/displacement.png)
- 半载 / 候选回填：[磁场](evidence/lr_alignment_20261026/half_load/candidate/magnetic.png)、[温度](evidence/lr_alignment_20261026/half_load/candidate/thermal.png)、[应力](evidence/lr_alignment_20261026/half_load/candidate/structural.png)、[位移](evidence/lr_alignment_20261026/half_load/candidate/displacement.png)
- 额定至半载 / 基准：[磁场](evidence/lr_alignment_20261026/rated_to_half/baseline/magnetic.png)、[温度](evidence/lr_alignment_20261026/rated_to_half/baseline/thermal.png)、[应力](evidence/lr_alignment_20261026/rated_to_half/baseline/structural.png)、[位移](evidence/lr_alignment_20261026/rated_to_half/baseline/displacement.png)
- 额定至半载 / 候选回填：[磁场](evidence/lr_alignment_20261026/rated_to_half/candidate/magnetic.png)、[温度](evidence/lr_alignment_20261026/rated_to_half/candidate/thermal.png)、[应力](evidence/lr_alignment_20261026/rated_to_half/candidate/structural.png)、[位移](evidence/lr_alignment_20261026/rated_to_half/candidate/displacement.png)

## 结果归属与复现

候选参数由 `apply_candidate_parameters` 从当前成功 C 结果读取，未使用报告中的四舍五入值。回填记录保存原修订、目标修订、父运行和文件 SHA-256。原电气与场结果保留在独立目录。候选重新求解后核对 L/R 差异，不能把旧运行的云图标成新设计。

验收首先核对电路参数是否与选定的 C 来源值完全相同。重新生成有限元网格时，计算出的电感可能有微小变化；摘要另列该差异，不据此悄悄改写已经选定的设计。阶跃工况表中的电气量和稳态场均取 0.16—0.24 s，即降载后的窗口，不能解释为阶跃过程的瞬态温度或最大热应力。

源码入口为 `tools/run_lr_iteration.py`，传入本机 `--matlab` 路径运行；支持同一研究目录恢复已完成且源文件未改变的运行。求解代码变化时需指定新的 `--study`，不能复用旧证据。随后运行 `tools/export_lr_iteration.py` 生成本报告和精简证据。使用 Python 3.10 以上及 MATLAB、Simulink、Simscape Electrical SPS、PDE Toolbox。

```powershell
python tools/run_lr_iteration.py --matlab "C:/Program Files/MATLAB/R2023b/bin/matlab.exe" --study lr_alignment_20261026
python tools/export_lr_iteration.py --study lr_alignment_20261026
```

实际完成状态及数值见 [summary.json](evidence/lr_alignment_20261026/summary.json)。大型全采样率 MAT 和可编辑 SLX 保留在本地 `outputs/lr_alignment_20261026/`，Git 中提供请求、误差表、日志和场图。

发布的文本统一使用 LF 换行，并单独记录发布文件的 SHA-256；原始 MAT 与结果 JSON 的哈希另行保存。仓库属性保留证据文件的字节，避免不同系统的换行转换影响校验。

本次检查针对 L/R 回填和电气步长；没有新增三档场网格检查，也没有将指定热源转换为材料损耗预测。温度与应力仍对应所列模型输入，不据此判断实物饱和或强度安全。
