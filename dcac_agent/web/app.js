"use strict";
const $ = (id) => document.getElementById(id);
let state = null, activeJob = null, pollTimer = null, result = null, chartKey = "voltage", currentRun = null;
let stateGeneration = 0, selectedSession = null, resultGeneration = 0;
const baselineStage = "baseline_ideal_switching_open_loop";
const stageName = spec => state?.model_stages?.[spec?.model_fidelity || baselineStage] || "基础开环模型";
let traceSignature = null;
let messageSignature = null;
const busyStates = new Set(["queued", "running", "cancelling"]);
const parameterFields = [
  ["input_voltage", "直流输入 / V", 1, 10, 1000], ["output_voltage", "输出有效值 / V", 1, 1, 700],
  ["output_power", "额定输出功率 / W", 1, 5, 10000], ["output_frequency", "输出频率 / Hz", 1, 40, 100],
  ["switching_frequency", "开关频率 / kHz", 1000, 5, 50], ["inductance", "滤波电感 / mH", .001, .1, 50],
  ["capacitance", "滤波电容 / μF", .000001, .1, 100], ["winding_resistance", "绕组电阻 / Ω", 1, 0, 10],
  ["stop_time", "仿真时长 / s", 1, .16, .5],
  ["load_step_time", "负载突变时刻 / s", 1, .04, .35],
  ["load_final_ratio", "突变后负载 / 额定值", 1, .1, 1],
];

async function api(path, body) {
  const opts = body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json", "X-CSRF-Token": state?.csrf || ""}, body: JSON.stringify(body)};
  const response = await fetch(path, opts);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}
