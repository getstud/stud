import test from 'node:test';
import assert from 'node:assert/strict';
import {OptionComparison,resolveOption,createComparisonTools,visualDifferences} from '../web/option-comparison.js';
const options=[{id:'a',label:'Gabled roof',head:'aaa'},{id:'b',label:'Dormered roof',head:'bbb'},{id:'c',label:'Dormered roof with porch',head:'ccc'}];
const model=(id,shape=id)=>({revision:id,parts:[{id:'roof',name:'Roof',stock:'wood',size:[10,12,4],cad:{shape_key:shape,placement:[id]}}],cad:{presentation:'history',option_id:id,checkpoint:options.find(o=>o.id===id)?.head,build_id:id}});
function fixture(){
 let current=model('a'),display='a';const calls=[];
 const camera={position:[17,31,94],quaternion:[.1,.2,.3,.9],target:[0,4,8],zoom:2,projection:'orthographic',projection_matrix:Array.from({length:16},(_,i)=>i/3)};
 const status={active_option:'a',option:options[0],request:{id:'editing',intent:'Keep editing the gabled roof'}};
 const controller=new OptionComparison({request:async url=>url.endsWith('status')?status:url.endsWith('options')?options:[],run:async(operation,args)=>{
  calls.push({operation,args});
  if(operation==='prepare_option')return {id:args.option_id,status:'complete',result:{views:[model(args.option_id)]}};
  if(operation==='inspect_option')display=args.option_id;
  if(operation==='return_live')display='live';
 },refreshModel:async()=>{current=display==='live'?{...model('a'),cad:{...model('a').cad,presentation:'live',option_id:null}}:model(display);},readViewer:()=>({model:current,camera}),onChange:()=>{}});
 return {controller,calls,camera,status,setCurrent:value=>{current=value;}};
}
test('natural names resolve exactly and ambiguous references return candidates',()=>{
 assert.equal(resolveOption(options,'the gabled version').id,'a');
 assert.equal(resolveOption(options,'Dormered roof').id,'b');
 assert.throws(()=>resolveOption(options,'dormered version'),e=>e.code==='AMBIGUOUS_OPTION'&&e.candidates.length===2);
 assert.throws(()=>resolveOption(options,'red'),e=>e.code==='OPTION_NOT_FOUND'&&e.candidates.length===3);
});
test('N options, cached switching, exact viewpoint and editing identity through real descriptors',async()=>{
 const {controller,camera,status,calls}=fixture(),tools=new Map(createComparisonTools(controller).map(tool=>[tool.name,tool]));
 const initial=structuredClone(camera);
 assert.equal((await tools.get('list_options').execute()).state.options.length,3);
 for(const option of ['b','c','a','b']){
  const response=await tools.get('switch_option').execute({option});assert.equal(response.ok,true);
  assert.equal(response.state.displayed.option_id,option);assert.deepEqual(response.state.viewpoint,initial);
  assert.equal(response.state.editing.request_id,'editing');assert.equal(status.active_option,'a');
 }
 assert.equal(calls.filter(c=>c.operation==='prepare_option').length,3);
 assert.ok(calls.every(c=>!['activate_option','begin','finish'].includes(c.operation)));
 const compared=await tools.get('compare_options').execute({option:'c'});
 assert.equal(compared.baseline.option_id,'b');assert.equal(compared.comparison.option_id,'c');assert.deepEqual(compared.changes[0].changes,['reshaped','moved']);
 const live=await tools.get('return_to_editing_view').execute();assert.equal(live.state.displayed.mode,'live');assert.deepEqual(live.state.viewpoint,initial);
});
test('ambiguous and stale references cannot select a display or writer',async()=>{
 const {controller,calls}=fixture(),tools=createComparisonTools(controller);
 const result=await tools.find(t=>t.name==='switch_option').execute({option:'dormered version'});
 assert.equal(result.error.code,'AMBIGUOUS_OPTION');assert.equal(calls.length,0);
 await assert.rejects(controller.switchOption('b',{expected_head:'old'}),e=>e.code==='CHANGED_HEAD');
 assert.equal(calls.length,0);
 for(const input of [null,{option:'b',activate:true},{option:'b',expected_head:1}])assert.equal((await tools[1].execute(input)).error.code,'INVALID_INPUT');
});
test('a slow earlier selection cannot replace the latest tab',async()=>{
 const {controller,calls}=fixture(),prepare=controller.prepared.bind(controller);let release;
 const gate=new Promise(resolve=>{release=resolve;});
 controller.prepared=async option=>{if(option.id==='b')await gate;return prepare(option);};
 const old=controller.switchOption('b').catch(error=>error);
 await new Promise(resolve=>setImmediate(resolve));
 await controller.switchOption('c');release();assert.equal((await old).code,'SUPERSEDED');
 assert.deepEqual(calls.filter(c=>c.operation==='inspect_option').map(c=>c.args.option_id),['c']);
 assert.equal(controller.state().displayed.option_id,'c');assert.equal(controller.pending,null);
});
test('failed preparation retains the visible design and can be retried',async()=>{
 const {controller}=fixture(),run=controller.run;let failed=true;
 controller.run=async(operation,args)=>{if(operation==='prepare_option'&&failed)throw new Error('Mesh unavailable');return run(operation,args);};
 await assert.rejects(controller.switchOption('b'),/Mesh unavailable/);assert.equal(controller.state().displayed.option_id,'a');assert.equal(controller.pending,null);
 failed=false;await controller.switchOption('b');assert.equal(controller.state().displayed.option_id,'b');
});
test('comparison distinguishes added, removed and appearance changes',()=>{
 const left=model('a','same'),right=model('a','same');right.parts[0].color='blue';right.parts.push({...right.parts[0],id:'dormer'});left.parts.push({...left.parts[0],id:'chimney'});
 assert.deepEqual(visualDifferences(left,right).map(row=>[row.id,...row.changes]),[['roof','appearance'],['chimney','removed'],['dormer','added']]);
});

