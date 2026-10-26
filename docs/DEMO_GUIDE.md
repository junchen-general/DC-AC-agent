# 课程演示与复现

先在项目根目录安装 Python 环境，并确认 MATLAB 包含 Simulink、Simscape Electrical 的 SPS 和 PDE Toolbox。以下示例使用本次验收的 R2023b 路径，其他机器按实际安装位置修改。

```powershell
$env:DCAC_MATLAB = 'C:/Program Files/MATLAB/R2023b/bin/matlab.exe'
.\.venv\Scripts\python.exe run_web.py
```

打开 `http://127.0.0.1:7862`。本次演示使用本地规则模式，不需要配置大模型。

## 网页演示顺序

1. 新建设计，在参数页选择电压闭环、380 V 输入、220 V 输出、500 W、50 Hz、20 kHz。先说明当前修订及 L=2 mH、R=0.25 Ω 基准。
2. 点击“运行仿真”。完成后查看电压、电流、THD、实际步数和统计窗口，说明单次运行与步长对比的区别。
3. 运行磁热力分析，依次查看磁场、温度、热应力和位移图，指出场结果关联的电气运行。
4. 输入“回填候选参数”。当前修订增加，原图被标为旧修订；检查 L 与 R20 的更新记录。
5. 再运行电气仿真和磁热力分析，比较新旧 L/R 差异。不要把历史结果当成新的求解结果。
6. 在下拉列表切换旧运行，再刷新页面，核对默认选中最新成功运行。在文件页下载 SLX。
7. 用[课程验收记录](COURSE_ACCEPTANCE.md)说明网格比较和热源敏感性；演示时无需等待重新计算全部加密工况。

磁热力图位于右侧结果区域下方，需在该区域向下滚动。完整流程会启动 MATLAB，耗时取决于本机性能；没有计算完成时，不提前展示“成功”结论。

## 自动验收

浏览器验收依赖 Playwright 和本机 Chrome；应用本身的规则模式不需要 Playwright。先安装：

```powershell
.\.venv\Scripts\python.exe -m pip install playwright==1.64.1
.\.venv\Scripts\python.exe tools/run_browser_acceptance.py --matlab $env:DCAC_MATLAB
```

脚本在 7864 端口启动独立服务，用独立会话运行两轮真实电气与场求解，并检查历史、刷新、下载、旧修订、缺失 MAT、取消和 Markdown 显示。完整结果在 `work/browser_acceptance_20261026/`；它与日常网页会话分开，截图中的会话不会自动出现在默认网页。

脚本保留已完成步骤用于中断恢复。同一输出目录再次执行会复用已记录步骤；若需要全新验收，先将该目录移至自己明确命名的备份位置，再执行。不要把恢复运行写成又完成了一整轮求解。

网格研究依赖[L/R 复验](LR_ALIGNMENT.md)生成的完整本地数据：`outputs/lr_alignment_20261026/iteration.json` 及其指向的候选 MAT。GitHub 只保存精简证据，新机器需先按该报告复现或取得对应完整数据并校验哈希。

```powershell
.\.venv\Scripts\python.exe tools/run_field_acceptance.py --matlab $env:DCAC_MATLAB
.\.venv\Scripts\python.exe tools/export_course_acceptance.py
```

网格驱动核对请求和求解源码后可以复用三档场结果；热源敏感性使用最细网格单位响应。导出脚本要求数值与浏览器记录均已完成，仅复制精简证据，不导出配置、密钥、MAT 或 SLX。

## 待补的模型服务验收

真实外部模型服务按用户要求暂缓。后续使用本项目自己的本地配置，验证新增 `run_multiphysics` 和 `apply_candidate_parameters` 能由真实模型正确调用，并核对最终回复与工具状态。当前 Nanobot 自动测试使用测试提供者，只验证接入和调度，不能替代这一步。