function node(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}
function icon(name) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#i-${name}`); el.append(use); return el;
}
let toastTimer;
function toast(message) {
  $("toast").textContent = message; $("toast").classList.remove("hidden");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => $("toast").classList.add("hidden"), 6500);
}
const number = (value, decimals = 2) => Number(value).toLocaleString("zh-CN", {maximumFractionDigits: decimals});
const localTime = (value, seconds = false) => new Date(value).toLocaleTimeString("zh-CN", {hour: "2-digit", minute: "2-digit", ...(seconds ? {second: "2-digit"} : {})});
function setBusy(busy) {
  for (const id of ["sendButton", "buildButton", "simulateButton", "editSpec", "compareButton", "exportButton", "fieldsButton"]) $(id).disabled = busy;
  $("taskBanner").classList.toggle("hidden", !busy);
  $("cancelTask").disabled = activeJob?.status === "cancelling";
}
async function refresh(sid = selectedSession) {
  const generation = ++stateGeneration;
  const data = await api("/api/state" + (sid ? `?session_id=${encodeURIComponent(sid)}` : ""));
  if (generation !== stateGeneration) return;
  const previousLatest = state?.session.id === data.session.id
    ? state.session.runs.filter(r => r.status === "completed" && r.metrics).at(-1)?.id : null;
  const latest = data.session.runs.filter(r => r.status === "completed" && r.metrics).at(-1);
  if (latest && latest.id !== previousLatest && (!currentRun || currentRun.id === previousLatest)) {
    currentRun = latest; result = null; resultGeneration++;
  }
  state = data; selectedSession = data.session.id;
  const llmOn = data.config.llm.enabled;
  $("modeBadge").textContent = llmOn ? (data.config.llm.backend === "nanobot" ? "Nanobot 工具模式" : "兼容接口模式") : "本地规则模式";
  $("composerMode").textContent = llmOn ? "大模型工具调用 · " + (data.config.llm.model || "待配置模型") : "本地规则 · 可直接建模与仿真";
  $("matlabStatus").classList.toggle("detected", data.environment.installed);
  $("matlabStatus").replaceChildren(node("i"), document.createTextNode(data.environment.installed ? "已检测到 MATLAB" : "未找到 MATLAB"));
  $("matlabStatus").title = data.environment.note;
  renderSessions(); renderSpec(); renderMessages(); renderRuns(); renderFiles();
  activeJob = data.job;
  renderTrace(activeJob?.events || []);
  if (activeJob && busyStates.has(activeJob.status)) watchJob(activeJob.id);
  else { clearTimeout(pollTimer); setBusy(false); }
}
function renderSessions() {
  $("sessions").replaceChildren();
  $("sessionCount").textContent = state.sessions.length;
  for (const session of state.sessions) {
    const button = node("button", "session-item" + (session.id === selectedSession ? " active" : ""));
    button.append(document.createTextNode(session.title), node("small", "", new Date(session.updated_at).toLocaleDateString("zh-CN", {month: "short", day: "numeric"})));
    button.title = session.title;
    button.addEventListener("click", async () => {
      clearTimeout(pollTimer); result = null; currentRun = null; resultGeneration++;
      try { await refresh(session.id); } catch (error) { toast(error.message); }
    });
    $("sessions").append(button);
  }
}
function renderSpec() {
  const s = state.session.spec;
  $("modelStageTag").textContent = stageName(s);
  const cells = [["直流输入", s.input_voltage, "V"], ["交流输出", s.output_voltage, "V"], ["额定功率", s.output_power, "W"],
    ["开关频率", s.switching_frequency / 1000, "kHz"], ["滤波电感", s.inductance * 1000, "mH"], ["滤波电容", s.capacitance * 1e6, "μF"]];
  $("specGrid").replaceChildren(...cells.map(([label, value, unit]) => {
    const el = node("div", "spec-cell"); const strong = node("strong", "", number(value)); strong.append(node("small", "", unit));
    el.append(node("span", "", label), strong); return el;
  }));
  const d = state.derived;
  $("derivedSummary").textContent = `${s.output_frequency} Hz · 调制度 ${number(d.modulation_index, 3)} · 额定负载 ${number(d.load_resistance)} Ω · 修订 ${state.session.revision}` + (s.load_step ? `\n${s.load_step_time} s负载突变 → ${number(s.load_final_ratio * 100)}%额定功率` : "");
}
function renderMessages() {
  const messages = state.session.messages;
  const signature = `${selectedSession}:${messages.length}:${messages.at(-1)?.created_at || ""}`;
  const changed = signature !== messageSignature;
  messageSignature = signature;
  const wasBottom = $("messages").scrollHeight - $("messages").scrollTop - $("messages").clientHeight < 100;
  $("intro").classList.toggle("hidden", messages.length > 0);
  $("messages").replaceChildren(...messages.map(m => {
    const row = node("article", "message " + m.role);
    const avatar = node("div", "message-avatar", m.role === "user" ? "你" : "");
    if (m.role !== "user") avatar.append(icon("wave"));
    const body = node("div", "message-body");
    const role = node("div", "message-role", m.role === "user" ? "你的需求" : "DC/AC Agent");
    role.append(node("time", "", localTime(m.created_at)));
    body.append(role, node("div", "message-content", m.content)); row.append(avatar, body); return row;
  }));
  if (wasBottom || changed) $("messages").scrollTo({top: $("messages").scrollHeight, behavior: "instant"});
}
function renderTrace(events) {
  const signature = `${events.length}:${events.at(-1)?.at || ""}:${events.at(-1)?.title || ""}`;
  if (signature === traceSignature) return;
  traceSignature = signature;
  $("traceCount").textContent = events.filter(e => e.kind === "tool").length;
  $("traceList").replaceChildren();
  if (!events.length) { $("traceList").append(node("div", "empty-small", "发送需求后，查看计划与真实工具调用。")); return; }
  for (const e of events) {
    const row = node("div", "trace-event " + e.kind);
    row.append(node("strong", "", e.title), node("time", "", localTime(e.at, true)));
    if (e.data) {
      const details = node("details");
      details.append(node("summary", "", "查看输入 / 输出"), node("pre", "", JSON.stringify(e.data, null, 2)));
      row.append(details);
    }
    $("traceList").append(row);
  }
}
function renderRuns() {
  const runs = state.session.runs.filter(r => r.status === "completed" && r.metrics);
  $("runSelect").replaceChildren();
  if (!runs.length) {
    $("runSelect").append(new Option("尚无成功的仿真记录", "")); currentRun = null; result = null; renderResult(); return;
  }
  for (const r of [...runs].reverse()) $("runSelect").append(new Option(`${stageName(r.spec)} · 修订 ${r.revision} · ${localTime(r.created_at)} · ${r.id.slice(0, 6)}`, r.id));
  if (!currentRun || !runs.some(r => r.id === currentRun.id)) currentRun = runs[runs.length - 1];
  $("runSelect").value = currentRun.id;
  if (!result || result.run_id !== currentRun.id) loadRun(currentRun.id).catch(e => toast(e.message));
  else renderResult();
}
async function loadRun(rid) {
  const generation = ++resultGeneration;
  const sid = selectedSession;
  const output = await api(`/api/results/${sid}/${rid}`);
  if (generation !== resultGeneration || sid !== selectedSession) return;
  currentRun = state.session.runs.find(r => r.id === rid);
  result = {...output, run_id: rid}; renderResult();
}
function renderResult() {
  renderPhysics();
  const m = result?.metrics;
  const values = m ? [number(m.output_rms), number(m.thd_percent, 3), number(m.inductor_rms, 3)] : ["—", "—", "—"];
  const labels = ["输出电压", "电压 THD", "电感电流"], units = ["Vrms", "%", "Arms"];
  $("metrics").replaceChildren(...values.map((value, i) => {
    const card = node("div", "metric"); const strong = node("strong", "", value); strong.append(node("small", "", " " + units[i])); card.append(node("span", "", labels[i]), strong); return card;
  }));
  $("chartEmpty").classList.toggle("hidden", !!m); $("waveChart").classList.toggle("hidden", !m);
  const stale = !!currentRun && currentRun.revision !== state.session.revision;
  $("staleNotice").classList.toggle("hidden", !stale);
  $("staleNotice").textContent = stale ? `当前参数已是修订${state.session.revision}；下方结果属于修订${currentRun.revision}，请重新仿真验证修改。` : "";
  $("resultSummary").textContent = m ? `${stageName(currentRun?.spec || result?.spec)} · 真实 Simulink 结果 · 输出功率 ${number(m.output_power)} W\n末尾4周期 · THD统计2–40次谐波 · 电压误差 ${m.voltage_error_percent >= 0 ? "+" : ""}${number(m.voltage_error_percent)}%\n单次仿真；本次尚未验证步长收敛` : "末尾4个完整基波周期 · THD统计2–40次谐波";
  requestAnimationFrame(drawChart);
}
function renderFiles() {
  $("fileList").replaceChildren();
  const runs = [...state.session.runs].reverse().filter(r => r.files?.length);
  if (!runs.length) { $("fileList").append(node("div", "empty-small", "建模或仿真后，下载模型、参数与运行日志。")); return; }
  for (const r of runs) {
    $("fileList").append(node("div", "file-group", `${stageName(r.spec)} · 修订 ${r.revision} · ${r.status === "completed" ? "完成" : r.status === "exported" ? "脚本已导出，未运行" : r.status === "cancelled" ? "已取消" : "失败"} · ${localTime(r.created_at)}`));
    for (const file of r.files) {
      const a = node("a", "file-row"); a.href = file.url; a.target = "_blank"; a.rel = "noopener";
      const body = node("div"); body.append(node("strong", "", file.name), node("small", "", file.bytes < 1024 ? `${file.bytes} B` : `${number(file.bytes / 1024, 1)} KB`));
      a.append(icon("file"), body, icon("download")); $("fileList").append(a);
    }
  }
}
function drawChart() {
  if (!result?.waveforms || $("waveChart").classList.contains("hidden")) return;
  const canvas = $("waveChart"), rect = canvas.getBoundingClientRect();
  if (!rect.width) return;
  const ratio = window.devicePixelRatio || 1; canvas.width = Math.round(rect.width * ratio); canvas.height = Math.round(190 * ratio);
  const ctx = canvas.getContext("2d"); ctx.scale(ratio, ratio);
  const w = rect.width, h = 190, pad = {l: 38, r: 9, t: 12, b: 27};
  const time = result.waveforms.time, values = result.waveforms[chartKey];
  const max = Math.max(...values.map(Math.abs)) * 1.12 || 1;
  const x = t => pad.l + (t - time[0]) / (time[time.length - 1] - time[0]) * (w - pad.l - pad.r);
  const y = v => pad.t + (max - v) / (2 * max) * (h - pad.t - pad.b);
  ctx.font = "9px Segoe UI, sans-serif"; ctx.lineWidth = .7;
  for (let i = 0; i <= 4; i++) {
    const v = max * (1 - i / 2), py = y(v); ctx.strokeStyle = "#eaf0e4"; ctx.beginPath(); ctx.moveTo(pad.l, py); ctx.lineTo(w - pad.r, py); ctx.stroke(); ctx.fillStyle = "#a5b298"; ctx.textAlign = "right"; ctx.fillText(number(v, chartKey === "voltage" ? 0 : 1), pad.l - 7, py + 3);
    const t = time[0] + (time[time.length - 1] - time[0]) * i / 4; ctx.textAlign = "center"; ctx.fillText(number(t * 1000, 0), x(t), h - 9);
  }
  ctx.textAlign = "right"; ctx.fillText("ms", w - 1, h - 9);
  ctx.strokeStyle = chartKey === "voltage" ? "#2a8966" : "#688fbd"; ctx.lineWidth = 1.3; ctx.beginPath();
  values.forEach((v, i) => i ? ctx.lineTo(x(time[i]), y(v)) : ctx.moveTo(x(time[i]), y(v))); ctx.stroke();
}
async function watchJob(jid) {
  clearTimeout(pollTimer);
  const sid = selectedSession;
  try {
    const job = await api(`/api/jobs/${jid}`);
    if (sid !== selectedSession) return;
    activeJob = job; setBusy(busyStates.has(job.status)); renderTrace(job.events);
    $("taskLabel").textContent = job.status === "queued" ? "任务排队中" : job.status === "cancelling" ? "正在取消任务…" : job.events.at(-1)?.title || "任务执行中";
    if (busyStates.has(job.status)) pollTimer = setTimeout(() => watchJob(jid), 1200);
    else {
      if (job.result) { result = job.result; currentRun = {id: result.run_id, revision: result.revision}; }
      await refresh(sid);
      if (job.status === "completed" && job.events.some(e => e.kind === "tool" && e.title === "run_multiphysics")) activateTab("results");
      if (job.status === "failed") { activateTab("trace"); toast("任务未完成，请查看执行过程和日志。"); }
    }
  } catch (error) { setBusy(false); toast(error.message); }
}
async function submit(message, action = "chat", updates = undefined) {
  if (!state) return;
  try {
    setBusy(true);
    const job = await api("/api/chat", {session_id: selectedSession, message, action, ...(action === "multiphysics" && currentRun ? {run_id: currentRun.id} : {}), ...(updates ? {updates} : {})});
    $("messageInput").value = "";
    // Refresh session messages, then resume polling through the server-owned job.
    await refresh(selectedSession);
  } catch (error) { setBusy(false); toast(error.message); }
}
function activateTab(tab) {
  for (const button of document.querySelectorAll(".inspector-tab")) {
    const active = button.dataset.tab === tab; button.classList.toggle("active", active); button.setAttribute("aria-selected", String(active));
  }
  for (const name of ["results", "trace", "files"]) $(`${name}Panel`).classList.toggle("hidden", name !== tab);
  $("physicsPanel").classList.toggle("hidden", tab !== "results");
  if (tab === "results") requestAnimationFrame(drawChart);
}
$("chatForm").addEventListener("submit", e => { e.preventDefault(); const text = $("messageInput").value.trim(); if (text) submit(text); });
$("messageInput").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); if (!$("sendButton").disabled) $("chatForm").requestSubmit(); } });
document.querySelectorAll("[data-prompt]").forEach(button => button.addEventListener("click", () => { $("messageInput").value = button.dataset.prompt; $("messageInput").focus(); }));
$("newSession").addEventListener("click", async () => { try { const s = await api("/api/sessions", {}); clearTimeout(pollTimer); result = null; currentRun = null; resultGeneration++; await refresh(s.id); $("messageInput").focus(); } catch(e) { toast(e.message); } });
$("buildButton").addEventListener("click", () => submit("生成当前设计的Simulink模型", "build"));
$("exportButton").addEventListener("click", () => { activateTab("files"); submit("导出建模与仿真脚本，供已打开的MATLAB执行", "export"); });
$("fieldsButton").addEventListener("click", () => { activateTab("trace"); submit("对当前电气运行执行E70候选磁热力分析", "multiphysics"); });
$("simulateButton").addEventListener("click", () => { activateTab("trace"); submit("运行当前设计的真实Simulink仿真", "simulate"); });
$("compareButton").addEventListener("click", () => submit("比较最近两次真实仿真结果", "compare"));
$("cancelTask").addEventListener("click", async () => { if (activeJob) { try { activeJob = await api("/api/cancel", {job_id: activeJob.id}); setBusy(true); } catch(e) { toast(e.message); } } });
$("runSelect").addEventListener("change", () => { if ($("runSelect").value) loadRun($("runSelect").value).catch(e => toast(e.message)); });
document.querySelectorAll(".inspector-tab").forEach(b => b.addEventListener("click", () => activateTab(b.dataset.tab)));
document.querySelectorAll(".chart-toggle").forEach(b => b.addEventListener("click", () => { chartKey = b.dataset.chart; document.querySelectorAll(".chart-toggle").forEach(x => x.classList.toggle("active", x === b)); $("chartTitle").textContent = chartKey === "voltage" ? "输出电压波形" : "电感电流波形"; drawChart(); }));
document.querySelectorAll(".close-dialog").forEach(b => b.addEventListener("click", () => b.closest("dialog").close()));
$("settingsButton").addEventListener("click", () => {
  if (!state) return;
  const c = state.config; $("agentBackend").value = c.llm.backend || "legacy"; $("nanobotStatus").textContent = state.nanobot?.installed ? `已安装 Nanobot ${state.nanobot.version}` : "当前Python未安装Nanobot，规则模式仍可使用。"; $("matlabPath").value = c.matlab_executable; $("llmEnabled").checked = c.llm.enabled; $("llmBase").value = c.llm.base_url; $("llmModel").value = c.llm.model; $("llmKey").value = ""; $("clearKey").checked = false;
  $("llmKey").placeholder = c.llm.has_api_key ? "已配置，留空保留；勾选下方可清除" : "尚未配置";
  $("settingsDialog").showModal();
});
$("settingsForm").addEventListener("submit", async e => {
  e.preventDefault(); try { await api("/api/settings", {matlab_executable: $("matlabPath").value, enabled: $("llmEnabled").checked, backend: $("agentBackend").value, base_url: $("llmBase").value, model: $("llmModel").value, api_key: $("llmKey").value, clear_api_key: $("clearKey").checked}); $("llmKey").value = ""; $("settingsDialog").close(); await refresh(); toast("设置已保存到本机。"); } catch(error) { toast(error.message); }
});
$("editSpec").addEventListener("click", () => {
  $("modelStage").replaceChildren(...Object.entries(state.model_stages || {[baselineStage]: "基础开环模型"}).map(([key, label]) => new Option(label, key)));
  $("modelStage").value = state.session.spec.model_fidelity || baselineStage;
  $("specFields").replaceChildren(...parameterFields.map(([key, label, scale, min, max]) => {
    const field = node("label", "", label); const input = node("input"); input.type = "number"; input.id = "param-" + key; input.step = "any"; input.min = min; input.max = max; input.required = true; input.value = Number((state.session.spec[key] / scale).toPrecision(10)); field.append(input); return field;
  }));
  $("loadStep").checked = state.session.spec.load_step; $("specDialog").showModal();
});
$("specForm").addEventListener("submit", async e => {
  e.preventDefault(); const updates = {};
  for (const [key, label, scale] of parameterFields) updates[key] = Number($("param-" + key).value) * scale;
  updates.load_step = $("loadStep").checked;
  updates.model_fidelity = $("modelStage").value;
  $("specDialog").close(); await submit("更新设计参数（参数面板）", "parameters", updates);
});
window.addEventListener("resize", drawChart);
refresh().catch(error => toast("连接本机服务失败：" + error.message));

