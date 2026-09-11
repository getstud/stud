import fs from 'node:fs/promises';
import { copyDesignResources } from './design-resources.mjs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const target = process.argv[2] || `${process.platform}-${process.arch}`;
const runtimes = JSON.parse(await fs.readFile(path.join(root, 'desktop/runtimes.json')));
const runtime = runtimes[target];
if (!runtime) throw new Error(`Unsupported desktop target: ${target}`);
if (target !== `${process.platform}-${process.arch}`) throw new Error('Stage CadQuery on the matching native macOS or Windows runner.');
const cache = path.join(root, '.desktop-cache', target);
const resources = path.join(root, 'src-tauri/resources');
await fs.mkdir(cache, { recursive: true });
const archive = path.join(cache, 'python.tar.gz');
const digest = data => crypto.createHash('sha256').update(data).digest('hex');
let archiveData = await fs.readFile(archive).catch(() => null);
if (!archiveData || digest(archiveData) !== runtime.sha256) {
  console.log(`Downloading bundled Python for ${target}…`);
  const response = await fetch(runtime.url);
  if (!response.ok) throw new Error(`Python download failed: ${response.status}`);
  archiveData = Buffer.from(await response.arrayBuffer());
  if (digest(archiveData) !== runtime.sha256) throw new Error('Python archive checksum mismatch');
  await fs.writeFile(archive, archiveData);
}
// Re-extract the verified archive so cache edits never reach a release.
const extracted = path.join(cache, 'extracted');
await fs.rm(extracted, { recursive: true, force: true });
await fs.mkdir(extracted, { recursive: true });
const untar = spawnSync('tar', ['-xzf', archive, '-C', extracted], { stdio: 'inherit' });
if (untar.status !== 0) throw new Error('Could not extract bundled Python');
await fs.rm(resources, { recursive: true, force: true });
await fs.mkdir(resources, { recursive: true });
await fs.cp(path.join(extracted, 'python'), path.join(resources, 'runtime'), { recursive: true, verbatimSymlinks: true });
const python = path.join(resources, process.platform === 'win32' ? 'runtime/python.exe' : 'runtime/bin/python3');
if (process.platform === 'darwin') {
  // NumPy publishes both Accelerate/macOS14 and older-OS wheels at the same
  // version. Select the compatible locked wheel before pip considers host tags.
  const lock = await fs.readFile(path.join(root, 'requirements.lock'), 'utf8');
  const numpy = lock.match(/^numpy==[^\n]*(?:\n[ \t]+[^\n]*)*/m)?.[0];
  if (!numpy) throw new Error('The dependency lock must pin NumPy');
  const selection = path.join(cache, 'numpy-platform.lock');
  const wheels = path.join(cache, 'numpy-compatible');
  await fs.writeFile(selection, numpy + '\n');
  await fs.rm(wheels, { recursive: true, force: true });
  await fs.mkdir(wheels, { recursive: true });
  const download = spawnSync(python, ['-B', '-E', '-s', '-m', 'pip', 'download', '--disable-pip-version-check',
    '--only-binary=:all:', '--no-deps', '--require-hashes', '--platform',
    process.arch === 'arm64' ? 'macosx_11_0_arm64' : 'macosx_10_13_x86_64',
    '--dest', wheels, '-r', selection], { stdio: 'inherit' });
  if (download.status !== 0) throw new Error('Could not obtain the locked NumPy wheel for supported macOS versions');
  const selected = (await fs.readdir(wheels)).filter(name => name.endsWith('.whl'));
  if (selected.length !== 1) throw new Error('Expected exactly one verified NumPy wheel');
  const install = spawnSync(python, ['-B', '-E', '-s', '-m', 'pip', 'install', '--disable-pip-version-check',
    '--no-compile', '--no-user', '--no-deps', path.join(wheels, selected[0])], { stdio: 'inherit' });
  if (install.status !== 0) throw new Error('Could not install the compatible NumPy wheel');
}
const dependencies = spawnSync(python, ['-B', '-E', '-s', '-m', 'pip', 'install', '--disable-pip-version-check', '--no-compile', '--no-user',
  '--require-hashes', '--cache-dir', path.join(cache, 'pip'), '-r', path.join(root, 'requirements.lock')], { stdio: 'inherit' });
