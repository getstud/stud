// Install a previous released app into an isolated folder, exercise Tauri's real
// signed update, and run the normal native project/prompt/price/PDF reopen proof.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {parseArgs} from 'node:util';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';

const {values}=parseArgs({options:Object.fromEntries([
 'candidate-cli','previous-installer','payload','signature','previous-version','evidence','target','test-binary',
].map(name=>[name,{type:'string'}]))});
for(const name of ['candidate-cli','previous-installer','payload','signature','previous-version','evidence'])assert.ok(values[name],`--${name} is required`);
assert.ok(['darwin','win32'].includes(process.platform),'Run on a supported native installer host');
if(process.platform==='win32') {
 assert.equal(process.env.GITHUB_ACTIONS,'true','Windows NSIS probes require disposable hosted CI');
 assert.equal(process.env.RUNNER_ENVIRONMENT,'github-hosted','Windows NSIS probes must not alter an existing user account');
 assert.ok(process.env.RUNNER_TEMP);
 for(const hive of ['HKCU','HKLM'])for(const view of ['32','64']) {
   const registration=spawnSync('reg',['query',`${hive}\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\stud`,`/reg:${view}`],{encoding:'utf8'});
   assert.equal(registration.status,1,'Uninstall any existing stud registration before this disposable CI probe');
 }
}
const repository=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const candidate=path.resolve(values['candidate-cli']),previous=path.resolve(values['previous-installer']);
const root=await fs.realpath(await fs.mkdtemp(path.join(process.platform==='win32'?process.env.RUNNER_TEMP:os.tmpdir(),'stud-update-probe-')));
await fs.writeFile(path.join(root,'.probe-owned'),'stud native update acceptance\n');
// Signing secrets are unnecessary in an installed application or test project.
const env=Object.fromEntries(Object.entries(process.env).filter(([name])=>!name.startsWith('APPLE_')&&!name.startsWith('TAURI_SIGNING_PRIVATE_KEY')));
function run(command,args,options={}) {
 const result=spawnSync(command,args,{cwd:repository,env,encoding:'utf8',timeout:600000,maxBuffer:16*1024*1024,...options});
 assert.equal(result.status,0,result.error?.message||[result.stdout,result.stderr].filter(Boolean).join('\n')||`${command} failed`);
 return result.stdout;
}
const version=run(candidate,['--version']).trim().replace(/^stud /,'');
const pubkey=process.env.STUD_UPDATER_PUBLIC_KEY;
assert.ok(pubkey,'STUD_UPDATER_PUBLIC_KEY must contain the candidate signing public key');
let testBinary=values['test-binary'];
if(!testBinary) {
 const messages=run('cargo',['test','--release','--manifest-path','src-tauri/Cargo.toml','--bin','stud-desktop',
   ...(values.target?['--target',values.target]:[]),'--no-run','--message-format=json']);
 for(const line of messages.split('\n')) {
   let record;try{record=JSON.parse(line);}catch{continue;}
   if(record.reason==='compiler-artifact'&&record.profile?.test&&record.target.name==='stud-desktop'&&record.executable)testBinary=record.executable;
 }
}
assert.ok(testBinary,'Could not locate the native Rust updater test executable');
const install=path.join(root,'previous');await fs.mkdir(install);
let executable,uninstaller;
try {
 if(process.platform==='darwin') {
   const mount=path.join(root,'media');await fs.mkdir(mount);
   run('hdiutil',['attach',previous,'-nobrowse','-readonly','-mountpoint',mount]);
   try{run('ditto',[path.join(mount,'stud.app'),path.join(install,'stud.app')]);}
   finally{run('hdiutil',['detach',mount]);}
   executable=path.join(install,'stud.app/Contents/MacOS/stud-desktop');
 } else {
   run(previous,['/S',`/D=${install}`]);
   executable=path.join(install,'stud-desktop.exe');
   uninstaller=path.join(install,'uninstall.exe');
 }
 await fs.access(executable);
 const config=path.join(root,'installation.json');
 await fs.writeFile(config,JSON.stringify({root,executable,version,previous_version:values['previous-version'],pubkey,
   signing_key_kind:process.env.STUD_UPDATE_KEY_KIND||'release',
   payload:path.resolve(values.payload),signature:path.resolve(values.signature),test_binary:path.resolve(testBinary)},null,2)+'\n');
 const evidence=path.resolve(values.evidence);await fs.mkdir(path.dirname(evidence),{recursive:true});
 run(process.execPath,[path.join(repository,'scripts/smoke-desktop.mjs'),candidate],{
   env:{...env,STUD_SIGNED_UPDATE_CONFIG:config,STUD_UPDATE_EVIDENCE:evidence},stdio:'inherit',timeout:900000,
 });
 const result=JSON.parse(await fs.readFile(evidence,'utf8'));assert.equal(result.smoke_passed,true);
 console.log(`Signed native update and data preservation passed. Evidence: ${evidence}`);
} finally {
 if(uninstaller) {
   // NSIS is asynchronous during final self-removal. Its own folder is the only
   // installation touched by this probe; user projects live outside that folder.
   try{run(uninstaller,['/S']);}catch(error){console.error(error.message);}
 }
 await fs.rm(root,{recursive:true,force:true,maxRetries:10,retryDelay:500});
}
