import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import * as THREE from 'three';
import {workshopInches,cutSpecification,mountingLevel,groupAssemblyCuts} from '../web/assembly-instructions.js';
const source=readFileSync(new URL('../web/app.js',import.meta.url),'utf8');
function setup(){
 const elements=new Map();
 const $=id=>{if(!elements.has(id))elements.set(id,{hidden:false,checked:false,children:[],attributes:{},getAttribute(key){return this.attributes[key];},setAttribute(key,value){this.attributes[key]=value;},replaceChildren(){this.children=[];},append(child){this.children.push(child);}});return elements.get(id);};
 const parts=[];
 for(const z of [7,31.75]){
  for(const y of [1,21.5])parts.push({id:`long-${y}-${z}`,assembly:'Frame',stock:'rails',size:[51,1.5,3.5],origin:[4.5,y,z],cut_length:51});
  for(const x of [1,57.5])parts.push({id:`end-${x}-${z}`,assembly:'Frame',stock:'rails',size:[1.5,15,3.5],origin:[x,4.5,z],cut_length:15});
 }
 parts.push({id:'leg',assembly:'Legs',stock:'legs',size:[3.5,3.5,35.25],origin:[1,1,0],cut_length:35.25});
 const meshes=parts.map(part=>{
  const mesh=new THREE.Mesh(new THREE.BoxGeometry(...part.size),new THREE.MeshStandardMaterial());
  mesh.quaternion.setFromAxisAngle(new THREE.Vector3(1,0,0),-Math.PI/2);
  mesh.position.set(part.origin[0]+part.size[0]/2,part.origin[2]+part.size[2]/2,-part.origin[1]-part.size[1]/2);
  mesh.userData={...part,basePosition:mesh.position.clone()};mesh.visible=part.assembly==='Legs';return mesh;
 });
 $('explode').checked=true;$('environmenttoggle').checked=true;$('dims').setAttribute('aria-pressed','false');
 const context=vm.createContext({THREE,$,meshes,model:{stocks:{rails:{name:'2×4',section:[1.5,3.5]},legs:{name:'4×4',section:[3.5,3.5]}}},selected:null,assemblyReview:null,drawingLabels:[],partMeasurements:new WeakMap(),
 workshopInches,cutSpecification,mountingLevel,groupAssemblyCuts,escape:String,
 visibility:new Map([['Frame',false],['Legs',true]]),expandedAssemblies:new Set(),innerWidth:1200,
 grid:{visible:true},environment:{setEnabled(value){this.enabled=value;}},drawingDimensions:new THREE.Group(),dimGroup:new THREE.Group(),labelRoot:$('labels'),
 document:{createElement:()=>({})},buildAnimation:{atRest:fn=>fn(),finish(){}},clearShow(){},clearValidationHighlights(){},clearAnnotationHover(){},select(){},renderList(){},setModelPanel(){},setView(){},
 inches:value=>`${value}″`,disposeTree:group=>group.clear()});
 const display=source.slice(source.indexOf('function applyDisplay('),source.indexOf('function select('));
 const review=source.slice(source.indexOf('function partMeasurement('),source.indexOf('function partLabel('));
 vm.runInContext(display+review,context);return context;
}
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
