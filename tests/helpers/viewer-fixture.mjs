import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import * as THREE from 'three';
import {workshopInches,cutSpecification,mountingLevel,groupAssemblyCuts} from '../../web/assembly-instructions.js';
const source=readFileSync(new URL('../../web/app.js',import.meta.url),'utf8');
export function setup(){
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
 const context=vm.createContext({THREE,$,meshes,model:{revision:'r1',name:'Fixture',stocks:{rails:{name:'2×4',section:[1.5,3.5]},legs:{name:'4×4',section:[3.5,3.5]}}},selected:null,assemblyReview:null,drawingLabels:[],partMeasurements:new WeakMap(),
 workshopInches,cutSpecification,mountingLevel,groupAssemblyCuts,escape:String,
 hiddenParts:new Set(),visibility:new Map([['Frame',false],['Legs',true]]),expandedAssemblies:new Set(),innerWidth:1200,
 grid:{visible:true},environment:{setEnabled(value){this.enabled=value;}},drawingDimensions:new THREE.Group(),dimGroup:new THREE.Group(),labelRoot:$('labels'),
 document:{createElement:()=>({})},buildAnimation:{atRest:fn=>fn(),finish(){}},clearShow(){},clearValidationHighlights(){},clearAnnotationHover(){},select(){},renderList(){},setModelPanel(){},setView(){},
 inches:value=>`${value}″`,disposeTree:group=>group.clear()});
 const display=source.slice(source.indexOf('function applyDisplay('),source.indexOf('function select('));
 const review=source.slice(source.indexOf('function partMeasurement('),source.indexOf('function partLabel('));
 vm.runInContext(display+review+source.slice(source.indexOf('function revealAndSelectPart('),source.indexOf('let down;renderer.domElement'))+source.slice(source.indexOf('function setWarningsVisible('),source.indexOf('function showValidationFinding(')),context);return context;
}
