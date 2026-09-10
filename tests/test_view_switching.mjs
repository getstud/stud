import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import * as THREE from 'three';
import {preserveCamera} from '../web/camera-transition.js';
const source=readFileSync(new URL('../web/app.js',import.meta.url),'utf8');
const setViewSource=source.slice(source.indexOf('function setView('),source.indexOf('const showGroup'));
for(const view of ['perspective','top','front','side']) test(`returning from flight to ${view} frames the design`,()=>{
 const frame=new THREE.Box3(new THREE.Vector3(0,0,0),new THREE.Vector3(60,36,24));
 const camera=new THREE.PerspectiveCamera(38,1,.1,10000);
 camera.position.set(3000,2000,4000);camera.rotation.set(.4,1,0);
 class Orbit {constructor(){this.target=new THREE.Vector3();}update(){}dispose(){}}
 const context=vm.createContext({model:null,THREE,preserveCamera,camera,currentView:'firstperson',focusDistance:100,assemblyReview:null,buildCamera:{cancel(){},stop(){}},
 controls:{dispose(){}},viewport:{clientWidth:800,clientHeight:700},renderer:{domElement:{}},
 OrbitControls:Orbit,FlyControls:class {},document:{querySelectorAll:()=>[]},$:()=>({}),bounds:()=>frame});
 vm.runInContext(setViewSource+`;setView('${view}',bounds(),true);`,context);
 assert.ok(context.controls.target.distanceTo(frame.getCenter(new THREE.Vector3()))<1e-8,'preset must focus the model after flying away');
 assert.ok(context.camera.position.distanceTo(frame.getCenter(new THREE.Vector3()))<500,'preset must return to a useful model distance');
});
