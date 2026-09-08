import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs/promises';

const source = await fs.readFile(new URL('../desktop/ui/app.js', import.meta.url), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
async function desktop(add) {
  const elements = new Map();
  const element = () => ({ textContent: '', disabled: false, children: [], events: {},
    classList: { toggle() {} }, addEventListener(name, handler) { this.events[name] = handler; },
    replaceChildren() { this.children = []; }, append(...children) { this.children.push(...children); } });
  const get = id => { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); };
  let rows = [];
  let additions = 0;
  const invoke = async name => {
    if (name === 'status') return { python: 'Python 3', updatesConfigured: false };
    if (name === 'list_projects') return rows;
    if (name === 'add_project') {
      additions++;
      const result = await add();
      if (result) rows = [{ name: 'Bench', path: '/a project/bench', available: true }];
      return result;
    }
  };
  vm.runInNewContext(source, {
    document: { getElementById: get, createElement: element },
    window: { __TAURI__: { core: { invoke } }, addEventListener() {} }, setInterval() {},
  });
  await tick();
  return { get, additions: () => additions };
}

test('Add project refreshes the list after a folder is accepted', async () => {
  const app = await desktop(async () => true);
  await app.get('add-project').events.click();
  assert.equal(app.get('project-list').children[0].children[0].textContent, 'Bench');
  assert.equal(app.get('add-project').disabled, false);
});
test('Cancel preserves the list and message', async () => {
  const app = await desktop(async () => false);
  const message = app.get('projects-message').textContent;
  await app.get('add-project').events.click();
  assert.equal(app.get('projects-message').textContent, message);
  assert.equal(app.get('project-list').children.length, 0);
});
test('Errors are shown and another add can be attempted', async () => {
  const app = await desktop(async () => { throw new Error('No design.py found'); });
  await app.get('add-project').events.click();
  assert.match(app.get('projects-message').textContent, /No design.py found/);
  assert.equal(app.get('add-project').disabled, false);
});
test('Repeated clicks cannot open multiple pickers', async () => {
  let resolve;
  const app = await desktop(() => new Promise(done => { resolve = done; }));
  const pending = app.get('add-project').events.click();
  await app.get('add-project').events.click();
  assert.equal(app.additions(), 1);
  resolve(false);
  await pending;
});
