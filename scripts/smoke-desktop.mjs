import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { spawn, spawnSync } from 'node:child_process';
import { once } from 'node:events';

let cli = path.resolve(process.argv[2] || (process.platform === 'darwin'
  ? 'src-tauri/target/aarch64-apple-darwin/release/bundle/macos/stud.app/Contents/MacOS/stud'
  : 'src-tauri/target/x86_64-pc-windows-msvc/release/stud.exe'));
let resources = process.platform === 'darwin' ? path.resolve(path.dirname(cli), '../Resources') : path.dirname(cli);
let python = path.join(resources, process.platform === 'win32' ? 'runtime/python.exe' : 'runtime/bin/python3');
const temporary = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'stud-installed-')));
const project = path.join(temporary, 'Project with spaces & café');
const env = { ...process.env, HOME: temporary, APPDATA: temporary,
  LOCALAPPDATA: temporary, STUD_DATA_DIR: path.join(temporary, 'catalog'),
  PATH: process.platform === 'win32' ? `${process.env.SystemRoot}\\System32` : '/usr/bin:/bin',
  PYTHONHOME: '/invalid-python', PYTHONPATH: '/invalid-python' };
function command(...args) {
  const result = spawnSync(cli, args, { cwd: temporary, env, encoding: 'utf8', timeout: 120000, maxBuffer: 16 * 1024 * 1024 });
  assert.equal(result.status, 0, result.error?.message || result.stdout + result.stderr);
  return result.stdout;
}
async function stop(child, graceful = true) {
  if (child.exitCode !== null) return;
  const done = once(child, 'exit');
  if (process.platform === 'win32') spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F']);
  else child.kill(graceful ? 'SIGINT' : 'SIGTERM');
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
let beforeFiles = await bundleFiles();
let server;
let blocker;
let updateEvidence;
try {
  for (const file of ['skills/stud-design/SKILL.md', 'skills/stud-design/agents/openai.yaml',
    'skills/stud-design/references/stud-integration.md', 'engine/README.md',
    'engine/docs/workshop.md', 'engine/docs/assemblies.md', 'engine/docs/validation.md',
    'engine/docs/environment.md', 'engine/examples/environment/assets/tree.js', 'engine/examples/framed-shed/design.py',
    'engine/examples/framed-shed/README.md']) {
    assert.ok((await fs.readFile(path.join(resources, file), 'utf8')).length, `Missing bundled skill resource: ${file}`);
  }
  assert.match(command('--version'), /^stud \d+\.\d+\.\d+/);
  assert.equal(JSON.parse(command('doctor')).status, 'healthy');
  command('init', project, '--name', 'Café 工作台');
  server = spawn(cli, ['serve', project, '--port', '0', '--no-open'], { cwd: temporary, env, stdio: ['ignore', 'pipe', 'pipe'] });
  const line = await firstLine(server);
  const url = line.match(/http:\/\/127\.0\.0\.1:\d+/)?.[0];
  assert.ok(url, line);
  async function api(operation, arguments_, key = crypto.randomUUID()) {
    const response = await fetch(url + '/api/v1/command', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ operation, key, arguments: arguments_ }) });
    const body = await response.json();
    assert.ok(response.ok, JSON.stringify(body));
    return body;
  }
  const state = JSON.parse(command('status', project));
  const request = JSON.parse(command('begin', project, '--intent', 'Installed native workflow', '--expected-head', state.option.head, '--key', 'installed-edit'));
  await fs.mkdir(path.join(request.workspace, 'inputs'));
  await fs.writeFile(path.join(request.workspace, 'helper.py'), "from pathlib import Path\nTITLE=Path('inputs/title.txt').read_text()\n");
  await fs.writeFile(path.join(request.workspace, 'inputs/title.txt'), 'External project');
  await fs.appendFile(path.join(request.workspace, 'design.py'), '\nimport helper\nmodel.name = helper.TITLE\n');
  const source = JSON.parse(command('source', project, '--request', request.id));
  const build = JSON.parse(command('evaluate', project, '--request', request.id, '--source', source.source_id, '--wait'));
  assert.equal(build.status, 'complete', JSON.stringify(build));
  const manifest = await (await fetch(url + `/api/v1/builds/${build.id}/manifest.json`)).json();
  assert.equal(manifest.name, 'External project');
  assert.equal(manifest.checks.all_passed, true);
  const promptId = crypto.randomUUID();
  await api('save_prompt', { prompt_id: promptId, text: 'Installed viewer note', object_id: 'starter', build_id: build.id, source_id: source.source_id });
  await api('save_prices', { quotes: [{ product_id: 'lumber.1.5x3.5', specification: { material: 'softwood', section: [1.5,3.5], stock_length: '96', length_unit: 'in' },
    purchase_unit: 'board', price: '8.50', currency: 'USD', supplier: 'Installed test', source: 'Manual fixture', quote_date: '2026-09-09', kind: 'manual' }],
    expected_build: build.id });
  const saved = JSON.parse(command('finish', project, '--request', request.id, '--source', source.source_id, '--summary', 'Installed native workflow', '--wait'));
  assert.equal(saved.status, 'complete', JSON.stringify(saved));
  assert.equal(JSON.parse(command('finish', project, '--request', request.id, '--source', source.source_id, '--summary', 'Installed native workflow', '--wait')).checkpoint, saved.checkpoint);
  assert.equal(JSON.parse(command('validate', project, '--json')).all_passed, true);
  const packet = JSON.parse(command('plans', project, '--checkpoint', saved.checkpoint, '--wait'));
  assert.equal(packet.status, 'complete', JSON.stringify(packet));
  assert.equal((await fs.readFile(packet.result.pdf)).subarray(0,5).toString(), '%PDF-');
  assert.match(await fs.readFile(path.join(project, `records/prompts/${promptId}.json`), 'utf8'), /Installed viewer note/);
  const originalPacket = await fs.readFile(packet.result.pdf);
  const originalEstimate = await (await fetch(url + '/api/pricing')).json();
  assert.equal(originalEstimate.total, '8.50');
  assert.equal(originalEstimate.unpriced_lines, 0);
  const example = path.join(temporary, 'Adaptable shed example');
  await fs.cp(path.join(resources, 'engine/examples/framed-shed'), example, { recursive: true });
  command('build', example);
  const exampleReport = JSON.parse(command('validate', example, '--json'));
  assert.equal(exampleReport.counts.FAIL ?? 0, 0);
  for (const route of ['/', '/app.js', '/cad-scene.js', '/project-events.js', '/show.js', '/area-capture.js', '/updates.js', '/api/update', '/vendor/three.js', '/vendor/three.core.js', '/vendor/OrbitControls.js', '/api/model', '/api/v1/checkpoints', '/api/v1/prompts']) {
    const response = await fetch(url + route);
    assert.equal(response.status, 200, route);
    assert.ok((await response.text()).length, route);
  }
  const support = process.platform === 'darwin' ? path.join(temporary, 'Library/Application Support/app.stud.desktop') : path.join(temporary, 'app.stud.desktop');
  const lockPath = path.join(support, 'runtime.lock');
  const lockScript = process.platform === 'win32'
    ? "import sys,msvcrt,time\nf=open(sys.argv[1],'r+b')\nmsvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)\nprint('locked',flush=True)\ntime.sleep(60)"
    : "import sys,fcntl,time\nf=open(sys.argv[1],'r+b')\nfcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)\nprint('locked',flush=True)\ntime.sleep(60)";
  const conflict = spawnSync(python, ['-B', '-E', '-s', '-c', lockScript.replace('time.sleep(60)', ''), lockPath], { env, encoding: 'utf8' });
  assert.notEqual(conflict.status, 0, 'Viewer must hold the shared update lock');
  await stop(server); server = null;
  if (process.env.STUD_SIGNED_UPDATE_CONFIG) {
    assert.deepEqual(await bundleFiles(),beforeFiles,'Project setup must not write into the candidate app');
    const {installSignedCandidate}=await import('./native-update-probe.mjs');
    const originalHead=saved.checkpoint;
    await fs.writeFile(path.join(project,'user-notes.txt'),'Keep this unrelated project file.\n');
    const result=await installSignedCandidate(process.env.STUD_SIGNED_UPDATE_CONFIG,env);
    cli=result.cli;
    resources=process.platform==='darwin'?path.resolve(path.dirname(cli),'../Resources'):path.dirname(cli);
    python=path.join(resources,process.platform==='win32'?'runtime/python.exe':'runtime/bin/python3');
    beforeFiles=await bundleFiles();
    assert.equal(JSON.parse(command('status',project)).option.head,originalHead);
    command('stop',project);
    const deadline=Date.now()+15000;
    while(await fs.access(path.join(project,'.stud/endpoint.json')).then(()=>true,()=>false)) {
      assert.ok(Date.now()<deadline);await new Promise(resolve=>setTimeout(resolve,50));
    }
    assert.equal(await fs.readFile(path.join(project,'user-notes.txt'),'utf8'),'Keep this unrelated project file.\n');
    updateEvidence={...result,project_id:state.project_id,checkpoint:originalHead};
  }
  const copy = path.join(temporary, 'Reopened copy');
  await fs.cp(project, copy, { recursive: true });
  server = spawn(cli, ['serve', copy, '--port', '0', '--no-open'], { cwd: temporary, env, stdio: ['ignore', 'pipe', 'pipe'] });
  const copyUrl = (await firstLine(server)).match(/http:\/\/127\.0\.0\.1:\d+/)?.[0];
  const reopened = JSON.parse(command('status', copy));
  assert.equal(reopened.project_id, state.project_id);
  assert.equal(reopened.project_root, copy);
  assert.equal(reopened.option.head, saved.checkpoint);
  assert.deepEqual(await fs.readFile(path.join(copy, path.relative(project, packet.result.pdf))), originalPacket);
  assert.equal((await (await fetch(copyUrl + '/api/v1/prompts')).json())[0].text, 'Installed viewer note');
  assert.deepEqual(await (await fetch(copyUrl + '/api/pricing')).json(), originalEstimate);
  const catalog = JSON.parse(command('projects', '--json'));
  const catalogPath = process.platform === 'win32' ? copy.toLowerCase() : copy;
  assert.ok(catalog.some(entry => entry.path === catalogPath && entry.available));
  await stop(server); server = null;
  // A CLI-created background coordinator must keep the update lock and have
  // a supported stop command, even when no foreground viewer process exists.
  command('status', copy);
  const held = spawnSync(python, ['-B', '-E', '-s', '-c', lockScript.replace('time.sleep(60)', ''), lockPath], { env, encoding: 'utf8' });
  assert.notEqual(held.status, 0, 'Detached coordinator must hold the shared update lock');
  assert.equal(JSON.parse(command('stop', copy)).status, 'stopping');
  const stopDeadline = Date.now() + 15000;
  while (await fs.access(path.join(copy, '.stud/endpoint.json')).then(() => true, () => false)) {
    assert.ok(Date.now() < stopDeadline, 'Coordinator must stop and remove its endpoint');
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  assert.equal(JSON.parse(command('stop', copy)).status, 'stopped');
  blocker = spawn(python, ['-B', '-E', '-s', '-c', lockScript, lockPath], { env, stdio: ['ignore', 'pipe', 'pipe'] });
  assert.equal(await firstLine(blocker), 'locked');
  const blocked = spawnSync(cli, ['--version'], { cwd: temporary, env, encoding: 'utf8' });
  assert.notEqual(blocked.status, 0);
  assert.match(blocked.stderr, /being updated/);
  await stop(blocker, false); blocker = null;
  assert.match(command('--version'), /^stud /);
  assert.deepEqual(await bundleFiles(), beforeFiles, 'CLI commands must not write caches into the installed app');
  if(updateEvidence) await fs.writeFile(process.env.STUD_UPDATE_EVIDENCE||path.join(temporary,'update-evidence.json'),
    JSON.stringify({...updateEvidence,preserved:{project:true,checkpoint:true,prompt:true,prices:true,pdf:true,unrelated_file:true},smoke_passed:true},null,2)+'\n');
  console.log('Installed-app smoke test passed: pinned CAD/PDF/Git runtime, native geometry, request save/retry, quotes, prompts, vector plans, full-folder reopen, catalog, legacy project and update locking.');
} finally {
  if (server) await stop(server);
  if (blocker) await stop(blocker, false);
  await fs.rm(temporary, { recursive: true, force: true });
}
