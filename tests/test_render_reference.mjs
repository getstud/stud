import {test} from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {ProjectEvents} from '../web/project-events.js';
import {createControlActivity,createViewerToolRunner} from '../web/viewer-tools.js';
import {createRenderReferenceTool,captureUntextured,renderBrief} from '../web/render-reference.js';

function fixture(){
 const model={name:'Shed',revision:'cedar:final',units:'in',stocks:{cedar:{name:'Cedar siding',specification:{species:'western red cedar',finish:'clear matte'}}},
  parts:[{id:'front',name:'Front siding',stock:'cedar',assembly:'Exterior',color:'#bd8050'},{id:'back',name:'Back siding',stock:'cedar',assembly:'Exterior'}],
  cad:{presentation:'history',build_id:'cedar',source_id:'source-cedar',checkpoint:'saved-cedar',option_id:'cedar-option',completion:{geometry:'complete'},latest_build_id:'cedar',latest_status:'complete'}};
 const state={model,camera:{position:[2,3,4],projection:'orthographic'},visible_part_ids:['front']};
 const calls=[];
 const tool=createRenderReferenceTool({readViewer:()=>state,capture:()=>{calls.push('capture');return 'png';},save:async payload=>{calls.push(payload);return {reference_path:'/project/exports/reference.png'};}});
 return {state,calls,tool};
}
test('capture binds material brief and camera to the displayed saved option, excluding hidden parts',async()=>{
 const {tool,calls,state}=fixture(),before=structuredClone(state);
 const result=await tool.execute({expected_revision:'cedar:final',lighting:'Warm afternoon light',finishes:'Clear matte cedar'});
 assert.equal(result.ok,true);assert.equal(result.reference_path,'/project/exports/reference.png');
 assert.equal(result.brief.displayed.checkpoint,'saved-cedar');
 assert.deepEqual(result.brief.hidden_part_ids,['back']);
 assert.equal(result.brief.materials[0].specifications[0].species,'western red cedar');
 assert.match(result.brief.prompt,/Warm afternoon light/);assert.match(result.brief.prompt,/exact viewpoint/);
 assert.match(result.next,/image-generation tool/);assert.deepEqual(state,before);
 assert.equal(calls[1].brief.revision,'cedar:final');
 // Later option/material changes cannot rewrite an already captured brief.
 state.model.cad.checkpoint='later';state.camera.position[0]=90;
 assert.equal(result.brief.displayed.checkpoint,'saved-cedar');assert.equal(result.brief.camera.position[0],2);
});
test('invalid, stale, partial, failed, exploded, hidden and busy views never create artifacts',async()=>{
 const cases=[
  [{},'INVALID_INPUT'],[{expected_revision:'old'},'REVISION_CONFLICT'],[{expected_revision:'cedar:final',view:'front'},'INVALID_INPUT'],
  [{expected_revision:'cedar:final',finishes:2},'INVALID_INPUT'],[{expected_revision:'cedar:final',lighting:'x'.repeat(1001)},'INVALID_INPUT'],
 ];
 for(const [input,code] of cases){const {tool,calls}=fixture();assert.equal((await tool.execute(input)).error.code,code);assert.equal(calls.length,0);}
 for(const [patch,code] of [[{busy:true},'VIEWER_BUSY'],[{exploded:true},'ASSEMBLED_VIEW_REQUIRED'],[{assemblyReview:true},'ASSEMBLED_VIEW_REQUIRED'],[{loadFailed:true},'BUILD_NOT_READY'],[{visible_part_ids:[]},'EMPTY_VIEW']]){
  const {tool,state,calls}=fixture();Object.assign(state,patch);assert.equal((await tool.execute({expected_revision:'cedar:final'})).error.code,code);assert.equal(calls.length,0);
 }
 for(const patch of [{completion:{geometry:'partial'}},{presentation:'live',latest_build_id:'failed-build',latest_status:'generation_failed'},
  ...['queued','running','generation_failed','failed','canceled','interrupted','superseded',undefined].map(latest_status=>({presentation:'live',latest_status}))]){
  const {tool,state,calls}=fixture();Object.assign(state.model.cad,patch);assert.equal((await tool.execute({expected_revision:'cedar:final'})).error.code,'BUILD_NOT_READY');assert.equal(calls.length,0);
 }
});
test('capture cancellation and save failures cannot report a successful generated image',async()=>{
 const {tool,calls,state}=fixture(),abort=new AbortController();abort.abort();
 assert.equal((await tool.execute({expected_revision:'cedar:final'},{signal:abort.signal})).error.code,'CANCELED');assert.equal(calls.length,0);
 const saving=createRenderReferenceTool({readViewer:()=>state,capture:()=>'',save:async()=>{throw Error('Disk full');}});
 assert.equal((await saving.execute({expected_revision:'cedar:final'})).error.message,'Disk full');
 const late=new AbortController();
 const cancelSaving=createRenderReferenceTool({readViewer:()=>state,capture:()=>'',save:async()=>{late.abort();return {reference_path:'saved'};}});
 assert.equal((await cancelSaving.execute({expected_revision:'cedar:final'},{signal:late.signal})).error.code,'CANCELED');
});
test('untextured capture strips overlays and original materials without changing live geometry or camera',()=>{
 const group=new THREE.Group(),mesh=new THREE.Mesh(new THREE.BoxGeometry(2,4,6),new THREE.MeshStandardMaterial({color:'red',emissive:'green',opacity:.3,transparent:true}));
 mesh.position.set(3,7,9);mesh.rotation.z=.4;group.position.set(11,0,2);group.add(mesh);
 mesh.add(new THREE.LineSegments(new THREE.EdgesGeometry(mesh.geometry),new THREE.LineBasicMaterial({color:'orange'})));
 const camera=new THREE.OrthographicCamera(-10,10,8,-8,.1,100);camera.position.set(10,20,30);camera.zoom=1.3;camera.lookAt(0,0,0);camera.updateProjectionMatrix();
 const beforeCamera=camera.clone(),beforeMaterial=mesh.material;let captured,disposed=false,lost=false,bufferDisposed=false;
 mesh.geometry.addEventListener('dispose',()=>bufferDisposed=true);
 const renderer={shadowMap:{},setPixelRatio(){},setSize(w,h){assert.deepEqual([w,h],[2048,1600]);},render(scene,clonedCamera){captured=scene;
  assert.notEqual(clonedCamera,camera);assert.deepEqual(clonedCamera.projectionMatrix,beforeCamera.projectionMatrix);
 },domElement:{toDataURL:()=> 'data:image/png;base64,test'},dispose(){disposed=true;},forceContextLoss(){lost=true;}};
 assert.equal(captureUntextured({THREE,meshes:[mesh],camera,width:2048,height:1600,createRenderer:()=>renderer}),'data:image/png;base64,test');
 const result=captured.children.find(child=>child.isMesh);
 assert.equal(result.children.length,0);assert.equal(result.geometry,mesh.geometry);assert.deepEqual(result.matrix,mesh.matrixWorld);
 assert.equal(result.material.map,null);assert.equal(result.material.opacity,1);assert.equal(result.material.emissive.getHex(),0);
 assert.equal(mesh.material,beforeMaterial);assert.equal(mesh.children.length,1);assert.equal(mesh.parent,group);
 assert.deepEqual(camera.projectionMatrix,beforeCamera.projectionMatrix);assert.deepEqual(camera.position,beforeCamera.position);
 assert(disposed&&lost);assert.equal(bufferDisposed,false);
 renderer.render=()=>{throw Error('GPU error');};disposed=false;lost=false;
 assert.throws(()=>captureUntextured({THREE,meshes:[mesh],camera,width:2048,height:1600,createRenderer:()=>renderer}),/GPU error/);
 assert(disposed&&lost);assert.equal(mesh.material,beforeMaterial);assert.equal(bufferDisposed,false);
});
test('legacy materials and dimensions remain usable in the render brief',()=>{
 const {state}=fixture();delete state.model.cad;delete state.model.stocks.cedar.specification;
 const brief=renderBrief(state.model,['front'],state.camera,{});
 assert.equal(brief.displayed.presentation,'legacy');assert.equal(brief.geometry_units,'in');assert.deepEqual(brief.materials[0].specifications,[{}]);
});
test('same-product parts retain distinct finish assignments and hidden finishes never enter the prompt',()=>{
 const {state}=fixture();
 state.model.parts[0].material_specifications=[{finish:'red paint'},{grain:'vertical'}];
 state.model.parts[1].material_specifications=[{finish:'blue paint'}];
 const front=renderBrief(state.model,['front'],state.camera,{});
 assert.deepEqual(front.materials[0].specifications,[{finish:'red paint'},{grain:'vertical'}]);
 assert.match(front.prompt,/red paint/);assert.match(front.prompt,/vertical/);assert.doesNotMatch(front.prompt,/blue paint|clear matte/);
 const both=renderBrief(state.model,['front','back'],state.camera,{});
 assert.equal(both.materials.length,2);
 assert.deepEqual(both.materials.map(m=>m.parts.map(p=>p.id)),[['front'],['back']]);
 state.model.parts[0].material_specifications=[];
 assert.deepEqual(renderBrief(state.model,['front'],state.camera,{}).materials[0].specifications,[]);
});
test('build-start events refresh readiness before the first geometry publication',async()=>{
 const {state,tool,calls}=fixture();state.model.cad.presentation='live';
 const source=readFileSync(new URL('../web/app.js',import.meta.url),'utf8');
 const registration=source.slice(source.indexOf('const projectEvents=new ProjectEvents('),source.indexOf('void projectEvents.connect()'));
 let refreshes=0;
 const events=runInNewContext(registration+';projectEvents',{
  ProjectEvents,cadScene:{invalidate(){}},window:{dispatchEvent(){}},CustomEvent:class{},
  refreshFromEvent(){refreshes++;state.busy=true;},
 });
 assert.equal((await tool.execute({expected_revision:state.model.revision})).ok,true);calls.length=0;
 events.accept({sequence:1,type:'build_started',build_id:'next'});
 assert.equal(refreshes,1);
 assert.equal((await tool.execute({expected_revision:state.model.revision})).error.code,'VIEWER_BUSY');
 // The response can retain the previous geometry, but carries the pending job.
 Object.assign(state.model.cad,{latest_build_id:'next',latest_status:'queued'});state.busy=false;
 assert.equal((await tool.execute({expected_revision:state.model.revision})).error.code,'BUILD_NOT_READY');
 assert.equal(calls.length,0);
 events.accept({sequence:2,type:'request_canceled'});assert.equal(refreshes,2);
 Object.assign(state.model.cad,{latest_build_id:'cedar',latest_status:'complete'});state.busy=false;
 assert.equal((await tool.execute({expected_revision:state.model.revision})).ok,true);
});

