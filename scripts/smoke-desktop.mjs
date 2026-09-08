import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { spawn, spawnSync } from 'node:child_process';
import { once } from 'node:events';

const cli = path.resolve(process.argv[2] || (process.platform === 'darwin'
  ? 'src-tauri/target/aarch64-apple-darwin/release/bundle/macos/stud.app/Contents/MacOS/stud'
  : 'src-tauri/target/x86_64-pc-windows-msvc/release/stud.exe'));
const resources = process.platform === 'darwin' ? path.resolve(path.dirname(cli), '../Resources') : path.dirname(cli);
const python = path.join(resources, process.platform === 'win32' ? 'runtime/python.exe' : 'runtime/bin/python3');
const temporary = await fs.mkdtemp(path.join(os.tmpdir(), 'stud-installed-'));
const project = path.join(temporary, 'Project with spaces & café');
const env = { ...process.env, HOME: temporary, APPDATA: temporary,
  PATH: process.platform === 'win32' ? `${process.env.SystemRoot}\\System32` : '/usr/bin:/bin',
  PYTHONHOME: '/invalid-python', PYTHONPATH: '/invalid-python' };
function command(...args) {
  const result = spawnSync(cli, args, { cwd: temporary, env, encoding: 'utf8', timeout: 120000, maxBuffer: 16 * 1024 * 1024 });
  assert.equal(result.status, 0, result.error?.message || result.stdout + result.stderr);
  return result.stdout;
}
async function stop(child) {
  if (child.exitCode !== null) return;
  const done = once(child, 'exit');
  if (process.platform === 'win32') spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F']);
  else child.kill('SIGTERM');
  await done;
}
async function firstLine(child) {
  let data = '';
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Process did not become ready')), 20000);
    child.stdout.on('data', chunk => { data += chunk; if (data.includes('\n')) { clearTimeout(timer); resolve(data.split(/\r?\n/)[0]); } });
    child.once('exit', code => { clearTimeout(timer); reject(new Error(`Process exited before readiness: ${code}`)); });
    child.once('error', error => { clearTimeout(timer); reject(error); });
    child.stderr.on('data', chunk => process.stderr.write(chunk));
  });
}
async function bundleFiles() {
  return (await fs.readdir(resources, { recursive: true })).sort();
}
const beforeFiles = await bundleFiles();
let server;
let blocker;
try {
  for (const file of ['skills/stud-design/SKILL.md', 'skills/stud-design/agents/openai.yaml',
    'skills/stud-design/references/stud-integration.md', 'engine/README.md',
    'engine/docs/workshop.md', 'engine/docs/assemblies.md', 'engine/docs/validation.md',
    'engine/docs/environment.md', 'engine/examples/environment/assets/tree.js', 'engine/examples/framed-shed/design.py',
    'engine/examples/framed-shed/README.md']) {
    assert.ok((await fs.readFile(path.join(resources, file), 'utf8')).length, `Missing bundled skill resource: ${file}`);
  }
  assert.match(command('--version'), /^stud \d+\.\d+\.\d+/);
  command('init', project, '--name', 'Installed app test');
  await fs.writeFile(path.join(project, 'helper.py'), "from pathlib import Path\nTITLE=Path('title.txt').read_text()\n");
  await fs.writeFile(path.join(project, 'title.txt'), 'External project');
  await fs.appendFile(path.join(project, 'design.py'), '\nimport helper\nproject.name = helper.TITLE\n');
  command('build', project);
  const report = JSON.parse(command('validate', project, '--json'));
  assert.equal(report.counts.FAIL ?? 0, 0);
  const exports = JSON.parse(await fs.readFile(path.join(project, 'output/model/model.json')));
  assert.equal(exports.name, 'External project');
  const example = path.join(temporary, 'Adaptable shed example');
  await fs.cp(path.join(resources, 'engine/examples/framed-shed'), example, { recursive: true });
  command('build', example);
  const exampleReport = JSON.parse(command('validate', example, '--json'));
  assert.equal(exampleReport.counts.FAIL ?? 0, 0);
  server = spawn(cli, ['serve', project, '--port', '0'], { cwd: temporary, env, stdio: ['ignore', 'pipe', 'pipe'] });
  const line = await firstLine(server);
  const url = line.match(/http:\/\/127\.0\.0\.1:\d+/)?.[0];
  assert.ok(url, line);
  for (const route of ['/', '/app.js', '/show.js', '/area-capture.js', '/updates.js', '/api/update', '/vendor/three.js', '/vendor/three.core.js', '/vendor/OrbitControls.js', '/api/model']) {
    const response = await fetch(url + route);
    assert.equal(response.status, 200, route);
    assert.ok((await response.text()).length, route);
  }
  const comment = await fetch(url + '/api/comments', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: crypto.randomUUID(), part_id: 'frame.stud.01', text: 'Installed viewer note' }) });
  assert.equal(comment.status, 200);
  assert.match(await fs.readFile(path.join(project, 'annotations/comments.json'), 'utf8'), /Installed viewer note/);
  const support = process.platform === 'darwin' ? path.join(temporary, 'Library/Application Support/app.stud.desktop') : path.join(temporary, 'app.stud.desktop');
  const lockPath = path.join(support, 'runtime.lock');
  const lockScript = process.platform === 'win32'
    ? "import sys,msvcrt,time\nf=open(sys.argv[1],'r+b')\nmsvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)\nprint('locked',flush=True)\ntime.sleep(60)"
    : "import sys,fcntl,time\nf=open(sys.argv[1],'r+b')\nfcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)\nprint('locked',flush=True)\ntime.sleep(60)";
  const conflict = spawnSync(python, ['-B', '-E', '-s', '-c', lockScript.replace('time.sleep(60)', ''), lockPath], { env, encoding: 'utf8' });
  assert.notEqual(conflict.status, 0, 'Viewer must hold the shared update lock');
  await stop(server); server = null;
  blocker = spawn(python, ['-B', '-E', '-s', '-c', lockScript, lockPath], { env, stdio: ['ignore', 'pipe', 'pipe'] });
  assert.equal(await firstLine(blocker), 'locked');
  const blocked = spawnSync(cli, ['--version'], { cwd: temporary, env, encoding: 'utf8' });
  assert.notEqual(blocked.status, 0);
  assert.match(blocked.stderr, /being updated/);
  await stop(blocker); blocker = null;
  assert.match(command('--version'), /^stud /);
  assert.deepEqual(await bundleFiles(), beforeFiles, 'CLI commands must not write caches into the installed app');
  console.log('Installed-app smoke test passed: bundled runtime, external projects, exports, viewer, annotations, update locking.');
} finally {
  if (server) await stop(server);
  if (blocker) await stop(blocker);
  await fs.rm(temporary, { recursive: true, force: true });
}
