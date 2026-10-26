// State regressions using the real frontend functions; no browser dependencies.
const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const elements = new Map();
function element() {
  const classes = new Set();
  return {children: [], classList: {toggle(k, on) {on ? classes.add(k) : classes.delete(k);},
    contains(k) {return classes.has(k);}},
    append(...xs) {this.children.push(...xs);}, replaceChildren(...xs) {this.children = xs;},
    addEventListener() {}, setAttribute() {}};
}
const context = vm.createContext({assert, console, setTimeout, clearTimeout,
  fetch: () => new Promise(() => {}), requestAnimationFrame() {},
  window: {addEventListener() {}},
  document: {getElementById(id) {if (!elements.has(id)) elements.set(id, element()); return elements.get(id);},
    createElement: tag => Object.assign(element(), {tagName:tag.toUpperCase()}), createTextNode: text => ({textContent: text}), querySelectorAll: () => []}});
vm.runInContext(fs.readFileSync('dcac_agent/web/app.js', 'utf8'), context);
vm.runInContext(`
(async () => {
  const precision = precisionSummary({solver:{steps_per_switching_period:800,fixed_step_s:6.25e-8},
    metrics:{analysis_start:.16,analysis_end_exclusive:.24}});
  assert.match(precision,/800/); assert.match(precision,/0.16/); assert.match(precision,/尚未/);
  assert.doesNotMatch(precisionSummary({}),/undefined|NaN/);
  const rich = document.createElement('div');
  appendRichText(rich,'**结论** <img src=x onerror=alert(1)> [坏链接](javascript:alert(1))');
  const descendants = n => [n,...(n.children || []).flatMap(descendants)];
  const nodes = descendants(rich);
  assert.ok(nodes.some(n => n.tagName==='STRONG'));
  assert.ok(!nodes.some(n => ['IMG','SCRIPT','IFRAME'].includes(n.tagName)));
  assert.ok(!nodes.some(n => n.href?.startsWith('javascript:')));
  activateTab('trace'); assert.equal($('physicsPanel').classList.contains('hidden'), true);
  activateTab('results'); assert.equal($('physicsPanel').classList.contains('hidden'), false);
  currentRun = {id: 'new'};
  state = {multiphysics: [{parent_run_id:'old', revision:1, domains:{}},
                         {parent_run_id:'new', revision:2, domains:{}}]};
  renderPhysics();
  assert.equal($('physicsPanel').children.length, 2);
  assert.match($('physicsPanel').children[1].textContent, /new/);
  state.multiphysics=[{parent_run_id:'new',revision:2,status:'completed',evidence:'numerical',domains:{},
    input_summary:{L_difference_percent:0,R_difference_percent:0,options:{ambient_c:40,convection_w_m2k:10,extra_winding_heat_w:.5,core_heat_w:.5}}}];
  renderPhysics();
  assert.ok(!$('physicsPanel').children.some(n => /未回填电路/.test(n.textContent || '')));
  const run = id => ({id, status:'completed', metrics:{output_rms:220}});
  const data = ids => ({session:{id:'session', runs:ids.map(run)}, config:{llm:{enabled:false}}, environment:{installed:false}});
  // Isolate rendering while exercising refresh selection and request handling.
  renderSessions = renderSpec = renderMessages = renderRuns = renderFiles = renderTrace = () => {};
  state = data(['old']); currentRun = run('old'); result = {run_id:'old'};
  api = async () => data(['old','new']);
  await refresh('session'); assert.equal(currentRun.id, 'new'); assert.equal(result, null);
  state = data(['old','new']); currentRun = run('old'); result = {run_id:'old'};
  api = async () => data(['old','new','newest']);
  await refresh('session'); assert.equal(currentRun.id, 'old');
  console.log('Frontend state regressions passed');
})()
`, context).catch(error => {console.error(error); process.exitCode = 1;});
