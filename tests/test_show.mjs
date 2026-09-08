import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createShowTool, registerShowTool} from '../web/show.js';

function fixture() {
 const calls=[];
 const tool=createShowTool({loadModel:async()=>({revision:'r1',parts:[{id:'beam'}]}),
  display:async input=>{calls.push(input);return {model_revision:'r1',view:input.view||'perspective'};}});
 return {tool,calls};
}
test('show frames the model or named parts through one tool',async()=>{
 const {tool,calls}=fixture();
 assert.equal(tool.name,'show');
 assert.equal((await tool.execute({})).ok,true);
 assert.equal((await tool.execute({part_ids:['beam'],view:'front',expected_revision:'r1'})).view,'front');
 assert.equal((await tool.execute({region:{min:[0,0,0],max:[10,20,30]}})).ok,true);
 assert.equal(calls.length,3);
});
test('invalid inputs never change the viewer',async()=>{
 const {tool,calls}=fixture();
 for(const input of [null,[],{view:'rear'},{part_ids:[]},{part_ids:['beam','beam']},
  {part_ids:['beam'],region:{min:[0,0,0],max:[1,1,1]}},
  {region:{min:[0,0,0],max:[1,0,1]}},{region:{min:[0,0,0],max:[1,Infinity,1]}},
  {region:{min:[0,0,0]}},{execute:'python'},{expected_revision:5}]){
  assert.equal((await tool.execute(input)).error.code,'INVALID_INPUT');
 }
 assert.equal(calls.length,0);
});
test('missing parts and stale revisions never partially apply',async()=>{
 const {tool,calls}=fixture();
 assert.equal((await tool.execute({part_ids:['beam','missing']})).error.code,'PART_NOT_FOUND');
 assert.equal((await tool.execute({expected_revision:'old'})).error.code,'REVISION_CONFLICT');
 assert.equal(calls.length,0);
});
test('failed model refresh is not a successful show',async()=>{
 const tool=createShowTool({loadModel:async()=>{throw Error('Build failed');},display:()=>assert.fail()});
 assert.equal((await tool.execute({})).error.code,'MODEL_UNAVAILABLE');
});
test('registration is optional and registers exactly show',async()=>{
 const {tool}=fixture();const registered=[];
 assert.equal(await registerShowTool(undefined,tool),false);
 assert.equal(await registerShowTool({registerTool:t=>registered.push(t)},tool),true);
 assert.deepEqual(registered.map(t=>t.name),['show']);
});