function renderPhysics() {
  const panel = $("physicsPanel"); panel.replaceChildren(node("strong", "", "磁 · 热 · 力结果交接"));
  const items = (state.multiphysics || []).filter(item => (item.parent_run_id || item.run_id) === currentRun?.id);
  if (!items.length) { panel.append(node("p", "", "此电气运行尚无磁热力结果。点击“运行磁热力分析”执行E70候选求解。")); return; }
  const domainNames = {magnetic: "磁场", thermal: "温度场", structural: "热应力与位移"};
  const metricNames = {candidate_inductance:"候选电感", bulk_peak_flux_density:"中心柱峰值磁密", peak_temperature:"最高温度", candidate_dc_copper_heat:"候选直流铜热", specified_core_heat:"指定磁芯热", specified_extra_winding_heat:"指定额外绕组热", max_displacement:"最大位移", core_probe_tensile_stress:"磁芯探针拉应力"};
  for (const item of items) {
    if (["running", "failed", "cancelled", "invalid"].includes(item.status)) {
      panel.append(node("p", "", `${{running:"求解中",failed:"求解失败",cancelled:"已取消",invalid:"结果无效"}[item.status]}：${item.message || "请查看执行过程"}`));
      continue;
    }
    if (item.input_summary) {
      const x = item.input_summary, o = x.options;
      panel.append(node("p", "", `E70候选 · 单向耦合 · L差异 ${number(x.L_difference_percent)}% · R20差异 ${number(x.R_difference_percent)}%`));
      panel.append(node("p", "", `环境 ${o.ambient_c}°C；h=${o.convection_w_m2k} W/(m²·K)；指定额外绕组热 ${o.extra_winding_heat_w} W、磁芯热 ${o.core_heat_w} W。未回填电路L/R；本次未验证网格/电气步长收敛。`));
    }
    panel.append(node("p", "", item.status === "invalid" ? `结果被拒绝：${item.message}` : `运行 ${item.parent_run_id} · 修订 ${item.revision} · ${item.evidence === "test" ? "测试数据，不作为课程结论" : item.evidence === "numerical" ? "数值求解（生产者声明）" : "解析计算"}${item.stale ? " · 已过期" : ""}`));
    for (const [domain, data] of Object.entries(item.domains || {})) {
      panel.append(node("p", "", `${domainNames[domain] || domain} · ${data.status === "completed" ? "已完成" : data.status}`));
      for (const [key, metric] of Object.entries(data.metrics || {})) {
        const scales = {H:[1000,"mH"],m:[1e6,"μm"],Pa:[1e-6,"MPa"],degC:[1,"°C"]};
        const [scale, unit] = scales[metric.unit] || [1, metric.unit];
        panel.append(node("div", "", `${metricNames[key] || key}: ${number(metric.value * scale, 4)} ${unit}`));
      }
      for (const file of data.files || []) {
        const link = node("a", "file-row", file.name); link.href = file.url; link.target = "_blank"; link.rel = "noopener"; panel.append(link);
        if (file.image) { const img = node("img", "physics-image"); img.src = file.url; img.alt = `${domain} ${file.name}`; panel.append(img); }
      }
    }
  }
}
