import fs from 'node:fs/promises';
import { pathToFileURL } from 'node:url';

// Restrict published versions to the two supported channels.
export function releaseVersion(version) {
  const match = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-preview\.(0|[1-9]\d*))?$/.exec(version || '');
  if (!match) throw new Error('Release version must be X.Y.Z or X.Y.Z-preview.N');
  return { version, channel: match[4] === undefined ? 'stable' : 'preview', parts: match.slice(1).map(v => v === undefined ? Infinity : BigInt(v)) };
}

export function compareVersions(a, b) {
  const left = releaseVersion(a).parts;
  const right = releaseVersion(b).parts;
  for (let i = 0; i < left.length; i++) {
    if (left[i] !== right[i]) return left[i] > right[i] ? 1 : -1;
  }
  return 0;
}

export function channelPath(channel = 'stable') {
  if (channel === 'stable') return 'latest/download';
  if (channel === 'preview') return 'download/channel-preview';
  throw new Error('Release channel must be stable or preview');
}

export async function verifyRelease(tag) {
  const pkg = JSON.parse(await fs.readFile('package.json', 'utf8'));
  const release = releaseVersion(pkg.version);
  if (tag !== `v${pkg.version}`) throw new Error('Tag must match package.json version');
  for (const file of ['src-tauri/Cargo.toml', 'desktop/launcher/Cargo.toml']) {
    const manifest = await fs.readFile(file, 'utf8');
    const version = manifest.match(/^version\s*=\s*"([^"]+)"/m)?.[1];
    if (version !== pkg.version) throw new Error(`${file} version must match package.json`);
  }
  return release;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const release = await verifyRelease(process.env.GITHUB_REF_NAME);
  if (process.env.GITHUB_OUTPUT) await fs.appendFile(process.env.GITHUB_OUTPUT, `channel=${release.channel}\n`);
  console.log(`Validated ${release.channel} release ${release.version}`);
}
