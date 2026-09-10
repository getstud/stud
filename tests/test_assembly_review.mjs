import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import * as THREE from 'three';
import {workshopInches,cutSpecification,mountingLevel,groupAssemblyCuts} from '../web/assembly-instructions.js';
import {setup} from './helpers/viewer-fixture.mjs';
for(const view of ['top','front','side'])test(`${view} drawing shows stock cut lengths, with heights from the complete design base`,()=>{
 const c=setup();vm.runInContext(`openAssemblyDrawing('Frame','${view}')`,c);
 assert.equal(c.meshes.filter(mesh=>mesh.visible).length,8);
 const labels=Array.from(c.drawingLabels,label=>label.el.textContent);
 assert.ok(labels.some(text=>text.includes('51″ cut')&&text.includes('×4')));
 assert.ok(labels.some(text=>text.includes('15″ cut')&&text.includes('×4')));
 assert.ok(!labels.includes('58″'),'assembly envelope is not a board cut length');
 if(view==='top')assert.match(c.$('drawing-context').innerHTML,/7″ \/ 31¾″/);
 else{
  assert.ok(labels.includes('7″'));
  assert.ok(Array.from(c.drawingLabels,label=>label.el.title).includes('Height from design base to bottom edge'));
  assert.ok(labels.includes('31¾″'));
 }
 assert.equal(c.dimGroup.visible,false);
 assert.equal(c.environment.enabled,false);
 vm.runInContext('endAssemblyReview()',c);
 assert.equal(c.meshes.filter(mesh=>mesh.visible).length,1);
 assert.equal(c.meshes.find(mesh=>mesh.visible).userData.assembly,'Legs');
 assert.equal(c.$('explode').checked,true);
 assert.equal(c.$('dims').getAttribute('aria-pressed'),'false');
 assert.equal(c.environment.enabled,true);
 assert.equal(c.drawingDimensions.children.length,0);
});
test('a mounting level filters geometry and quantities while preserving its base and view switches',()=>{
 const c=setup();vm.runInContext("openAssemblyDrawing('Frame','top',7);openAssemblyDrawing('Frame','front')",c);
 assert.equal(c.meshes.filter(mesh=>mesh.visible).length,4);
 const labels=Array.from(c.drawingLabels,label=>label.el.textContent);
 assert.ok(labels.some(text=>text.includes('51″ cut')&&text.includes('×2')));
 assert.ok(labels.includes('7″'));
  assert.ok(Array.from(c.drawingLabels,label=>label.el.title).includes('Height from design base to bottom edge'));
 assert.ok(!labels.includes('31¾″'));
 vm.runInContext("openAssemblyDrawing('Frame','top',31.75)",c);
 assert.equal(c.meshes.filter(mesh=>mesh.visible).length,4);
 assert.match(c.$('drawing-context').innerHTML,/31¾″/);
});
test('model base is independent of exploded display and hidden assemblies',()=>{
 const c=setup();for(const mesh of c.meshes)mesh.position.y+=100;
 vm.runInContext("openAssemblyDrawing('Frame','front',7)",c);
 assert.ok(Array.from(c.drawingLabels,label=>label.el.textContent).includes('7″'));
});
test('rotated lumber uses the recorded cut length and shaped parts are identified as blanks',()=>{
 const p={size:[1.5,3.5,9],blank_size:[1.5,3.5,10],cut_length:10,profile:{bottom:[0,0],top:[8,9]},rotation:[40,0,0]};
 assert.equal(cutSpecification(p,{section:[1.5,3.5]}).text,'10″ blank');
 assert.equal(cutSpecification({...p,size:[51,1.5,3.5],blank_size:undefined,profile:undefined,cut_length:51},{section:[1.5,3.5]}).text,'51″ cut');
 assert.equal(cutSpecification({size:[24,48,.75]}, {sheet:[48,96],sheet_thickness:.75}).text,'24″ × 48″ cut');
});
