# DC/AC Agent

参考 `D:/code/plcc-agent/PLCC-agent` 的本地Web控制台、会话管理、工具调用轨迹和MATLAB控制方式，实现的单相逆变器设计工作台。

当前版本：**成员A集成版（2026-10-23）**，已加入Nanobot适配与多物理场结果接收，物理求解能力仍以v0.1为基础。网页和计算流程可以不配置大模型直接使用；真正的建模、编译与仿真需要本机MATLAB/Simulink。

**C 分工补充（2026-10-25）**：滤波电感的磁场、温度和热应力分析已作为独立研究模块加入仓库，包含 E55/E70 方案比较、500/750 W 电气复验、网格与步长检查，以及 29 张结果图。先看 [C 分工说明](docs/c_multiphysics/README.md) 或 [课程报告](docs/c_multiphysics/C课程报告.md)。这些脚本已在 MATLAB R2023b Update 7 上运行，尚未接入网页的工具调用流程。

## 启动

已安装Python 3.10或以上版本时，不需要额外安装Python依赖：

```powershell
cd D:\code\DC-AC-agent
python run_web.py
```

浏览器访问 **http://127.0.0.1:7862**。也可以双击 `启动DCAC-Agent.bat`。程序默认只监听本机，不会部署到公网。原PLCC项目不受影响。

端口冲突时：

```powershell
$env:DCAC_PORT = '7863'
python run_web.py
```

## 已实现

- 中文对话与设计会话，参数面板，设计修订及历史保存。
- 从中文要求中提取输入/输出电压、功率、频率、LC参数及负载突变。
- 参数与物理约束检查；默认380 V DC → 220 Vrms、50 Hz、500 W。
- 根据参数**通过MATLAB脚本搭建可编辑的真实Simulink模型**，不是预制模型图片。
- 本地MATLAB批处理调用、串行后台任务、任务取消、原始错误日志。
- 成功仿真后提取有效值、2–40次电压谐波THD、电感电流、负载功率和给定绕组电阻损耗。
- 真实波形绘制，最近两次结果比较，参数更改后标明旧结果所属修订。
- 下载`.slx`、MAT数据、CSV、JSON参数、波形PNG、MATLAB日志及可单独运行的建模脚本。
- 可选兼容Chat Completions工具调用的模型接口；模型读取工具结果后继续决策，单轮最多三次MATLAB任务。
- 导出脚本后可在已打开的MATLAB中执行；在原目录执行成功后，刷新网页可读取生成的结果。

## 模型边界

当前模板是**单相全桥理想开关函数＋LC状态方程，开环、单极性SPWM、40 ms软启动**。

模型包含可打开的`SPWM`、`Full_Bridge`、`LC_Filter`子系统。全桥用`Vab = Vin * (Sa - Sb)`表示，桥臂下管采用互补信号；LC通过连续积分器计算：

```text
L * dIL/dt = Vab - rL*IL - Vout
C * dVout/dt = IL - Gload(t)*Vout
```

这是有实际开关脉冲和滤波动态的等效模型，**尚不是由四个Simscape半导体器件构成的器件级模型**。网页使用的电气模板当前不包含死区、开关/导通损耗、闭环控制、三相或并网。磁芯选型和磁/热/结构有限元位于独立的 `matlab/multiphysics/` 模块，暂不由网页调用。

不输出虚构的效率、结温、磁通密度或应力。给定绕组电阻损耗不等于整机总损耗。THD在末尾4个完整基波周期计算2–40次谐波，不含载波频段；它不是全频带失真指标，也不是实验测量值。

输出功率是基于**目标输出电压**选择电阻负载的额定值；实测仿真输出功率取决于实际输出电压。默认负载突变为0.12 s额定负载降到半载，变更前后仍为电阻负载。

网页模板采用`ode4`固定步长，步长为`1/(100*fsw)`。C 的独立复现副本已比较每开关周期 100—1600 步，并对 E70 的 500/750 W 工况进行了 400/800 步复核，见 [波形与谐波复核](docs/c_multiphysics/波形与谐波复核.md)。电压 THD 不代表电感电流的高频纹波；低次 THD 和磁链积分残差仍有步长敏感性。

## C 分工：滤波电感多物理场

