# B → C 电气数据交接说明

本说明对应 `dcac.electrical.handoff/1.0`。只有 `run_manifest.json.status=success` 且 `data_origin=real_simulation` 的运行可作为最终耦合输入；测试替身、解析估算、网页曲线和失败运行不可替代。

## 权威文件与兼容文件

- `electrical_raw_v1.mat`：C 的权威输入，包含 `t`、命名 `signals`、`meta`、`windows`、`metrics`、`losses`、工况与运行上下文。
- `electrical_full_v1.csv`：普通独立运行默认生成的同一全分辨率带表头版本。24 组验证矩阵为控制磁盘占用关闭该冗余导出，C 应直接读取 MAT。
- `run_manifest.json`：变量、单位、符号、采样、窗口、模型保真度、设计指纹、工件哈希和限制。
- `simulation.mat` 与无表头 `signals.csv`：普通独立运行为旧 Agent/UI 保留；旧 `y` 前四列固定为 `[Vout, IL, Iload, Vbridge]`。验证矩阵关闭这些冗余文件，但没有改变默认接口。
- `result.json.waveforms`：最多约 3200 点，只供网页显示，严禁用于磁芯损耗、峰值或纹波计算。

manifest 的工件清单在它自身写入前生成，因此不会递归记录 `run_manifest.json` 的自身哈希；其余同目录文件记录 SHA-256 与字节数。

## 本次真实交接包

根目录：`outputs/b_final/baseline_build/validation/`。24 个 case 均为 `run_manifest.json.status=success`、`data_origin=real_simulation`。三个推荐的闭环细步长 case 保留全分辨率 MAT；其他 case 保留可编辑 SLX、波形 PNG、结果 JSON、损耗依据、manifest 和可复现请求，原始 MAT 可按需重跑再生。机器可读的三项优先输入索引为 `docs/B_TO_C_HANDOFF_INDEX_v1.json`。

GitHub 提交另包含 `artifacts/b_final/` 精简包。其 `raw_windows/*.mat` 是从三个权威 n400 MAT 按 manifest 的 `magnetic_representative` 窗口直接截取，保持 0.125 μs 原始采样，无网页降采样；每份包含最后一个完整 50 Hz 周期，共 160,000 点。为降低仓库体积，GitHub 包只保留电感电流、桥臂/输出/电感端电压、负载与直流侧电流、门极状态、时间和样本索引；`v_winding_resistive=rL*i_inductor`、`v_inductive=v_inductor_terminal-v_winding_resistive`、`i_capacitor=i_inductor-i_load`、瞬时绕组损耗等重复派生数组由主通道恢复。`tools/export_b_handoff.py` 可从本地完整 MAT 重建该包。

C 优先使用下列细步长 case：

| 工况 | 目录 | 固定步长 | 样本数 | 代表性磁场窗 |
| --- | --- | ---: | ---: | --- |
| 额定 | `sps_device_closed_loop__rated__n400` | 0.125 μs | 1,920,001 | 0.22–0.24 s，160,000 点 |
| 半载 | `sps_device_closed_loop__half_load__n400` | 0.125 μs | 1,920,001 | 0.22–0.24 s，160,000 点 |
| 额定→半载 | `sps_device_closed_loop__rated_to_half__n400` | 0.125 μs | 1,920,001 | 0.22–0.24 s，160,000 点；另读 pre/transient/post 窗 |

额定细步长主要电气量：Vrms=219.688 V、THD(2–40)=1.727%、IL,rms=2.309 A、|IL|peak=3.707 A、`v_inductive` RMS=162.872 V、峰值=387.373 V。半载为 Vrms=220.053 V、THD=1.840%、IL,rms=1.258 A、|IL|peak=2.691 A。负载突变 case 最终 Vrms=220.057 V、THD=1.852%，瞬态电感峰值为 2.759 A，一周期 RMS 2% 整定时间为 20 ms。闭环使用显式死区基波前馈 `Δm=8*f_sw*t_dead/π=0.05093`；这是近似补偿，不是非线性器件观察器。

这些细步长 case 是推荐输入，但相应闭环组合没有全部通过严格步长一致性判据；C 在磁芯峰值/损耗结论中必须同时引用 `time_step_comparison_v1.csv` 的未收敛状态，必要时要求 B 继续细化时间步长。

## 完整 CSV 列

