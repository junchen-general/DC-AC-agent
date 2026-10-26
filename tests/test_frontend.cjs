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
    createElement: element, createTextNode: text => ({textContent: text}), querySelectorAll: () => []}});
vm.runInContext(fs.readFileSync('dcac_agent/web/app.js', 'utf8'), context);
vm.runInContext(`
(async () => {
  activateTab('trace'); assert.equal($('physicsPanel').classList.contains('hidden'), true);
  activateTab('results'); assert.equal($('physicsPanel').classList.contains('hidden'), false);
  currentRun = {id: 'new'};
  state = {multiphysics: [{parent_run_id:'old', revision:1, domains:{}},
                         {parent_run_id:'new', revision:2, domains:{}}]};
  renderPhysics();
  assert.equal($('physicsPanel').children.length, 2);
  assert.match($('physicsPanel').children[1].textContent, /new/);
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
