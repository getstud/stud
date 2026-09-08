import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {preserveCamera} from '../web/camera-transition.js';
const near = (a,b) => assert.ok(Math.abs(a-b)<1e-7, `${a} != ${b}`);
test('orbit and flight preserve position, rotation and zoom, even far from the model', () => {
 const old=new THREE.PerspectiveCamera(38,1,.1,10000);
 old.position.set(10000,32,-150); old.rotation.set(.2,.8,0,'YXZ'); old.zoom=2;
 const next=new THREE.PerspectiveCamera(38,1,.1,10000);
 const state=preserveCamera(old,next,'firstperson',null,90);
 near(next.position.distanceTo(old.position),0);
 near(next.quaternion.angleTo(old.quaternion),0); near(next.zoom,2);
 near(state.focus.distanceTo(old.position),90);
});
test('orthographic transitions preserve panned focus and apparent scale', () => {
 const old=new THREE.PerspectiveCamera(38,1,.1,10000), focus=new THREE.Vector3(52,78,-94);
 old.position.copy(focus).add(new THREE.Vector3(200,100,300));old.lookAt(focus);
 const top=new THREE.OrthographicCamera(-300,300,300,-300,.1,10000);top.up.set(0,0,-1);
 const state=preserveCamera(old,top,'top',focus,100);
 near(state.focus.distanceTo(focus),0);
 near(top.position.x,focus.x);near(top.position.z,focus.z);
 const height=2*old.position.distanceTo(focus)*Math.tan(THREE.MathUtils.degToRad(38)/2);
 near((top.top-top.bottom)/top.zoom,height);
 const back=new THREE.PerspectiveCamera(38,1,.1,10000);
 preserveCamera(top,back,'perspective',focus,state.distance);
 near(back.position.distanceTo(focus),old.position.distanceTo(focus));
 near(back.getWorldDirection(new THREE.Vector3()).distanceTo(top.getWorldDirection(new THREE.Vector3())),0);
});
