// Measure the real viewer against an already evaluated, closed benchmark project.
// Uses archived geometry; it never edits the design or requests a new native build.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const project=path.resolve(process.argv[2]);
const output=path.resolve(process.argv[3]||path.join(root,'docs/evidence/viewer-performance.json'));
const {chromium}=await import(process.env.STUD_PLAYWRIGHT_MODULE||'playwright');
const python=process.env.STUD_PYTHON||path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
const server=spawn(python,['-B','-m','stud.session_http','--project',project],{cwd:root,stdio:['ignore','pipe','pipe']});
let stderr='',browser;
server.stderr.on('data',value=>stderr+=value);
const ready=new Promise((resolve,reject)=>{
 const timeout=setTimeout(()=>reject(new Error('Server startup timed out: '+stderr)),60000);
 createInterface({input:server.stdout}).on('line',line=>{const url=line.match(/http:\/\/127\.0\.0\.1:\d+/)?.[0];if(url){clearTimeout(timeout);resolve(url);}});
 server.once('exit',code=>{clearTimeout(timeout);reject(new Error(`Server exited ${code}: ${stderr}`));});
});
try{
 const url=await ready;
 browser=await chromium.launch({headless:true,...(process.env.STUD_CHROME?{executablePath:process.env.STUD_CHROME}:{}),
   args:process.env.STUD_RENDERER==='default'?[]:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],requests=[];
 page.on('pageerror',error=>errors.push(String(error)));
 page.on('request',request=>requests.push({url:new URL(request.url()).pathname,at:performance.now()}));
 await page.addInitScript(()=>performance.setResourceTimingBufferSize(10000));
 const started=performance.now();
 await page.goto(url);
 await page.waitForFunction(()=>window.stud?.performance?.parts>0,null,{timeout:120000});
 const readyMs=performance.now()-started;
 const readyAt=performance.now();
 const initial=await page.evaluate(()=>({scene:window.stud.performance,assets:window.stud.assets,parts:window.stud.visibleCount,
   resources:performance.getEntriesByType('resource').filter(r=>r.name.includes('/api/model')||r.name.includes('/api/v1/builds/')).map(r=>({url:new URL(r.name).pathname,duration_ms:r.duration,transfer_bytes:r.transferSize,decoded_bytes:r.decodedBodySize})),
   heap:performance.memory?{used_bytes:performance.memory.usedJSHeapSize,total_bytes:performance.memory.totalJSHeapSize}:null}));
 const frames=await page.evaluate(()=>new Promise(resolve=>{
   const samples=[],start=performance.now();let previous=start;
   function tick(now){samples.push(now-previous);previous=now;if(now-start<4000)requestAnimationFrame(tick);else resolve(samples);}
   requestAnimationFrame(tick);
 }));
 // Exercise the same CadScene implementation in isolation so geometry-cache
 // hits and patch cost are separated from the application tables and rendering.
 const patches=await page.evaluate(async()=>{
   const THREE=await import('three');
   const {CadScene}=await import('/cad-scene.js');
   const data=window.stud.model;
   const scene=new CadScene({THREE,group:new THREE.Group()});
   let loads=0;scene.fetcher=async url=>{loads++;return fetch(url);};
   const firstStarted=performance.now();const first=await scene.prepare(data);first();const firstMs=performance.now()-firstStarted;
   const originals=new Map(scene.objects),loadCount=loads;
   const repeatStarted=performance.now();const repeat=await scene.prepare(data);const patched=repeat();const repeatMs=performance.now()-repeatStarted;
   const result={full_scene_ms:firstMs,cached_scene_ms:repeatMs,initial_asset_requests:loadCount,repeat_asset_requests:loads-loadCount,
     objects_preserved:[...originals].every(([id,mesh])=>scene.objects.get(id)===mesh),additions:patched.additions.length,changes:patched.changed.length};
   scene.dispose();return result;
 });
 const idleRequests=requests.filter(request=>request.at>readyAt+500&&['/api/model','/api/validation'].includes(request.url));
 assert.deepEqual(idleRequests,[],'Idle native models use the ordered event stream without repeating model/check payloads');
 assert.equal(patches.repeat_asset_requests,0);assert.equal(patches.objects_preserved,true);assert.equal(patches.additions,0);assert.equal(patches.changes,0);assert.deepEqual(errors,[]);
 frames.sort((a,b)=>a-b);
 const renderer=await page.evaluate(()=>{
   const gl=document.querySelector('canvas')?.getContext('webgl2');const debug=gl?.getExtension('WEBGL_debug_renderer_info');
   return debug?gl.getParameter(debug.UNMASKED_RENDERER_WEBGL):'unavailable';
 });
 const result={project,url,chrome:await browser.version(),renderer,ready_ms:readyMs,initial,patches,idle_model_validation_requests:idleRequests.length,
   frames:{count:frames.length,median_ms:frames[Math.floor(frames.length*.5)],p95_ms:frames[Math.floor(frames.length*.95)]},errors};
 await mkdir(path.dirname(output),{recursive:true});
 await page.screenshot({path:output.replace(/\.json$/,'.png')});
 await writeFile(output,JSON.stringify(result,null,2)+'\n');
 console.log(JSON.stringify(result));
}finally{
 await browser?.close();server.kill('SIGINT');
 await new Promise(resolve=>{if(server.exitCode!==null)return resolve();server.once('exit',resolve);setTimeout(resolve,10000);});
}
