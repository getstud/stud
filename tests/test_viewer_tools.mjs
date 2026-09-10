import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createViewerToolRunner,createViewerTools,createControlActivity,registerViewerTools,viewerSchemas,validate} from '../web/viewer-tools.js';
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function fixture(overrides={}){
 const calls=[],activity=[];const context=()=>({model_revision:'r1'});
 const operations=Object.fromEntries(Object.keys(viewerSchemas).map(name=>[name,async input=>{calls.push([name,input]);return {result:name};}]));
 const tools=createViewerTools({operations:{...operations,...overrides},context,activity:createControlActivity(active=>activity.push(active),tick)});
 return {tools:Object.fromEntries(tools.map(t=>[t.name,t])),calls,activity};
}
test('all parity tools register through the real descriptor contract; unsupported browsers remain usable',async()=>{
 const {tools}=fixture(),registered=[];
 assert.equal(await registerViewerTools(undefined,Object.values(tools)),false);
 assert.equal(await registerViewerTools({registerTool:t=>registered.push(t)},Object.values(tools)),true);
 assert.deepEqual(registered.map(t=>t.name),Object.keys(viewerSchemas));
 for(const tool of registered)assert.equal(typeof tool.execute,'function');
});
test('bad inputs and stale revisions cannot partially mutate viewer or estimates',async()=>{
 const {tools,calls,activity}=fixture();
 for(const [name,input] of [['viewer',{action:'hide',part_ids:[]}],['viewer',{action:'dimensions',enabled:'true'}],['camera',{action:'pose',position:[1,2,Infinity],target:[0,0,0]}],['camera',{action:'zoom',factor:0}],['estimate',{action:'set',key:'wood',unit_price:-1}],['versions',{action:'activate',option_id:'x'}],['plans',{action:'generate',paper:'illegal'}],['checks',{action:'read',comments:true}]])assert.equal((await tools[name].execute(input)).error.code,'INVALID_INPUT');
 assert.deepEqual(activity,[]);
 assert.equal((await tools.viewer.execute({action:'reset',expected_revision:'old'})).error.code,'REVISION_CONFLICT');
 assert.deepEqual(calls,[]);
 assert.deepEqual(activity,[true,false]);
});
test('read-only questions do not glow or navigate; mutations return displayed context',async()=>{
 const {tools,activity}=fixture();
 for(const [name,input] of [['viewer_context',{}],['inspect_parts',{}],['estimate',{action:'read'}],['versions',{action:'list'}],['checks',{action:'read'}],['plans',{action:'list'}]])assert.equal((await tools[name].execute(input)).ok,true);
 assert.deepEqual(activity,[]);
 const shown=await tools.viewer.execute({action:'isolate',part_ids:['beam']});
 assert.equal(shown.context.model_revision,'r1');assert.deepEqual(activity,[true,false]);
});
test('activity lasts through awaited work, nested stop, paint, and failures; queued actions stay ordered',async()=>{
 let release;const order=[];
 const f=fixture({plans:async()=>{order.push('plans');await new Promise(resolve=>release=resolve);throw Error('Failed job');},viewer:async()=>{order.push('viewer');},camera:async()=>{order.push('stop');}});
 const pending=f.tools.plans.execute({action:'generate'}),queued=f.tools.viewer.execute({action:'reset'});
 await tick();await tick();assert.deepEqual(f.activity,[true]);assert.deepEqual(order,['plans']);
 await f.tools.camera.execute({action:'stop'});assert.deepEqual(order,['plans','stop']);assert.deepEqual(f.activity,[true]);
 release();assert.equal((await pending).ok,false);assert.equal((await queued).ok,true);assert.deepEqual(order,['plans','stop','viewer']);
 assert.deepEqual(f.activity,[true,false,true,false]);
});
test('schemas reject extra fields even for otherwise valid actions',()=>{
 assert.throws(()=>validate(viewerSchemas.viewer,{action:'reset',arbitrary:'code'}));
 assert.throws(()=>validate(viewerSchemas.camera,{action:'move',delta:[1,2]}));
 assert.throws(()=>validate(viewerSchemas.inspect_parts,{part_ids:['a','a']}));
 assert.doesNotThrow(()=>validate(viewerSchemas.estimate,{action:'set',key:'line',unit_price:8,quantity:4}));
});

