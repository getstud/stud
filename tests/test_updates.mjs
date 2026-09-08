import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';
const source = await fs.readFile(new URL('../web/updates.js', import.meta.url), 'utf8');

test('viewer notice handles availability, dismissal, a later release, and offline checks', async () => {
  const elements = Object.fromEntries(['update-notice', 'update-title', 'update-release', 'update-dismiss'].map(id => [id, {hidden: true}]));
  let update = {available: true, version: '1.1.0', url: 'https://github.com/owner/stud/releases/latest'};
  let poll;
  let offline = false;
  const storage = new Map();
  const context = vm.createContext({URL, AbortSignal,
    document: {getElementById: id => elements[id], addEventListener() {}},
    sessionStorage: {getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value)},
    setInterval: callback => { poll = callback; },
    fetch: async () => { if (offline) throw Error('offline'); return {ok: true, json: async () => update}; }
  });
  vm.runInContext(source, context);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(elements['update-notice'].hidden, false);
  assert.equal(elements['update-title'].textContent, 'stud 1.1.0 is available');
  elements['update-dismiss'].onclick();
  await poll();
  assert.equal(elements['update-notice'].hidden, true);
  update = {...update, version: '1.2.0'};
  await poll();
  assert.equal(elements['update-notice'].hidden, false);
  offline = true;
  await poll();
  assert.equal(elements['update-title'].textContent, 'stud 1.2.0 is available');
});
