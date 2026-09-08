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

import { releaseVersion, compareVersions, verifyRelease } from '../scripts/release-channel.mjs';
import { validateFeed } from '../scripts/release-feed.mjs';

test('stable and preview builds use separate HTTPS feeds', () => {
  const bytes = Buffer.alloc(42); bytes.write('Ed');
  const key = Buffer.from(`untrusted comment: test key\n${bytes.toString('base64')}\n`).toString('base64');
  assert.deepEqual(releaseConfig('team/stud', key, 'preview').plugins.updater.endpoints,
    ['https://github.com/team/stud/releases/download/channel-preview/latest.json']);
  assert.throws(() => releaseConfig('team/stud', key, 'nightly'), /channel/);
});

test('versions classify channels and order previews numerically', () => {
  assert.equal(releaseVersion('1.0.0').channel, 'stable');
  assert.equal(releaseVersion('1.0.0-preview.1').channel, 'preview');
  for (const version of ['1.0', '1.0.0-rc.1', '1.0.0-preview.01', 'v1.0.0', '1.0.0+build']) {
    assert.throws(() => releaseVersion(version), /version/);
  }
  assert.equal(compareVersions('1.0.0-preview.10', '1.0.0-preview.9'), 1);
  assert.equal(compareVersions('1.0.0', '1.0.0-preview.10'), 1);
  assert.equal(compareVersions('1.0.0-preview.1', '1.1.0-preview.1'), -1);
  assert.equal(compareVersions('1.0.0', '1.0.0'), 0);
});

test('release tags must match the package version', async () => {
  await assert.rejects(verifyRelease('v999.0.0'), /Tag must match/);
});

test('channel publication requires complete signed artifacts for the exact release', () => {
  const tag = 'v1.2.0-preview.1';
  const feed = { version: '1.2.0-preview.1', platforms: Object.fromEntries(
    ['darwin-aarch64', 'darwin-x86_64', 'windows-x86_64'].map(platform =>
      [platform, { signature: 'signed', url: `https://github.com/team/stud/releases/download/${tag}/${platform}.zip` }])) };
  assert.equal(validateFeed(feed, tag, 'team/stud').channel, 'preview');
  assert.throws(() => validateFeed(feed, 'v1.2.0-preview.2', 'team/stud'), /version/);
  const partial = structuredClone(feed);
  delete partial.platforms['windows-x86_64'];
  assert.throws(() => validateFeed(partial, tag, 'team/stud'), /windows/);
  const foreign = structuredClone(feed);
  foreign.platforms['darwin-aarch64'].url = 'https://example.com/update';
  assert.throws(() => validateFeed(foreign, tag, 'team/stud'), /darwin/);
});

import { publishFeed } from '../scripts/release-feed.mjs';
import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';

test('failed rebuild cannot promote the readiness marker from a previous success', async () => {
  const tag = 'v1.2.0-preview.1';
  const feed = { version: tag.slice(1), platforms: Object.fromEntries(
    ['darwin-aarch64', 'darwin-x86_64', 'windows-x86_64'].map(platform =>
      [platform, { signature: 'signed', url: `https://github.com/team/stud/releases/download/${tag}/${platform}.zip` }])) };
  const assets = new Map([['latest.json', JSON.stringify(feed)]]);
  let draft = true;
  const execute = (command, args) => {
    assert.equal(command, 'gh');
    if (args[0] === 'api') return JSON.stringify([[{ tag_name: tag, draft, prerelease: true, assets: [...assets.keys()].map(name => ({ name })) }]]);
    if (args[1] === 'view') return JSON.stringify({ isDraft: draft, isPrerelease: true });
    if (args[1] === 'download') {
      const name = args[args.indexOf('--pattern') + 1];
      if (!assets.has(name)) throw new Error(`Missing asset: ${name}`);
      writeFileSync(path.join(args[args.indexOf('--dir') + 1], name), assets.get(name));
    } else if (args[1] === 'upload') {
      assert.equal(args[2], tag); // No feed may be promoted in this test.
      assets.set(path.basename(args[3]), readFileSync(args[3], 'utf8'));
    } else if (args[1] === 'delete-asset') assets.delete(args[3]);
    else throw new Error(`Unexpected gh command: ${args.join(' ')}`);
    return '';
  };
  const options = { repository: 'team/stud', execute };
  await publishFeed('ready', tag, options);
  assert.ok(assets.has('release-ready.json'));
  // A modified manifest with the same version must not reuse readiness.
  draft = false;
  assets.set('latest.json', JSON.stringify({ ...feed, notes: 'rebuilt' }));
  await assert.rejects(publishFeed('preview', tag, options), /not passed/);
  // Invalidation happens before a rerun; a subsequent failed build leaves no marker.
  draft = true;
  await publishFeed('invalidate', tag, options);
  assert.equal(assets.has('release-ready.json'), false);
  draft = false;
  await assert.rejects(publishFeed('preview', tag, options), /Missing asset: release-ready/);
  await assert.rejects(publishFeed('invalidate', tag, options), /cannot be rebuilt/);
});