`sample_index_0based,time_s,i_inductor_A,v_bridge_V,v_out_V,i_load_A,load_conductance_S,v_inductor_terminal_V,v_winding_resistive_V,v_inductive_V,i_capacitor_A,p_winding_resistive_W,gate_a_upper,gate_a_lower,gate_b_upper,gate_b_lower,i_dc_A,v_dc_V`

主要符号约定：

- `i_inductor_A` 正方向：桥臂 A → 滤波电感 → 输出负载。
- `v_bridge_V`：桥臂 A 中点减桥臂 B 中点。
- `v_out_V`：输出节点减桥臂 B 返回端。
- `v_inductor_terminal_V=v_bridge_V-v_out_V`：含 DCR 的线圈总端电压。
- `v_winding_resistive_V=rL*i_inductor_A`。
- `v_inductive_V=v_bridge_V-v_out_V-rL*i_inductor_A`：理想感应电压，供磁链/磁芯分析。
- `p_winding_resistive_W=i_inductor_A²*rL`：常数 R 的瞬时直流欧姆项。

MAT 中的命名数组是权威源；采样间隔以 `t` 为准，不能只从请求步长推断。`meta.sampling` 记录求解器、固定步长、样本数、均匀性和起止时间。

## 窗口与工况

- `full_run`：全时域，用于软启动和负载突变追溯。
- `thd_steady`：末尾 4 个完整基波周期，右端点排除。
- `magnetic_representative`：按 `round(Tfund/dt)` 个样本选取末尾 1 个完整基波周期，保留开关纹波，优先供 C 选择代表性磁场输入。
- 突变工况另有 `pre_step`、`transient`、`post_step`。

每个窗口同时给出 `start_index_0based`、`end_index_exclusive_0based`、`last_sample_time_s` 与 `end_time_exclusive_s`，不把最后一个已包含样本误写成排除端点。

工况分开运行：额定恒载、半载恒载、额定→半载。半载的负载导纳和功率比是 0.5，电阻为 193.6 Ω。不能通过把设计额定功率改为 250 W 来冒充 500 W 设计的半载工况。

## 损耗与温度假设

- `loss_basis_v1.json` 记录器件参数、数据手册版本、测试条件和适用局限。
- 默认 `rL=0.25 Ω` 没有来源、参考温度和频率条件；`I²R` 不能直接作为最终热源。
- 若 C 具有导线几何、材料和温度结果，应分别回传 `Rdc(T)`、`Rac(f,T)` 与磁芯损耗。B 不把交流铜损或磁芯损耗并入未注明的单一“绕组损耗”。
- 在损耗账本未闭合前，不报告整机效率。

## 运行/修订绑定

`run_manifest.json.identity` 包含 `session_id`、`run_id`、`design_revision`、`component_revision_id`、`parent_component_revision_id`、`comparison_group_id` 与完整 `spec` 指纹。经兼容性审查后，正常 Agent 路径已经注入 session/run/design revision，不改变动作、旧字段或前端；低层直接调用 `prepare` 或手工构造请求且不传 `run_context` 时，对应字段才会为空。C 回传电感后，B 必须显式传入组件修订和父修订；C 不应从目录名猜修订。

`dcac_validate.m` 为同一阶段/工况的两档步长写入共同 `comparison_group_id` 和 peer run IDs；矩阵完成后，每个成功 run 的 manifest 会回填 `time_step_study_v1.json` 路径、实际差值、收敛布尔量和选中的细步长 run。单个孤立运行只标记为未比较，不能自行声称收敛。

## C 修改电感后的回传要求

C 至少回传：`component_revision_id,parent_revision_id,L_H,rL_ohm`，并注明：

- L 是割线、电感微分量还是能量等效值；对应偏置电流、纹波、频率、温度和容差。
- `rL` 是 Rdc 还是 Rac；对应参考/工作温度和频率。
- 匝数、气隙、磁芯材料/几何、导线和数据来源版本。
- 若明显非线性，提供 `L(i,T)`/`Rac(f,T)` 表，而不是强塞单一标量。

B 收到后需建立新设计修订，复算 LC 谐振、阻尼、调制度和器件裕量；重跑四阶段所需模型、额定/半载/突变与两档步长；复验输出 RMS、功率、THD、电感 RMS/峰值/纹波、感应电压、伏秒平衡、C 电流、动态峰值与整定时间；按新的温度/频率条件重算分项损耗，并重新发布完整 MAT/CSV/manifest。旧结果保留但标记过期，不覆盖。
