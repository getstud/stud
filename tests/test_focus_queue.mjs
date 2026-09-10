import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync('web/app.js','utf8');
const functionText=source.slice(source.indexOf('let focusTask=null'),source.indexOf('const projectEvents='));
let releaseA;const requested=[],shown=[];
const context=vm.createContext({
  queueMicrotask,viewerActivity:async action=>action(),
  fetch:async (url,options)=>{
    requested.push(url);
    if(url.endsWith('/A'))await new Promise(resolve=>releaseA=resolve);
    return {ok:true,json:async()=>({status:'waiting_viewer',build_id:'b',objects:['beam']})};
  },
  loadModel:async()=>{},model:{cad:{build_id:'b'}},$:()=>({}),
  displayShow:input=>shown.push(input),
  camera:{position:{toArray:()=>[0,0,0]},quaternion:{toArray:()=>[0,0,0,1]}},
  controls:{target:{toArray:()=>[0,0,0]}},console,
});
vm.runInContext(functionText,context);
vm.runInContext("focusTask='A';void applyFocusTask()",context);
await new Promise(resolve=>setImmediate(resolve));
vm.runInContext("focusTask='B';void applyFocusTask()",context);
releaseA();await new Promise(resolve=>setImmediate(resolve));
assert.deepEqual(requested,['/api/v1/jobs/A','/api/v1/jobs/B','/api/v1/command']);
assert.equal(shown.length,1);
assert.equal(vm.runInContext('focusTask',context),null);
console.log('Superseding focus request was drained and acknowledged:',requested);