if (dependencies.status !== 0) throw new Error('Could not install the pinned CAD/PDF dependencies into the bundled runtime');
const gitRuntime = JSON.parse(await fs.readFile(path.join(root, 'desktop/git-runtimes.json')))[target];
const gitArchive = path.join(cache, 'git.tar.gz');
let gitData = await fs.readFile(gitArchive).catch(() => null);
if (!gitData || digest(gitData) !== gitRuntime.sha256) {
  const response = await fetch(gitRuntime.url);
  if (!response.ok) throw new Error(`Bundled Git download failed: ${response.status}`);
  gitData = Buffer.from(await response.arrayBuffer());
  if (digest(gitData) !== gitRuntime.sha256) throw new Error('Git archive checksum mismatch');
  await fs.writeFile(gitArchive, gitData);
}
await fs.mkdir(path.join(resources, 'git'), { recursive: true });
const extractGit = spawnSync('tar', ['-xzf', gitArchive, '-C', path.join(resources, 'git')], { stdio: 'inherit' });
if (extractGit.status !== 0) throw new Error('Could not extract bundled Git');
if (process.platform === 'darwin') {
  const config = JSON.parse(await fs.readFile(path.join(root, 'src-tauri/tauri.conf.json'), 'utf8'));
  const floor = spawnSync(python, ['-B', '-E', '-s', path.join(root, 'scripts/verify-macos-floor.py'),
    '--minimum', config.bundle.macOS.minimumSystemVersion, '--json', path.join(resources, 'macos-deployment.json'),
    path.join(resources, 'runtime'), path.join(resources, 'git')], { stdio: 'inherit' });
  if (floor.status !== 0) throw new Error('Bundled native dependencies exceed the advertised macOS minimum');
}
await fs.copyFile(path.join(root, 'desktop/THIRD_PARTY_NOTICES.md'), path.join(resources, 'THIRD_PARTY_NOTICES.md'));
await copyDesignResources(root, resources);
const engine = path.join(resources, 'engine');
await fs.mkdir(engine, { recursive: true });
await fs.copyFile(path.join(root, 'README.md'), path.join(engine, 'README.md'));
await fs.copyFile(path.join(root, 'requirements.lock'), path.join(engine, 'requirements.lock'));

const files = ['build.py', 'serve.py', 'stud_cli.py', 'updates.py', 'validate.py'];
for (const file of files) await fs.copyFile(path.join(root, file), path.join(engine, file));
for (const dir of ['stud', 'web']) {
  await fs.cp(path.join(root, dir), path.join(engine, dir), {
    recursive: true, filter: source => !source.includes('__pycache__') && !source.endsWith('.pyc')
  });
}
for (const file of ['build/three.module.js', 'build/three.core.js', 'examples/jsm/controls/OrbitControls.js', 'LICENSE']) {
  const destination = path.join(engine, 'node_modules/three', file);
  await fs.mkdir(path.dirname(destination), { recursive: true });
  await fs.copyFile(path.join(root, 'node_modules/three', file), destination);
}
const pkg = JSON.parse(await fs.readFile(path.join(root, 'package.json')));
await fs.writeFile(path.join(engine, 'version.json'), JSON.stringify({ version: pkg.version, repository: process.env.STUD_RELEASE_REPOSITORY || null, channel: process.env.STUD_RELEASE_CHANNEL || 'stable' }) + '\n');
await fs.writeFile(path.join(resources, 'runtime-info.json'), JSON.stringify({ target, ...runtime, git: gitRuntime,
  dependencyLockSha256: digest(await fs.readFile(path.join(root, 'requirements.lock'))) }, null, 2) + '\n');
const nativeTrial = spawnSync(python, ['-B', '-E', '-s', '-c',
  'import cadquery as cq; from reportlab.pdfgen.canvas import Canvas; from svglib.svglib import svg2rlg; assert abs(cq.Workplane("XY").box(10,20,30).val().Volume()-6000)<1e-6; print("Bundled CadQuery and PDF runtime loaded")'], { stdio: 'inherit' });
if (nativeTrial.status !== 0) throw new Error('Bundled native runtime trial failed');
console.log(`Prepared stud ${pkg.version} for ${target} in ${resources}`);
