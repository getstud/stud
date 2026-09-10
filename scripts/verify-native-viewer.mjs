// Run with a CadQuery Python and Playwright. All project writes use a fresh temp folder.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {mkdir,writeFile,rename} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const {chromium}=await import(process.env.STUD_PLAYWRIGHT_MODULE||'playwright');
const python=process.env.STUD_PYTHON||path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
const server=spawn(python,['-B','scripts/native-viewer-fixture.py'],{cwd:root,stdio:['ignore','pipe','pipe']});
let stderr='';server.stderr.on('data',data=>{stderr+=data;});
const ready=new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('Fixture startup timed out: '+stderr)),90000);const lines=createInterface({input:server.stdout});lines.on('line',line=>{if(line.startsWith('READY ')){clearTimeout(timer);resolve(JSON.parse(line.slice(6)));}});server.once('exit',code=>{clearTimeout(timer);reject(new Error(`Fixture exited ${code}: ${stderr}`));});});
let browser,context,info;const errors=[],evidence=path.join(root,'docs/evidence');
await mkdir(evidence,{recursive:true});
async function api(route,payload){const response=await fetch(info.url+route,payload?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}:undefined);const data=await response.json();assert(response.ok,JSON.stringify(data));return data;}
const command=(operation,args={})=>api('/api/v1/command',{operation,key:crypto.randomUUID(),arguments:args});
async function waitJob(job){while(['queued','running'].includes(job.status)){await new Promise(resolve=>setTimeout(resolve,100));job=await api('/api/v1/jobs/'+job.id);}assert.equal(job.status,'complete',JSON.stringify(job));return job;}
try{
 info=await ready;
 browser=await chromium.launch({headless:true,...(process.env.STUD_CHROME?{executablePath:process.env.STUD_CHROME}:{}),args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 context=await browser.newContext({viewport:{width:1440,height:1000},recordVideo:{dir:path.join(evidence,'native-video'),size:{width:1440,height:1000}}});
 const page=await context.newPage();page.on('pageerror',error=>errors.push(String(error)));const video=page.video();
 await page.goto(info.url);await page.waitForFunction(()=>window.stud?.visibleCount===12);
 await page.getByRole('button',{name:'Expand Frame',exact:true}).click();
 await page.locator('[data-id="bench.leg.left.front"]').click();
 const selected=await page.evaluate(()=>window.stud.selected),camera=await page.evaluate(()=>window.stud.camera);
 await page.screenshot({path:path.join(evidence,'native-current-workbench.png')});
 const source=`import time\nimport cadquery as cq\nfrom stud.cad import Model\nfrom workbench import workbench\nmodel=Model('Workbench with setup blocks',units='in')\nworkbench(model,width=84)\nmodel.assembly('bench.fixtures','Setup blocks',parent='bench')\nblocks=[]\nfor index in range(2):\n    time.sleep(.8)\n    part='bench.fixture.'+str(index)\n    with model.batch():\n        model.part(part,cq.Workplane('XY').box(1.5,3.5,4,centered=(False,False,False)),parent='bench.fixtures',material='lumber.2x4',location=cq.Location(cq.Vector(8+8*index,12,36)),blank={'size':[1.5,3.5,4],'cut_length':4,'operations':[{'kind':'square_cut','finished_length':4}]})\n        model.requirement(part+'.blank','stock_fit',[part])\n        blocks.append(part)\nmodel.demand('fixture.stock',product_id='lumber.2x4',specification={'material':'softwood','section':[1.5,3.5],'grade':'construction'},object_ids=blocks,purchase_unit='board',unit='in',stock_lengths=[96],cuts=[{'object_id':part,'length':4} for part in blocks],kerf=.125)\nmodel.step('fixtures','Place the two loose setup blocks on the bench.',parts=blocks)\n`;
 await page.evaluate(()=>{window.nativeSamples=[];window.nativeSampleTimer=setInterval(()=>window.nativeSamples.push({count:window.stud.visibleCount,animation:window.stud.animation,camera:window.stud.camera,selected:window.stud.selected,build:window.stud.model?.cad.build_id}),35);});
 await writeFile(path.join(info.active.workspace,'design.py'),source);
 // The project's file watcher should evaluate the content without an evaluate command.
 await page.waitForFunction(()=>window.stud.visibleCount===14&&window.stud.model.cad.completion.geometry==='complete',null,{timeout:45000});
 await page.waitForTimeout(1300);
 const samples=await page.evaluate(()=>{clearInterval(window.nativeSampleTimer);return window.nativeSamples;});
 assert(samples.some(sample=>sample.count===13),'A coherent intermediate batch was visible');
 assert(samples.some(sample=>sample.animation.some(entry=>entry.id.startsWith('bench.fixture.')&&Math.abs(entry.y-entry.targetY)>.01)),'New parts animate toward their final positions');
 assert.equal(await page.evaluate(()=>window.stud.selected),selected,'Selection persists through worker updates');
 assert(!samples.some(sample=>sample.animation.some(entry=>entry.id==='bench.leg.left.front')),'Unchanged parts do not replay the addition animation');
 await page.screenshot({path:path.join(evidence,'native-live-additions.png')});
 const activeAfterBuild=await api('/api/v1/status');assert.equal(activeAfterBuild.active_request,info.active.id);
 await page.getByRole('link',{name:'Versions',exact:true}).click();
 await page.locator('#version-left').selectOption(info.baseline.checkpoint);await page.locator('#version-right').selectOption(info.wider.checkpoint);
 await page.locator('#version-compare').click();await page.waitForFunction(()=>document.getElementById('comparison-summary').textContent.includes('changed parts'),null,{timeout:45000});
 assert.equal(await page.locator('#version-error').innerText(),'');
 assert.equal(await page.locator('.comparison-canvas canvas').count(),2);
 await page.locator('#comparison-views').scrollIntoViewIfNeeded();
 const otherCanvas=page.locator('.comparison-canvas canvas').nth(1),beforeOrbit=await otherCanvas.screenshot();
 const orbitBox=await page.locator('.comparison-canvas canvas').first().boundingBox();
 await page.mouse.move(orbitBox.x+orbitBox.width/2,orbitBox.y+orbitBox.height/2);await page.mouse.down();await page.mouse.move(orbitBox.x+orbitBox.width/2+65,orbitBox.y+orbitBox.height/2+25,{steps:10});await page.mouse.up();await page.waitForTimeout(100);
 assert(!beforeOrbit.equals(await otherCanvas.screenshot()),'Orbiting A changes the coordinated B view');
 await page.screenshot({path:path.join(evidence,'native-version-comparison.png')});
 assert.equal((await api('/api/v1/status')).active_request,info.active.id,'Comparing leaves the writer active');
 await page.locator('#version-price-mode').selectOption('common_price');await page.locator('#version-compare').click();
 await page.waitForFunction(()=>document.getElementById('comparison-summary').textContent.includes('Both estimates use the same saved quotes.'),null,{timeout:45000});
 await page.locator(`[data-checkpoint="${info.baseline.checkpoint}"]`).click();
 await page.waitForFunction(()=>window.stud.model?.cad.presentation==='history'&&window.stud.visibleCount===12);
 assert.equal((await api('/api/v1/status')).active_request,info.active.id);
 await page.getByRole('link',{name:'Estimate',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('#costs > .sub').textContent.includes('Original saved estimate'));
 assert.equal(await page.locator('#pricerows input:enabled').count(),0);
 await page.getByRole('link',{name:'Versions',exact:true}).click();await page.locator('#version-live').click();
 await page.waitForFunction(()=>window.stud.model?.cad.presentation==='live'&&window.stud.visibleCount===14);
 await page.getByRole('link',{name:'Versions',exact:true}).click();
 await page.locator('#version-plan-checkpoint').selectOption(info.baseline.checkpoint);await page.locator('#version-plans').click();
 await page.waitForSelector('#version-exports a[download]',{timeout:45000});assert.equal(await page.locator('#version-error').innerText(),'');
 const href=await page.locator('#version-exports a').first().getAttribute('href'),pdf=await fetch(info.url+href);assert.equal(pdf.status,200);assert.equal(pdf.headers.get('content-type'),'application/pdf');
 const bytes=new Uint8Array(await pdf.arrayBuffer());assert.equal(new TextDecoder().decode(bytes.slice(0,5)),'%PDF-');
 await page.screenshot({path:path.join(evidence,'native-version-packets.png')});
 const finalState=await api('/api/v1/status');assert.equal(finalState.active_request,info.active.id,'Export leaves the writer active');
 // Version-bound review, focus delivery and failure/reconnect recovery.
 await page.getByRole('link',{name:'Workspace',exact:true}).click();
 const current=await page.evaluate(()=>window.stud.model.cad);
 let firstFocusFetch,releaseFocus;const focusHeld=new Promise(resolve=>{firstFocusFetch=resolve;});
 const focusGate=new Promise(resolve=>{releaseFocus=resolve;});let interceptedFocus=false;
 await page.route('**/api/v1/jobs/show_*',async route=>{if(!interceptedFocus){interceptedFocus=true;firstFocusFetch();await focusGate;}await route.continue();});
 const firstShow=await command('show',{expected_build:current.build_id,objects:['bench.leg.left.front']});
 await focusHeld;
 const secondShow=await command('show',{expected_build:current.build_id,objects:['bench.fixture.0']});
 releaseFocus();
 for(let i=0;i<150;i++){const job=await api('/api/v1/jobs/'+secondShow.id);if(job.status==='complete')break;await page.waitForTimeout(100);}
 assert.equal((await api('/api/v1/jobs/'+secondShow.id)).status,'complete','The newer focus request receives an actual viewer acknowledgement');
 assert.equal((await api('/api/v1/jobs/'+firstShow.id)).status,'superseded');
 await page.unroute('**/api/v1/jobs/show_*');
 const promptId='browser_review_'+crypto.randomUUID().replaceAll('-','');
 const savedPrompt=await command('save_prompt',{prompt_id:promptId,text:'Remove this loose setup block after fitting.',
  build_id:current.build_id,source_id:current.source_id,manifest_version:current.manifest_version,object_id:'bench.fixture.0',
  camera:await page.evaluate(()=>window.stud.camera),screenshot:'data:image/png;base64,'+(await page.screenshot()).toString('base64')});
 await command('update_prompt',{prompt_id:promptId,expected_revision:0,action:'resolve',addressing_request:info.active.id});
 await writeFile(path.join(info.active.workspace,'design.py'),source.replace('range(2)','range(1)')+'\nraise RuntimeError("Intentional partial-build acceptance failure")\n');
 await page.waitForFunction(()=>window.stud.model?.cad.latest_status==='generation_failed'&&window.stud.model.cad.completion.geometry==='partial'&&window.stud.model.parts.length===13,null,{timeout:45000});
 assert((await page.locator('#error').innerText()).includes('completed parts remain inspectable'));
 await page.screenshot({path:path.join(evidence,'native-partial-failure.png')});
 const partial=await page.evaluate(()=>window.stud.model.cad);
 const partialPromptId='partial_review_'+crypto.randomUUID().replaceAll('-','');
 await command('save_prompt',{prompt_id:partialPromptId,text:'Inspect the block retained from this failed draft.',build_id:partial.build_id,
  source_id:partial.source_id,manifest_version:partial.manifest_version,object_id:'bench.fixture.0'});
 const deletedSource="from stud.cad import Model\nfrom workbench import workbench\nmodel=Model('Workbench after removing setup blocks',units='in')\nworkbench(model,width=84)\n";
 await writeFile(path.join(info.active.workspace,'design.py'),deletedSource);
 await page.waitForFunction(()=>window.stud.model?.parts.length===12&&window.stud.model.cad.completion.geometry==='complete'&&window.stud.model.name==='Workbench after removing setup blocks',null,{timeout:45000});
 const prompts=await api('/api/v1/prompts'),resolved=prompts.find(prompt=>prompt.id===promptId),orphan=prompts.find(prompt=>prompt.id===partialPromptId);
 assert.equal(resolved.target_resolution,'unresolved');assert.equal(resolved.resolved,true);assert.equal(resolved.original_target.id,'bench.fixture.0');
 assert.equal(resolved.source_id,savedPrompt.source_id);assert.equal(orphan.source_id,partial.source_id);assert.equal(orphan.target_resolution,'unresolved');
 await writeFile(path.join(info.active.workspace,'design.py'),'raise RuntimeError("Intentional failure before Model creation")\n');
 await page.waitForFunction(()=>window.stud.model?.cad.latest_status==='generation_failed'&&document.getElementById('error').textContent.includes('Showing previous model'),null,{timeout:45000});
 assert.equal(await page.evaluate(()=>window.stud.model.parts.length),12);
 await page.screenshot({path:path.join(evidence,'native-early-failure.png')});
 await page.route('**/*.mesh',route=>route.fulfill({status:503,body:'Injected missing mesh'}));
 const changedSource=source.replace('width=84','width=85');
 assert.notEqual(changedSource,source,'Missing-asset recovery requires a distinct source and mesh');
 await writeFile(path.join(info.active.workspace,'design.py'),changedSource);
 await page.waitForFunction(()=>document.getElementById('error').textContent.includes('Mesh asset unavailable'),null,{timeout:45000});
 assert.equal(await page.evaluate(()=>window.stud.model.parts.length),12,'Missing new geometry keeps the last display intact');
 await page.unroute('**/*.mesh');
 await page.waitForFunction(()=>window.stud.model?.parts.length===14&&window.stud.model.cad.completion.geometry==='complete',null,{timeout:45000});
 const reconnectSelection=await page.evaluate(()=>window.stud.selected);
 await context.setOffline(true);
 await writeFile(path.join(info.active.workspace,'design.py'),source);
 // Wait for the real coordinator to finish while browser delivery is offline.
 let offlineBuild;
 for(let i=0;i<450;i++){const state=await api('/api/v1/status');const candidate=state.latest_build?await api('/api/v1/jobs/'+state.latest_build):null;if(candidate?.status==='complete'&&candidate.source_id!== (await page.evaluate(()=>window.stud.model.cad.source_id))){offlineBuild=candidate;break;}await page.waitForTimeout(100);}
 assert(offlineBuild,'A new complete build exists while event delivery is disconnected');
 await context.setOffline(false);
 await page.waitForFunction(build=>window.stud.model?.cad.build_id===build&&window.stud.model.cad.completion.geometry==='complete',offlineBuild.id,{timeout:45000});
 assert.equal(await page.evaluate(()=>window.stud.selected),reconnectSelection);
 await page.waitForFunction(()=>document.getElementById('commentstatus').hidden,null,{timeout:15000});
 await page.screenshot({path:path.join(evidence,'native-reconnected.png')});
 const recovery={superseding_focus_acknowledged:true,partial_failure:true,early_failure:true,deleted_prompt_context:true,missing_asset_recovery:true,event_reconnect:true,prompt_id:promptId,partial_prompt_id:partialPromptId};
 await command('cancel',{request_id:info.active.id});
 await page.getByRole('link',{name:'Versions',exact:true}).click();
 await page.locator('#version-new-name').fill('Saved alternative');await page.locator('#version-create').click();await page.waitForFunction(()=>[...document.querySelectorAll('#version-option option')].some(o=>o.textContent==='Saved alternative'));
 const alternative=(await api('/api/v1/options')).find(option=>option.label==='Saved alternative');await page.locator('#version-option').selectOption(alternative.id);
 await page.locator('#version-name').fill('Retained alternative');await page.locator('#version-rename').click();
 await page.waitForFunction(()=>[...document.querySelectorAll('#version-option option')].some(o=>o.textContent==='Retained alternative'));
 for(let n=0;n<150;n++){const state=await api('/api/v1/status');if(!state.active_request&&!state.pending_records.length)break;await page.waitForTimeout(100);}
 await page.evaluate(()=>window.dispatchEvent(new Event('studprojectchange')));
 const restore=page.locator(`[data-restore="${info.baseline.checkpoint}"]`);await page.waitForFunction(()=>[...document.querySelectorAll('[data-restore]')].some(button=>!button.disabled));await restore.click();
 await page.waitForFunction(()=>document.getElementById('version-status').textContent.includes('Restored design saved'),null,{timeout:45000});
 assert.equal(await page.locator('#version-error').innerText(),'');const restored=await api('/api/v1/status');assert.notEqual(restored.option.head,info.baseline.checkpoint);assert.equal(restored.active_request,null);
 assert.deepEqual(errors,[]);
 await writeFile(path.join(evidence,'native-viewer-acceptance.json'),JSON.stringify({project:info.root,baseline:info.baseline.checkpoint,wider:info.wider.checkpoint,active_request:info.active.id,errors,initial_camera:camera,selected,samples,pdf_bytes:bytes.length,recovery},null,2));
 await context.close();context=null;await rename(await video.path(),path.join(evidence,'cadquery-live-animation.webm'));
 console.log(JSON.stringify({status:'passed',project:info.root,partial_batches:true,animated_additions:true,selection_retained:true,comparison_views:2,historical_read_only:true,pdf_bytes:bytes.length,errors}));
}finally{
 await context?.close();await browser?.close();
 if(info)try{await command('shutdown');}catch{}
 if(server.exitCode===null){const timer=setTimeout(()=>server.kill('SIGTERM'),3000);await new Promise(resolve=>server.once('exit',resolve));clearTimeout(timer);}
}
