import assert from 'node:assert/strict';
import path from 'node:path';

export function smokeEnvironment(temporary, parent = process.env, platform = process.platform) {
  let appdata = temporary;
  if (platform === 'win32' && parent.STUD_SIGNED_UPDATE_CONFIG) {
    assert.equal(parent.GITHUB_ACTIONS, 'true', 'Windows update smoke requires disposable hosted CI');
    assert.equal(parent.RUNNER_ENVIRONMENT, 'github-hosted');
    assert.ok(parent.APPDATA, 'Windows installer ApplicationData must be available');
    // NSIS resolves $APPDATA through the Windows known-folder API. The launcher
    // must use that same namespace while NSIS holds its installation lock.
    appdata = parent.APPDATA;
  }
  return { ...parent, HOME: temporary, APPDATA: appdata,
    LOCALAPPDATA: temporary, STUD_DATA_DIR: path.join(temporary, 'catalog'),
    PATH: platform === 'win32' ? `${parent.SystemRoot}\\System32` : '/usr/bin:/bin',
    PYTHONHOME: '/invalid-python', PYTHONPATH: '/invalid-python' };
}