最终课程算例采用 TDK N87 E70/33/32、2.5 mm 单片气隙和 68 匝绕组。二维线性磁场得到电感 1.909 mH，与绕组电阻 0.2166 Ω 一同回填电气模型；同时保留 E55 候选及厂商目录参数对照。

热—力算例取环境 40°C、外周对流系数 10 W/(m²·K)，额外绕组热和磁芯热各为 0.5 W，并迭代考虑铜电阻随温度变化。500/750 W 对应最高温度为 71.42/97.49°C。这些温度对应所列热源和边界条件，不能把两项 0.5 W 写成材料损耗模型的预测值。完整参数、位移、应力和网格检查见报告。

- [课程报告](docs/c_multiphysics/C课程报告.md)：参数选择、部件改进和计算结果。
- [给 A/B 的交接说明](docs/c_multiphysics/C仿真交接.md)：数据来源、指标含义与接入事项。
- [全部结果图](docs/c_multiphysics/C研究结果全图.md)：29 张波形、磁场、温度、位移、应力及复核图。
- [波形与谐波复核](docs/c_multiphysics/波形与谐波复核.md)：绘图混叠修正、电压/电流频谱与步长比较。
- [代码与复现入口](matlab/multiphysics/README.md)、[数值摘要](docs/c_multiphysics/evidence/study_summary.json)。

C 的电气计算使用独立的 R2023b 兼容副本，原电气核心与 A/B 的应用代码保持原样。全采样率 CSV、MAT、SLX 等大文件由脚本重新生成，未放入 Git；仓库保存源代码、参数、数值证据和图片。

## 建议先尝试

```text
建立500 W、输入380 V、输出220 V、50 Hz的单相逆变器，先查看设计参数
生成当前设计的模型
运行仿真
将开关频率改为25 kHz，重新仿真
电感改为3 mH，电容改为6.8 uF
加入负载突变并运行仿真
比较最近两次结果
导出建模与仿真脚本
```

没有API Key时，界面明确显示“本地规则模式”。规则模式支持有限句式，不等同于开放式大模型Agent。复杂需求可以通过参数面板输入，或配置大模型。

## 可选大模型配置

网页左下角“模型与运行设置”可填写兼容接口基础地址、支持工具调用的模型名称和API Key。也可以将`config.example.json`复制为`config.json`并编辑，或设置：

```powershell
$env:LLM_API_KEY = '填写你的Key'
$env:LLM_BASE_URL = '填写兼容接口基础地址（通常以/v1结尾）'
$env:LLM_MODEL = '填写模型名称'
python run_web.py
```

不复用原PLCC项目中的密钥、账号或连接配置。配置文件已在`.gitignore`中忽略，页面返回的配置会移除Key。开启大模型时，会将对话、设计参数和工具摘要发送给你选择的服务。首版使用轻量工具执行器，没有强制安装Nanobot；它保留了参考项目的对话—工具—结果结构，后续可适配Nanobot工具注册。

## MATLAB接入与故障恢复

默认自动检测`matlab.exe`，也可在设置中填写完整路径。当前机器安装路径为：

```text
D:/Program Files/MATLAB/R2025a/bin/matlab.exe
```

由于本机默认Python为3.14，首版默认采用`matlab -batch`，避免MATLAB Engine与Python版本兼容问题。每次任务独立启动进程，速度会慢于常驻Engine。

如果后台启动出现**5201**，表示MATLAB不能与所需MathWorks服务通信；这不代表电路模型已运行或已失败。先确认从桌面正常打开MATLAB是否可用。应用会保留任务日志。官方排查资料：

- https://www.mathworks.com/matlabcentral/answers/1815395-why-do-i-receive-error-5201-unable-to-access-services-required-to-run-matlab

可以点击“导出脚本，在已打开的MATLAB中执行”，复制对话给出的`run('.../run_in_matlab.m')`命令，在正常打开的MATLAB里执行。也可以在`outputs/<会话>/<运行>/`中打开`run_in_matlab.m`。**保留该目录内的`request.json`和`dcac_execute.m`。**

脚本执行成功后，原运行目录会生成`.slx`和结果文件，刷新网页可以读取；如果把导出目录移动到别处，结果保存在新目录，需要手动查看，不会自动关联原网页会话。

若MATLAB首选项目录不可写，可将环境变量`DCAC_MATLAB_PREFDIR`指向专用可写目录。不要把“已检测到MATLAB路径”误认为“许可证或仿真已经验证”。

