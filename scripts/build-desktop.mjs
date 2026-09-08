import fs from 'node:fs/promises';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { releaseVersion } from './release-channel.mjs';
import { releaseConfig } from './release-config.mjs';

const dev = process.argv.includes('--dev');
const release = process.argv.includes('--release');
const configIndex = process.argv.indexOf('--config');
const targetIndex = process.argv.indexOf('--target');
const target = targetIndex >= 0 ? process.argv[targetIndex + 1] : `${process.platform}-${process.arch}`;
const triples = { 'darwin-arm64': 'aarch64-apple-darwin', 'darwin-x64': 'x86_64-apple-darwin', 'win32-x64': 'x86_64-pc-windows-msvc' };
const rustTargetIndex = process.argv.indexOf('--rust-target');
const triple = rustTargetIndex >= 0 ? process.argv[rustTargetIndex + 1] : triples[target];
if (rustTargetIndex >= 0 && !(target === 'win32-x64' && triple === 'x86_64-pc-windows-gnu')) throw new Error('Only the Windows GNU cross-build override is supported');
if (!triple) throw new Error(`Unsupported target ${target}`);
function run(command, args, options = {}) {
  const result = spawnSync(command, args, { stdio: 'inherit', ...options });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}
const overrides = {};
if (release) {
  const configPath = configIndex >= 0 ? process.argv[configIndex + 1] : 'desktop/release.local.json';
  const settings = JSON.parse(await fs.readFile(configPath));
  if (!process.env.TAURI_SIGNING_PRIVATE_KEY) throw new Error('TAURI_SIGNING_PRIVATE_KEY is required for a release');
  const pkg = JSON.parse(await fs.readFile('package.json'));
  const channel = releaseVersion(pkg.version).channel;
  if (settings.channel && settings.channel !== channel) throw new Error('Release channel must match package.json version');
  Object.assign(overrides, releaseConfig(settings.repository, settings.publicKey, channel));
  process.env.STUD_RELEASE_CHANNEL = channel;
  process.env.STUD_RELEASE_REPOSITORY = settings.repository;
}
run(process.execPath, ['scripts/prepare-desktop.mjs', target]);
run('cargo', ['build', '--manifest-path', 'desktop/launcher/Cargo.toml', '--release', '--target', triple]);
await fs.mkdir('src-tauri/binaries', { recursive: true });
const ext = target.startsWith('win32') ? '.exe' : '';
await fs.copyFile(`desktop/launcher/target/${triple}/release/stud${ext}`, `src-tauri/binaries/stud-${triple}${ext}`);
if (process.argv.includes('--stage-only')) process.exit(0);
if (release && target.startsWith('darwin')) run(process.execPath, ['scripts/sign-macos-runtime.mjs']);
const args = [dev ? 'dev' : 'build', '--target', triple];
if (!dev) args.push('--bundles', target.startsWith('darwin') ? 'app,dmg' : 'nsis');
if (release) args.push('--config', JSON.stringify(overrides));
// Call the JS CLI directly, avoiding cmd.exe argument re-parsing on Windows.
run(process.execPath, [path.resolve('node_modules/@tauri-apps/cli/tauri.js'), ...args]);
