// An acceptance-test hook. It only updates the previously installed app inside
// a marked temporary probe folder; production updater configuration is untouched.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createReadStream} from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import {spawn,spawnSync} from 'node:child_process';
import {once} from 'node:events';
import {createHash} from 'node:crypto';
import {compareVersions} from './release-channel.mjs';

export async function installSignedCandidate(configPath,env) {
 const config=JSON.parse(await fs.readFile(configPath,'utf8'));
 const root=await fs.realpath(config.root),executable=await fs.realpath(config.executable);
 if(process.platform==='win32') {
   assert.equal(env.GITHUB_ACTIONS,'true');assert.equal(env.RUNNER_ENVIRONMENT,'github-hosted');
   const temporary=await fs.realpath(env.RUNNER_TEMP);
   assert.ok(root.toLowerCase().startsWith(temporary.toLowerCase()+path.sep));
 }
 assert.ok(path.basename(root).startsWith('stud-update-probe-'));
 assert.equal(await fs.readFile(path.join(root,'.probe-owned'),'utf8'),'stud native update acceptance\n');
 assert.ok(executable.startsWith(root+path.sep));
 assert.ok(compareVersions(config.version,config.previous_version)>0,'Candidate must be newer than the installed release');
 const cli=path.join(path.dirname(executable),process.platform==='win32'?'stud.exe':'stud');
 const version=()=>spawnSync(cli,['--version'],{env,encoding:'utf8',timeout:15000});
 const old=version();
 assert.equal(old.status,0,old.error?.message||old.stderr);
 assert.equal(old.stdout.trim(),`stud ${config.previous_version}`);
 const signature=(await fs.readFile(config.signature,'utf8')).trim(),payload=await fs.stat(config.payload);
 let endpoint,downloads=0;
 const server=http.createServer((request,response)=>{
   if(request.url==='/latest.json') {
     const body=JSON.stringify({version:config.version,platforms:{'native-probe':{url:endpoint+'/update',signature}}});
     response.writeHead(200,{'Content-Type':'application/json','Content-Length':Buffer.byteLength(body)});response.end(body);
   } else if(request.url==='/update') {
     downloads++;response.writeHead(200,{'Content-Type':'application/octet-stream','Content-Length':payload.size});
     const stream=createReadStream(config.payload);stream.on('error',error=>response.destroy(error));stream.pipe(response);
   } else {response.writeHead(404);response.end();}
 });
 server.listen(0,'127.0.0.1');await once(server,'listening');endpoint=`http://127.0.0.1:${server.address().port}`;
 const probe=path.join(root,'probe.json');
 await fs.writeFile(probe,JSON.stringify({...config,root,executable,endpoint}));
 let child;
 try {
   child=spawn(config.test_binary,['--ignored','--exact','update_tests::native_signed_update_installation','--nocapture'],
     {env:{...env,STUD_NATIVE_UPDATE_PROBE:probe},stdio:'inherit'});
   const timeout=setTimeout(()=>child.kill(),360000);
   try {const [code]=await once(child,'exit');assert.equal(code,0,'Tauri updater probe failed');}
   finally {clearTimeout(timeout);}
   const verified=JSON.parse(await fs.readFile(path.join(root,'verified-update.json'),'utf8'));
   assert.equal(verified.signature_verified,true);assert.equal(verified.version,config.version);assert.equal(downloads,1);
   const deadline=Date.now()+300000;
   let current;
   do {
     current=version();
     if(current.status===0&&current.stdout.trim()===`stud ${config.version}`)break;
     assert.ok(Date.now()<deadline,`Updated CLI did not become ready: ${current.stderr}`);
     await new Promise(resolve=>setTimeout(resolve,500));
   } while(true);
   console.log(`Real signed update installed ${config.previous_version} → ${config.version}.`);
   return {cli,previous_version:config.previous_version,version:config.version,signature_verified:true,payload_bytes:payload.size,
     signing_key_kind:config.signing_key_kind,public_key_sha256:createHash('sha256').update(config.pubkey).digest('hex')};
 } finally {
   if(child&&child.exitCode===null)child.kill();
   server.closeAllConnections();await new Promise(resolve=>server.close(resolve));
 }
}
