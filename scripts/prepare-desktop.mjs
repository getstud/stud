import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const target = process.argv[2] || `${process.platform}-${process.arch}`;
const runtimes = JSON.parse(await fs.readFile(path.join(root, 'desktop/runtimes.json')));
const runtime = runtimes[target];
if (!runtime) throw new Error(`Unsupported desktop target: ${target}`);
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
await fs.copyFile(path.join(root, 'desktop/THIRD_PARTY_NOTICES.md'), path.join(resources, 'THIRD_PARTY_NOTICES.md'));
await fs.cp(path.join(root, 'skills/stud-design'), path.join(resources, 'skills/stud-design'), { recursive: true });
const engine = path.join(resources, 'engine');
await fs.mkdir(engine, { recursive: true });
await fs.copyFile(path.join(root, 'README.md'), path.join(engine, 'README.md'));
await fs.mkdir(path.join(engine, 'docs'), { recursive: true });
for (const guide of ['workshop.md', 'assemblies.md', 'validation.md', 'environment.md']) {
  await fs.copyFile(path.join(root, 'docs', guide), path.join(engine, 'docs', guide));
}
await fs.cp(path.join(root, 'examples/environment'), path.join(engine, 'examples/environment'), {recursive: true});
const files = ['build.py', 'comments.py', 'pricing.py', 'serve.py', 'solid_geometry.py',
  'stud_cli.py', 'updates.py', 'validate.py', 'validation_rules.py'];
for (const file of files) await fs.copyFile(path.join(root, file), path.join(engine, file));
for (const dir of ['stud', 'clubhouse', 'web']) {
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
await fs.writeFile(path.join(resources, 'runtime-info.json'), JSON.stringify({ target, ...runtime }, null, 2) + '\n');
console.log(`Prepared stud ${pkg.version} for ${target} in ${resources}`);
