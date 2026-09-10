import { test } from 'node:test';
import assert from 'node:assert/strict';
import { smokeEnvironment } from '../scripts/smoke-environment.mjs';

test('only disposable Windows signed-update probes share the installer lock namespace', () => {
  const parent = { APPDATA: 'C:\\Users\\runner\\AppData\\Roaming', SystemRoot: 'C:\\Windows',
    GITHUB_ACTIONS: 'true', RUNNER_ENVIRONMENT: 'github-hosted', STUD_SIGNED_UPDATE_CONFIG: 'probe.json' };
  const actual = smokeEnvironment('/isolated', parent, 'win32');
  assert.equal(actual.APPDATA, parent.APPDATA);
  assert.equal(actual.HOME, '/isolated');
  assert.equal(actual.LOCALAPPDATA, '/isolated');
  assert.notEqual(actual.STUD_DATA_DIR, parent.APPDATA);
  assert.equal(smokeEnvironment('/isolated', { ...parent, STUD_SIGNED_UPDATE_CONFIG: '' }, 'win32').APPDATA, '/isolated');
  assert.equal(smokeEnvironment('/isolated', parent, 'darwin').APPDATA, '/isolated');
});

test('sharing Windows installer ApplicationData fails closed outside hosted CI', () => {
  const parent = { APPDATA: 'C:\\Users\\runner\\AppData\\Roaming', GITHUB_ACTIONS: 'true',
    RUNNER_ENVIRONMENT: 'github-hosted', STUD_SIGNED_UPDATE_CONFIG: 'probe.json' };
  for (const override of [{ GITHUB_ACTIONS: '' }, { RUNNER_ENVIRONMENT: 'self-hosted' }, { APPDATA: '' }]) {
    assert.throws(() => smokeEnvironment('/isolated', { ...parent, ...override }, 'win32'));
  }
});