test('legacy show and feature-owned tools share the same execution queue',async()=>{
 const {createViewerToolRunner}=await import('../web/viewer-tools.js');
 const order=[];let release;
 const wrap=createViewerToolRunner({context:()=>({model_revision:'r1'}),activity:fn=>fn()});
 const show=wrap({name:'show',execute:async()=>{order.push('show');await new Promise(resolve=>release=resolve);return {ok:true};}});
 const switchOption=wrap({name:'switch_option',execute:async()=>{order.push('switch');return {ok:true};}});
 const first=show.execute({}),second=switchOption.execute({});await tick();assert.deepEqual(order,['show']);release();await Promise.all([first,second]);assert.deepEqual(order,['show','switch']);
});

test('user Stop releases controls immediately, aborts active work and skips queued commands',async()=>{
 const {createViewerToolRunner}=await import('../web/viewer-tools.js');
 const state=[],calls=[];let release;
 const activity=createControlActivity(value=>state.push(value),tick);
 const wrap=createViewerToolRunner({context:()=>({model_revision:'r1'}),activity});
 const slow=wrap({name:'slow',execute:async(input,{signal})=>{await new Promise(resolve=>release=resolve);signal.throwIfAborted();calls.push('late display');return {ok:true};}});
 const next=wrap({name:'next',execute:async()=>{calls.push('next');return {ok:true};}});
 const pending=slow.execute({}),queued=next.execute({});await tick();await tick();
 wrap.stop();assert.equal(state.at(-1),false);
 release();assert.equal((await pending).error.code,'CONTROL_STOPPED');
 assert.equal((await queued).error.code,'CONTROL_STOPPED');assert.deepEqual(calls,[]);
 assert.equal((await next.execute({})).ok,true);assert.deepEqual(calls,['next']);assert.equal(state.at(-1),false);
});

test('AI camera lock blocks canvas input but leaves Stop usable and releases input afterward',async()=>{
 const {installCameraInputGuard}=await import('../web/viewer-tools.js');
 let locked=false;const listeners=new Map();
 const root={addEventListener:(name,fn,options)=>{assert.equal(options.capture,true);assert.equal(options.passive,false);listeners.set(name,fn);},removeEventListener:name=>listeners.delete(name)};
 const dispose=installCameraInputGuard({root,isControlled:()=>locked});
 const event=canvas=>({target:{closest:()=>canvas?{}:null},preventDefault(){this.prevented=true;},stopImmediatePropagation(){this.stopped=true;}});
 locked=true;
 for(const name of ['pointerdown','pointermove','pointerup','wheel','keydown','keyup']){
  const e=event(true);listeners.get(name)(e);assert.equal(e.prevented,true);assert.equal(e.stopped,true);
 }
 const stop=event(false);listeners.get('pointerdown')(stop);assert.equal(stop.stopped,undefined);
 locked=false;const free=event(true);listeners.get('pointerdown')(free);assert.equal(free.stopped,undefined);
 dispose();assert.equal(listeners.size,0);
});

test('activity setup failures restore controls and do not strand the next action',async()=>{
 const states=[];let fail=true;
 const activity=createControlActivity(active=>{states.push(active);if(active&&fail){fail=false;throw Error('Setup failed');}},tick);
 await assert.rejects(activity(async()=>{}),/Setup failed/);
 assert.deepEqual(states,[true,false]);
 await activity(async()=>{});assert.deepEqual(states,[true,false,true,false]);
});

test('sequence Stop bypasses queued camera work and aborts it immediately',async()=>{
 const context=()=>({model_revision:'r1'}),activity=createControlActivity(()=>{},tick);
 const wrap=createViewerToolRunner({context,activity});
 const tools=Object.fromEntries(createViewerTools({context,activity,wrap,operations:{
  camera:(_,{signal})=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(signal.reason),{once:true})),
  sequence:()=>{wrap.stop();return {sequence:{status:'stopped'}};},
 }}).map(tool=>[tool.name,tool]));
 const pending=tools.camera.execute({action:'move',delta:[10,0,0],duration:10});await tick();await tick();
 const stop=await tools.sequence.execute({action:'stop'});assert.equal(stop.ok,true);
 assert.equal((await pending).error.code,'CONTROL_STOPPED');
});
test('feature-owned read-only descriptors are identified before execution',async()=>{
 const seen=[],wrap=createViewerToolRunner({context:()=>({}),activity:async fn=>fn(),before:(name,input,metadata)=>seen.push(metadata.readOnly)});
 const tool=wrap({name:'list_options',annotations:{readOnlyHint:true},execute:async()=>({ok:true})});
 await tool.execute({});assert.deepEqual(seen,[true]);
});
