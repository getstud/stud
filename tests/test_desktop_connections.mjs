import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs/promises';
const source = await fs.readFile(new URL('../desktop/ui/app.js', import.meta.url), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
async function desktop(initial, repair = async () => 'Connected') {
  let connections = initial;
  const calls = [], events = {}, elements = new Map();
  const get = id => {
    if (!elements.has(id)) elements.set(id, { textContent: '', disabled: false, hidden: false,
      events: {}, classList: { toggle() {} }, addEventListener(name, fn) { this.events[name] = fn; }, replaceChildren() {} });
    return elements.get(id);
  };
  const invoke = async name => {
    calls.push(name);
    if (name === 'status') return { version: '1.0.0-preview.7', python: 'Python 3', updatesConfigured: true, connections };
    if (name === 'list_projects') return [];
    if (name === 'repair_connections') return repair(value => { connections = value; });
    if (name === 'check_update') return null;
  };
  vm.runInNewContext(source, { document: { getElementById: get },
    window: { __TAURI__: { core: { invoke } }, addEventListener(name, fn) { events[name] = fn; } }, setInterval() {} });
  await tick();
  return { get, calls, events, set: value => { connections = value; } };
}
const state = (cli, skill) => ({ cli, skill, skill_path: '/a/skills/stud-design' });
test('latest app still reports stale CLI and offers repair', async () => {
  const app = await desktop(state('stale', 'connected'));
  assert.match(app.get('update-message').textContent, /latest version/);
  assert.equal(app.get('cli-state').textContent, 'Repair needed');
  assert.equal(app.get('install-cli').textContent, 'Repair connections');
  assert.equal(app.get('install-cli').disabled, false);
});
test('missing setup connects both tools and verifies refreshed status', async () => {
  const app = await desktop(state('missing', 'missing'), async set => { set(state('connected', 'connected')); return 'Done'; });
  await app.get('install-cli').events.click();
  assert.ok(app.calls.includes('repair_connections'));
  assert.equal(app.get('cli-state').textContent, 'Connected');
  assert.equal(app.get('install-cli').disabled, true);
});
test('custom connections are explained and cannot be overwritten from setup', async () => {
  const app = await desktop(state('connected', 'conflict'));
  assert.equal(app.get('cli-state').textContent, 'Needs attention');
  assert.match(app.get('connection-help').textContent, /will not overwrite/);
  assert.equal(app.get('install-cli').disabled, true);
});
test('cancelled repair refreshes partial state and can be retried', async () => {
  const app = await desktop(state('stale', 'missing'), async set => { set(state('connected', 'missing')); throw new Error('Skill permission denied'); });
  await app.get('install-cli').events.click();
  assert.match(app.get('cli-message').textContent, /permission denied/);
  assert.match(app.get('connection-details').textContent, /CLI: Connected to this app. Skill: Not installed/);
  assert.equal(app.get('install-cli').disabled, false);
});
test('focus rechecks connections and repair suppresses duplicate clicks', async () => {
  let done;
  const app = await desktop(state('missing', 'missing'), () => new Promise(resolve => { done = resolve; }));
  const pending = app.get('install-cli').events.click();
  await app.get('install-cli').events.click();
  assert.equal(app.calls.filter(name => name === 'repair_connections').length, 1);
  done('Done'); await pending;
  app.set(state('connected', 'connected')); app.events.focus(); await tick();
  assert.equal(app.get('cli-state').textContent, 'Connected');
});

test('connection inspection errors do not hide app version or disable updates', async () => {
  const app = await desktop({ ...state('error', 'error'), error: 'Permission denied' });
  assert.match(app.get('version').textContent, /preview.7/);
  assert.match(app.get('update-message').textContent, /latest version/);
  assert.match(app.get('connection-help').textContent, /Permission denied/);
  assert.equal(app.get('install-cli').disabled, true);
});
