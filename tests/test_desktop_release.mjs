import { test } from 'node:test';
import assert from 'node:assert/strict';
import { releaseConfig } from '../scripts/release-config.mjs';

test('release config rejects missing repository and signing public key', () => {
  assert.throws(() => releaseConfig('', ''), /repository/);
  assert.throws(() => releaseConfig('team/stud', ''), /PUBLIC_KEY/);
});
test('release config pins signature verification and HTTPS GitHub endpoint', () => {
  const bytes = Buffer.alloc(42); bytes.write('Ed');
  const key = Buffer.from(`untrusted comment: test key\n${bytes.toString('base64')}\n`).toString('base64');
  const config = releaseConfig('team/stud', key);
  assert.equal(config.bundle.createUpdaterArtifacts, true);
  assert.equal(config.plugins.updater.pubkey, key);
  assert.deepEqual(config.plugins.updater.endpoints, ['https://github.com/team/stud/releases/latest/download/latest.json']);
  assert.equal(config.plugins.updater.dangerousInsecureTransportProtocol, undefined);
});