## 文件结构

```text
dcac_agent/
  agent.py       对话、工具定义、规则模式、可选大模型循环、任务队列
  design.py      设计参数、单位提取、约束检查
  runtime.py     MATLAB批处理调用、导出脚本、超时与取消
  store.py       会话、参数修订与运行历史
  web_app.py     本地HTTP服务、设置、工件下载
  web/           HTML/CSS/JS界面，无外部CDN依赖
matlab/
  dcac_execute.m 自动建模、编译、仿真、指标计算和工件导出
  multiphysics/  C 的独立磁场、热结构、电气复验与后处理脚本
docs/c_multiphysics/  C 的报告、交接、结果图和数值证据
tests/           标准库unittest测试
outputs/         每次运行独立的输入、模型、结果和日志（Git忽略）
work/            会话与本地验证中间文件（Git忽略）
```

## 验证

```powershell
python -m unittest discover -s tests -v
node --check dcac_agent/web/app.js
```

测试替身只在临时目录使用，不向正式网页注入示例仿真结果。真实MATLAB验证状态参见`VALIDATION.md`。

## 下一步

1. 完成本机真实MATLAB联调与步长验证。
2. 加入四个Simscape器件的全桥模板及死区、器件损耗。
3. 加入电压闭环与动态性能检查。
4. 将已有 C 多物理场脚本按共同运行协议接入 Agent 和网页，完成 A/B/C 联调。

软件用于课程设计建模，当前结果不能作为实物电源设计已完成的证据。


## 成员A：Nanobot模式与协作接口

规则模式仍只需Python标准库。Nanobot模式使用已验证的Python 3.14.6和nanobot-ai 0.3.5；其他Python版本尚未验证。

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install "nanobot-ai==0.3.5"
./.venv/Scripts/python.exe run_web.py
```

启动脚本和BAT会优先使用本项目.venv。网页设置中勾选“启用大模型工具调用”，选择“Nanobot 0.3.5”，填写支持Chat Completions工具调用的服务地址、模型和自己的API Key。关闭大模型恢复规则模式；原有自写循环保留在“兼容接口”选项。不要将密钥发到聊天或提交Git。

Nanobot只注册项目8个工具，不开放默认shell、文件操作或子代理工具。每个任务独立运行时，共享Store提供本会话最近16条消息；后台队列仍串行，最多12轮、3次MATLAB任务，支持取消。内部使用Nanobot的AgentLoop/ToolRegistry，已锁定版本，升级依赖需重新测试。密钥仅注入内存中的Nanobot配置；网页设置仍保存在被忽略的config.json。

每次电气任务生成run_manifest.json；C的multiphysics_result.json按协议交付后，网页刷新显示各域指标与PNG，检测归属并标记旧修订。**C的自动求解工具尚未接入**，目前只支持读取交付结果；结果格式合格不等于物理模型已验证。

完整协议、B/C待交付项、报告方法素材及演示流程见[docs/INTEGRATION.md](docs/INTEGRATION.md)。

验证命令：

```powershell
./.venv/Scripts/python.exe -m unittest discover -s tests -v
node --check dcac_agent/web/app.js
```

现已验证真实Nanobot运行时配合测试模型服务的工具循环；尚未验证用户的外部模型服务、真实Simulink及磁热力联合求解。首次使用Nanobot可能需要下载分词资源。测试使用独立临时目录，测试数据不作为课程结论。


2026-10-25进展：用户已完成外部模型工具调用和一次真实电气仿真，输出219.22 Vrms、THD（2—40次）0.608%。详细条件与证据边界见VALIDATION.md最新记录；多物理场联合求解仍待交付。


## 成员 B 电气模块已集成（2026-10-26）
新增四阶段电气建模、原始数据与损耗后处理、工况/步长验证及精简交付工件。默认网页仍使用基础开环模型；器件/闭环阶段目前通过脚本选择。现有 Nanobot、网页和 C 多物理场模块保留。

使用方法、纳入范围和验证限制见 [B 合并说明](docs/MERGE_B_20261026.md)，历史验证见 [B 验证记录](docs/B_VALIDATION_RESULTS.md)，数据见 [精简工件](artifacts/b_final/README.md)。B 的 20 kHz 历史矩阵与本机 25 kHz 基础复验是不同证据；12 组步长对比仍有 9 组未达标。
