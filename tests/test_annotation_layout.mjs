import test from 'node:test';
import assert from 'node:assert/strict';
import {placeAnnotation,editorPosition} from '../web/annotation-layout.js';
test('coincident markers remain separated and inside a narrow viewport',()=>{
 const positions=[];
 for(let i=0;i<12;i++)assert.ok(placeAnnotation(3,5,320,480,positions));
 for(const p of positions){assert.ok(p.x>=20&&p.x<=300&&p.y>=20&&p.y<=460);for(const q of positions)if(p!==q)assert.ok(Math.hypot(p.x-q.x,p.y-q.y)>=32);}
});
test('editor stays inside viewport near the bottom right marker',()=>{
 assert.deepEqual(editorPosition({left:310,bottom:470},280,200,320,480),{left:24,top:264});
});
