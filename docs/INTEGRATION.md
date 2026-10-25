# A/B/C 接口协议 v1.0

本协议是A已实现的接收边界，待B/C确认并交付生产者。保留原有 request.json/result.json，不更改B的执行签名。

## 电气运行

A调用现有 MatlabRuntime.execute(spec, action, outdir, cancel, emit)。每次结束写入同目录 run_manifest.json，含 schema_version、session_id、run_id、revision、spec、status、action、evidence、source、fidelity、operating_point、metrics、artifacts 和 handoff。
成功数值结果需 source=MATLAB/Simulink；导出/失败不视为数值证据。当前保真度固定为旧版理想开关函数模型，B升级时需同步A。

B应新增 electrical_handoff.json（尚未自动消费），提供：原始MAT/CSV相对路径、变量或列映射、SI单位、采样间隔、分析区间、电感电流/电压、RMS/峰值、铜损及温度/材料来源、步长验证记录。现有CSV无表头，不能猜列。A默认handoff=not_ready，尚不会把旧结果自动转交C求解。

## C的结果文件

C将 multiphysics_result.json 和引用工件放在对应电气运行目录 outputs/<session_id>/<run_id>/。刷新网页或调用 get_multiphysics_results(run_id)读取。没有文件返回not_run；不自动执行C代码。

必填字段示例（仅协议结构，不是仿真结果）：

```json
{
  "schema_version": "1.0",
  "session_id": "对应会话ID",
  "parent_run_id": "对应电气运行ID",
  "revision": 0,
  "evidence": "test",
  "component_version": "inductor-v1",
  "material_version": "material-v1",
  "boundary_version": "boundary-v1",
  "solver": "求解器及版本",
  "verification": {"mesh": "尚未开展", "loss_source": "待B交付"},
  "domains": {
    "magnetic": {"status": "not_run", "metrics": {}, "artifacts": []},
    "thermal": {"status": "not_run", "metrics": {}, "artifacts": []},
    "structural": {"status": "not_run", "metrics": {}, "artifacts": []}
  }
}
```

各域status为not_run/failed/completed。成功时metrics非空，格式为指标名→{"value":有限数值,"unit":"SI单位"}；未求值不要填0。artifacts为运行目录内相对路径，PNG显示为图片，其余支持JSON/CSV/MAT/PDF/M/SLX下载。evidence为test/analytical/numerical，网页始终显示类别；numerical为生产者声明，格式校验不代表物理正确性认证。

会话、运行、修订必须完全匹配；历史修订可读但显示过期。部件材料/边界版本由C管理，当前尚不能自动判断这些版本与最新设计的差异。

## 后续C执行器接口需求

建议 execute(electrical_handoff, component_spec, outdir, cancel, emit)返回以上结构。C先交付可独立复现入口和测试，再由A注册run_multiphysics工具。当前只注册读取工具，不把空实现作为求解器。

## 演示流程

1. 设置选择Nanobot，填写自己的支持工具调用的服务、模型和Key。
2. 输入“设置380 V输入、220 V/50 Hz输出、500 W，检查环境并导出脚本，不运行仿真”。
3. 展示实际工具输入/输出、独立目录和run_manifest.json，说明导出不是求解。
4. B环境可用后运行仿真；C按上述协议交付文件，刷新读取云图与指标。
5. 修改L为3 mH，旧结果显示过期；B/C复算后对比。完整真实联调仍待B/C交付。

## Agent方法报告素材

系统分为网页交互、串行任务与会话存储、Nanobot推理、受限领域工具和MATLAB执行五层。Nanobot负责根据需求选择工具、读取结构化反馈并决定下一步；参数校验、运行目录和求解由确定性代码负责。默认Nanobot内置工具全部移除，只注册本项目工具。会话历史由Store维护，每次任务独立运行时，避免跨设计混用上下文。取消信号同时传递给工具与模型等待任务。运行编号和修订将参数、调用轨迹和工件关联，用于审计与设计迭代；算法不以语言模型生成的数值代替物理求解。
