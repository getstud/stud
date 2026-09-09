import {test} from 'node:test';
import assert from 'node:assert/strict';
import {selectionRectangle, cropPixels, installAreaCapture} from '../web/area-capture.js';

test('dragging in either direction makes the same rectangle',()=>{
  const a={x:20,y:30}, b={x:90,y:100};
  assert.deepEqual(selectionRectangle(a,b,200,200),{x:20,y:30,width:70,height:70});
  assert.deepEqual(selectionRectangle(b,a,200,200),selectionRectangle(a,b,200,200));
});
test('dragging outside the viewer stays inside the screenshot',()=>{
  const rect=selectionRectangle({x:80,y:40},{x:-50,y:300},100,120);
  assert.deepEqual(rect,{x:0,y:40,width:80,height:80});
});
test('screen coordinates map to actual image pixels on scaled displays',()=>{
  const rect={x:10.5,y:20.5,width:30,height:40};
  assert.deepEqual(cropPixels(rect,{width:100,height:100},{width:200,height:200}),
    {x:21,y:41,width:60,height:80});
});


test('comment clicks allow hand jitter but do not turn thin drags into part picks', async () => {
 const {isCommentClick}=await import('../web/area-capture.js');
 assert.equal(isCommentClick({x:20,y:20},{x:20,y:20}),true);
 assert.equal(isCommentClick({x:20,y:20},{x:23,y:24}),true);
 assert.equal(isCommentClick({x:20,y:20},{x:80,y:21}),false);
 assert.equal(isCommentClick({x:20,y:20},{x:21,y:80}),false);
});

test('keyboard commenting saves a selected part without requiring pointer capture', async () => {
 const elements=new Map();
 const element=id=>{
  if(!elements.has(id))elements.set(id,{hidden:true,value:'',textContent:'',addEventListener(){},setAttribute(){},removeAttribute(){},focus(){},showModal(){this.open=true;},close(){this.open=false;}});
  return elements.get(id);
 };
 const previous=globalThis.document;
 globalThis.document={getElementById:element,addEventListener(){}};
 try {
  let selected='frame/rail',saved;
  installAreaCapture({viewport:{},capture(){throw new Error('Capture failed');},selectedPart:()=>selected,save:async payload=>{saved=payload;}});
  element('capturearea').onclick({detail:0});
  assert.equal(element('areacomment').open,true);
  element('areatext').value='Check this joint';
  await element('areaform').onsubmit({preventDefault(){}});
  assert.equal(saved.kind,'part');assert.equal(saved.part_id,selected);assert.equal(saved.text,'Check this joint');
  selected=null;element('capturearea').onclick({detail:0});
  assert.equal(element('commentstatus').hidden,false);
  assert.match(element('commentstatus').textContent,/Select a part/);
  element('capturearea').onclick({detail:1});
  assert.equal(element('commentstatus').hidden,false);
  assert.equal(element('commentstatus').textContent,'Capture failed');
 } finally {globalThis.document=previous;}
});
