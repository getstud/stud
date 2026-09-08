import {test} from 'node:test';
import assert from 'node:assert/strict';
import {selectionRectangle, cropPixels} from '../web/area-capture.js';

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