test('shared Stop suppresses a pending capture response and queued capture, then permits another capture',async()=>{
 const {state}=fixture(),before=structuredClone(state),activityStates=[];
 const activity=createControlActivity(active=>activityStates.push(active),()=>Promise.resolve());
 const runner=createViewerToolRunner({context:()=>({model_revision:state.model.revision}),activity});
 let release,started,captures=0;
 const saving=new Promise(resolve=>started=resolve),gate=new Promise(resolve=>release=resolve);
 const wrapped=runner(createRenderReferenceTool({readViewer:()=>state,capture:()=>{captures++;return 'png';},
  save:async(_payload,{signal})=>{assert(signal instanceof AbortSignal);started();await gate;return {reference_path:'reference.png'};}}));
 const first=wrapped.execute({expected_revision:state.model.revision});await saving;
 const queued=wrapped.execute({expected_revision:state.model.revision});runner.stop();release();
 assert.equal((await first).error.code,'CONTROL_STOPPED');assert.equal((await queued).error.code,'CONTROL_STOPPED');
 assert.equal(captures,1);assert.equal(activityStates.at(-1),false);assert.deepEqual(state,before);
 const fresh=await wrapped.execute({expected_revision:state.model.revision});
 assert.equal(fresh.ok,true);assert.equal(fresh.context.model_revision,state.model.revision);assert.equal(captures,2);assert.deepEqual(state,before);
});

