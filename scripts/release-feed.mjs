import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';
import { releaseVersion, compareVersions } from './release-channel.mjs';

const platforms = ['darwin-aarch64', 'darwin-x86_64', 'windows-x86_64'];
export function validateFeed(feed, tag, repository) {
  const release = releaseVersion(tag.replace(/^v/, ''));
  if (feed.version !== release.version) throw new Error('Feed version does not match release tag');
  for (const platform of platforms) {
    const entry = feed.platforms?.[platform];
    if (!entry?.signature?.trim() || !entry.url?.startsWith(`https://github.com/${repository}/releases/download/${tag}/`)) {
      throw new Error(`Missing or invalid signed update for ${platform}`);
    }
  }
  return release;
}

export async function publishFeed(mode, tag, { repository = process.env.GITHUB_REPOSITORY, execute = execFileSync } = {}) {
  if (!['invalidate', 'ready', 'preview'].includes(mode) || !tag?.startsWith('v')) throw new Error('Usage: release-feed.mjs invalidate|ready|preview vX.Y.Z[-preview.N]');
  if (!/^[\w.-]+\/[\w.-]+$/.test(repository || '')) throw new Error('GITHUB_REPOSITORY is required');
  const gh = (...args) => execute('gh', [...args, '--repo', repository], { encoding: 'utf8' });
  if (mode === 'invalidate') {
    const release = releaseVersion(tag.slice(1));
    const releases = JSON.parse(execute('gh', ['api', '--paginate', '--slurp', `repos/${repository}/releases`], { encoding: 'utf8' })).flat();
    const existing = releases.find(r => r.tag_name === tag);
    if (existing) {
      if (!existing.draft) throw new Error('Published releases cannot be rebuilt; use a new version');
      if (existing.assets.some(a => a.name === 'release-ready.json')) gh('release', 'delete-asset', tag, 'release-ready.json', '--yes');
    } else {
      // The tag already exists. Omit a raw target SHA so GitHub need not create
      // a new ref or request workflow-writing permission for release creation.
      gh('release', 'create', tag, '--verify-tag', '--draft', ...(release.channel === 'preview' ? ['--prerelease'] : []), '--title', `stud ${tag}`, '--notes', 'Installers are being built and tested. Do not publish before release-ready.json is attached.');
    }
    return;
  }
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'stud-feed-'));
  try {
    const info = JSON.parse(gh('release', 'view', tag, '--json', 'isDraft,isPrerelease'));
    gh('release', 'download', tag, '--pattern', 'latest.json', '--dir', dir);
    const feedBytes = await fs.readFile(path.join(dir, 'latest.json'));
    const digest = createHash('sha256').update(feedBytes).digest('hex');
    const feed = JSON.parse(feedBytes);
    const release = validateFeed(feed, tag, repository);
    if (info.isPrerelease !== (release.channel === 'preview')) throw new Error('GitHub prerelease flag does not match channel');
    if (mode === 'ready') {
      if (!info.isDraft) throw new Error('Builds must target an unpublished draft');
      const marker = path.join(dir, 'release-ready.json');
      await fs.writeFile(marker, JSON.stringify({ version: release.version, sha256: digest, run: process.env.GITHUB_RUN_ID }));
      gh('release', 'upload', tag, marker, '--clobber');
      return;
    }
    if (info.isDraft || release.channel !== 'preview') throw new Error('Preview feed requires a published preview release');
    gh('release', 'download', tag, '--pattern', 'release-ready.json', '--dir', dir);
    const marker = JSON.parse(await fs.readFile(path.join(dir, 'release-ready.json'), 'utf8'));
    if (marker.version !== feed.version || marker.sha256 !== digest) throw new Error('Release has not passed the build and smoke tests');
    const releases = JSON.parse(execute('gh', ['api', '--paginate', '--slurp', `repos/${repository}/releases`], { encoding: 'utf8' })).flat();
    const existing = releases.find(r => r.tag_name === 'channel-preview');
    if (existing) {
      if (existing.draft || !existing.prerelease) throw new Error('channel-preview must be a published prerelease');
      if (existing.assets.some(a => a.name === 'latest.json')) {
        const oldDir = path.join(dir, 'previous');
        await fs.mkdir(oldDir);
        gh('release', 'download', 'channel-preview', '--pattern', 'latest.json', '--dir', oldDir);
        const previous = JSON.parse(await fs.readFile(path.join(oldDir, 'latest.json'), 'utf8'));
        if (compareVersions(feed.version, previous.version) < 0) {
          console.log('Older preview publication ignored; feed already points to a newer version.');
          return;
        }
      }
    } else {
      gh('release', 'create', 'channel-preview', '--prerelease', '--latest=false', '--title', 'stud preview update feed', '--notes', 'Update metadata for preview installations. Download installers from the versioned preview releases.');
    }
    gh('release', 'upload', 'channel-preview', path.join(dir, 'latest.json'), '--clobber');
    console.log(`Preview feed now serves ${feed.version}`);
  } finally {
    await fs.rm(dir, { recursive: true, force: true });
  }
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await publishFeed(...process.argv.slice(2));