test('an invalid voice reference does not strand an in-flight tab selection',async()=>{
 const {controller}=fixture(),prepare=controller.prepared.bind(controller);let release;
 const gate=new Promise(resolve=>{release=resolve;});controller.prepared=async option=>{await gate;return prepare(option);};
 const pending=controller.switchOption('b');await new Promise(resolve=>setImmediate(resolve));
 await assert.rejects(controller.switchOption('unknown'),error=>error.code==='OPTION_NOT_FOUND');release();await pending;
 assert.equal(controller.pending,null);assert.equal(controller.state().displayed.option_id,'b');
});

test('prepared display is installed without a blocking full-model refresh',async()=>{
 const {controller,setCurrent}=fixture();let installs=0,refreshes=0;
 controller.displayPrepared=async data=>{setCurrent(data);installs++;assert.equal(data.cad.presentation,'history');assert.equal(data.cad.option_id,'b');};
 controller.refreshModel=async()=>{refreshes++;};
 await controller.switchOption('b');assert.equal(installs,1);assert.equal(refreshes,0);
});

test('a canceled renderer installation cannot report a successful tab switch',async()=>{
 const {controller}=fixture();controller.displayPrepared=async()=>{};
 const tool=createComparisonTools(controller).find(tool=>tool.name==='switch_option');
 const result=await tool.execute({option:'b'});assert.equal(result.ok,false);assert.equal(result.error.code,'DISPLAY_INTERRUPTED');
 assert.equal(controller.state().displayed.option_id,'a');assert.equal(controller.pending,null);
});

test('an older metadata response cannot overwrite a newer name and head',async()=>{
 const {controller}=fixture();let calls=0,release;
 const old=new Promise(resolve=>{release=resolve;});
 controller.request=async url=>{
  const older=calls++<3;if(older)await old;
  if(url.endsWith('/options'))return [{...options[0],label:older?'Old label':'New label',head:older?'old':'new'}];
  if(url.endsWith('/status'))return {active_option:'a',option:options[0]};
  return [];
 };
 const first=controller.refresh();await controller.refresh();release();await first;
 assert.equal(controller.options[0].label,'New label');assert.equal(controller.options[0].head,'new');
});

test('superseded initial readers wait for the newest metadata instead of seeing empty options',async()=>{
 const {controller}=fixture();let calls=0,releaseOld,releaseNew,finished=false;
 const old=new Promise(resolve=>{releaseOld=resolve;}),newest=new Promise(resolve=>{releaseNew=resolve;});
 const request=controller.request;
 controller.request=async url=>{const older=calls++<3;await (older?old:newest);return request(url);};
 const initial=controller.switchOption('b').then(result=>{finished=true;return result;});
 const latest=controller.refresh();releaseOld();await new Promise(resolve=>setImmediate(resolve));
 assert.equal(finished,false);releaseNew();await latest;await initial;
 assert.equal(controller.state().displayed.option_id,'b');
});