test('shared control entry preserves the exact camera target while resetting orbit inertia',()=>{
 const source=readFileSync(new URL('../web/app.js',import.meta.url),'utf8');
 const body=source.slice(source.indexOf('function stopViewerMotion('),source.indexOf('function assertViewerAvailable('));
 const camera=new THREE.PerspectiveCamera(),target=new THREE.Vector3(60.00000000000001,65.75000000000001,-47.999999999999986);
 camera.position.set(271,224,226);camera.lookAt(target);
 const before=camera.clone();let disposed=0;
 const context={camera,controls:{target:target.clone(),dispose(){disposed++;}},currentView:'perspective',renderer:{domElement:{}},
  buildCamera:{stop(){}},buildAnimation:{finish(){}},document:{body:{classList:{contains:()=>true}}},
  OrbitControls:class{target=new THREE.Vector3();dispose(){disposed++;}update(){this.target.x+=Number.EPSILON*64;camera.position.x++;camera.quaternion.identity();}}};
 const stop=runInNewContext(body+';stopViewerMotion',context);
 stop();stop();
 assert.equal(disposed,2);assert.deepEqual(context.controls.target,target);
 assert.deepEqual(camera.position,before.position);assert.deepEqual(camera.quaternion.toArray(),before.quaternion.toArray());assert.equal(context.controls.enabled,false);
});
