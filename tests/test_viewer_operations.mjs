import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {setup} from './helpers/viewer-fixture.mjs';
import {createViewerOperations} from '../web/viewer-operations.js';
function fixture(){
 const c=setup();let page='workspace',view='front',camera=new THREE.OrthographicCamera(-50,50,40,-40,.1,10000),controls={target:new THREE.Vector3(30,20,0),update(){}};
 camera.position.set(30,20,100);camera.lookAt(controls.target);const changes=[];
 c.environment.entries=new Map();c.environment.enabled=true;c.environment.visibilityFor=()=>true;c.environment.setVisible=()=>{};
 const a={get model(){return c.model},get meshes(){return c.meshes},get selected(){return c.selected},get page(){return page},get view(){return view},get camera(){return camera},get controls(){return controls},get drawing(){return c.assemblyReview},get versions(){return c.versions},get validation(){return c.validation},
  get exploded(){return c.$('explode').checked},set exploded(v){c.$('explode').checked=v},get dimensions(){return c.$('dims').getAttribute('aria-pressed')==='true'},set dimensions(v){c.$('dims').setAttribute('aria-pressed',String(v))},get gridVisible(){return c.grid.visible},set gridVisible(v){c.grid.visible=v},get environmentEnabled(){return c.$('environmenttoggle').checked},
  visibility:c.visibility,hiddenParts:c.hiddenParts,environment:c.environment,measurement:c.partMeasurement,designBase:c.designBaseElevation,label:p=>p.id,
  applyDisplay:c.applyDisplay,endDrawing:c.endAssemblyReview,openDrawing:c.openAssemblyDrawing,select:m=>{c.selected=m},selectPart:c.revealAndSelectPart,highlight(){},highlights:()=>[],setEnvironmentEnabled:v=>{c.$('environmenttoggle').checked=v;c.environment.setEnabled(v)},
  assertAvailable(){},stop(){changes.push('stop')},showWorkspace(){changes.push('workspace');page='workspace'},showPage:p=>page=p,render(){},setView:name=>{view=name;if(name==='perspective'&&!camera.isPerspectiveCamera){camera=new THREE.PerspectiveCamera(38,1.5,.1,10000);camera.position.set(30,20,100);camera.lookAt(controls.target);}},clearWarnings(){},clearShow(){},hasPriceDrafts:()=>false,
 };
 c.select=a.select;c.setView=name=>{view=name};
 return {...createViewerOperations(a),a,c,changes,setFront(){view='front';camera=new THREE.OrthographicCamera(-50,50,40,-40,.1,10000);camera.position.set(30,20,100);camera.lookAt(controls.target);},setFlight(){view='firstperson';camera=new THREE.PerspectiveCamera();controls={update(){}};page='costs';}};
}
test('voice selection uses the UI drawing transition and never selects hidden geometry',()=>{
 const f=fixture();f.operations.viewer({action:'drawing',assembly:'Frame',view:'front',level:7});
 f.operations.viewer({action:'select',part_ids:['long-1-31.75']});
 assert.equal(f.c.assemblyReview.level,31.75);assert.equal(f.c.selected.visible,true);
 f.operations.viewer({action:'select',part_ids:['leg']});assert.equal(f.c.assemblyReview,null);assert.equal(f.c.selected.visible,true);
});
test('drawing camera back retains the drawing’s complete return state and All levels',()=>{
 const f=fixture();f.a.hiddenParts.add('leg');
 f.operations.viewer({action:'drawing',assembly:'Frame',view:'front',level:7});
 f.operations.camera({action:'move',delta:[2,3,4]});f.operations.camera({action:'back'});
 f.operations.viewer({action:'drawing',assembly:'Frame',view:'front',level:null});
 assert.equal(f.c.assemblyReview.level,null);assert.equal(f.c.meshes.filter(m=>m.visible).length,8);
 f.c.endAssemblyReview(false);
 assert.equal(f.a.exploded,true);assert.equal(f.a.dimensions,false);assert.equal(f.a.environmentEnabled,true);assert.equal(f.c.environment.enabled,true);
 assert.deepEqual([...f.a.visibility],[['Frame',false],['Legs',true]]);assert(f.a.hiddenParts.has('leg'));
});
test('invalid targets and unsupported flight zoom leave page, camera and history alone',()=>{
 const f=fixture();f.setFlight();const before=f.context();
 assert.throws(()=>f.operations.camera({action:'zoom',factor:2}),/while flying/);
 assert.throws(()=>f.operations.viewer({action:'hide',part_ids:['missing']}),/Unknown parts/);
 assert.deepEqual(f.context(),before);assert.deepEqual(f.changes,[]);
 assert.throws(()=>f.operations.camera({action:'back'}),/No previous view/);
});
test('hiding checks closes a directly requested passing finding even when the warning list is closed',()=>{
 const f=fixture();let closed=0;
 f.c.$('validation-toggle').setAttribute('aria-pressed','false');
 f.c.$('validation-toggle').onclick=()=>assert.fail('The closed warning list should stay closed');
 f.c.$('close-warning').onclick=()=>{f.c.$('warning-detail').hidden=true;closed++;};
 f.c.$('warning-detail').hidden=false;
 f.c.setWarningsVisible(false);
 assert.equal(f.c.$('warning-detail').hidden,true);assert.equal(closed,1);
});
test('completed option creation remains successful if ancillary status/table reads fail',async t=>{
 const f=fixture();f.c.model.cad={build_id:'build'};let created=0;
 f.c.versions={refresh:async()=>{throw Error('Offline')}};
 t.mock.method(globalThis,'fetch',async(url,options)=>{
  if(options?.method==='POST'){created++;return {ok:true,json:async()=>({id:'option_created',label:'Alternative'})};}
  throw Error('Offline after completed mutation');
 });
 const result=await f.operations.versions({action:'create',name:'Alternative',base_checkpoint:'checkpoint'});
 assert.equal(result.result.id,'option_created');assert.equal(result.warnings.length,2);assert.equal(created,1);
});
test('a completed plan still delivers immutable downloads if its table cannot refresh',async t=>{
 const f=fixture();f.c.model.cad={build_id:'build',checkpoint:'checkpoint'};f.c.versions={refresh:async()=>{throw Error('Offline')}};
 t.mock.method(globalThis,'fetch',async(url,options)=>({ok:true,json:async()=>options?.method==='POST'?{id:'plans_1',status:'complete',result:{files:{'plans.pdf':'sha','parts.csv':'sha'}}}:{option:{id:'option'},request:null}}));
 globalThis.location={href:'http://127.0.0.1:8765/'};t.after(()=>{delete globalThis.location;});
 const result=await f.operations.plans({action:'generate'});
 assert.equal(result.packet.status,'complete');assert.equal(result.downloads.length,3);assert.equal(result.warnings.length,1);
});


test('sequence preparation validates every subject before mutation and leaves the starting view intact',()=>{
 const f=fixture();f.a.setView('perspective');const before=f.context();
 assert.throws(()=>f.operations.sequence({action:'prepare',title:'Bad',steps:[{label:'Reset',reset:true},{label:'Missing',part_ids:['missing']}]}),/Unknown parts/);
 assert.deepEqual(f.context(),before);
 const prepared=f.operations.sequence({action:'prepare',title:'Frame',steps:[{label:'Overview',reset:true},{label:'Lift',explode:true,part_ids:['leg'],highlight:['leg']} ]});
 assert.equal(prepared.sequence.status,'ready');assert.equal(prepared.sequence.duration,8);assert.deepEqual(f.context(),before);
});
test('reduced motion keeps timed holds but removes camera and part motion',()=>{
 const f=fixture();f.a.setView('perspective');f.a.sequenceReducedMotion=()=>true;
 const prepared=f.operations.sequence({action:'prepare',title:'Still tour',steps:[{label:'Overview',reset:true,duration:5,hold:3}]});
 assert.equal(prepared.sequence.duration,3);
});

test('resuming after a projection change reinitializes the transition and updates moving highlights',async t=>{
 const f=fixture();f.a.setView('perspective');let frame,clock=0,updates=0;
 globalThis.requestAnimationFrame=callback=>{frame=callback;return 1};globalThis.cancelAnimationFrame=()=>{frame=null};
 t.after(()=>{delete globalThis.requestAnimationFrame;delete globalThis.cancelAnimationFrame;});t.mock.method(performance,'now',()=>clock);
 f.a.updateHighlights=()=>updates++;
 f.operations.sequence({action:'prepare',title:'Lift',steps:[{label:'Lift',reset:true,explode:true,highlight:['leg'],duration:2,hold:2}]});
 f.operations.sequence({action:'play'});clock=500;frame(clock);f.sequence.pause();
 f.setFront();f.operations.sequence({action:'resume'});clock=1000;frame(clock);
 assert.equal(f.a.camera.isPerspectiveCamera,true);assert(updates>2);f.operations.sequence({action:'stop'});
});
test('inspect rejects competing checkpoint and option targets before dispatch',async()=>{
 const f=fixture();f.c.model.cad={build_id:'build'};f.a.optionComparison={switchOption:()=>assert.fail('Ambiguous target was dispatched')};
 await assert.rejects(f.operations.versions({action:'inspect',checkpoint:'checkpoint',option_id:'option'}),/Specify one/);
 assert.equal(f.changes.length,0);
});
