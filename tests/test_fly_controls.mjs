import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {FlyControls} from '../web/fly-controls.js';

test('flight follows camera, normalizes diagonals, releases focus and disposes listeners', () => {
  globalThis.window = new EventTarget();
  globalThis.document = new EventTarget();
  const canvas = new EventTarget();
  canvas.getAttribute = () => null;
  canvas.removeAttribute = () => {};
  canvas.focus = () => {document.activeElement = canvas;};
  canvas.blur = () => {document.activeElement = null; canvas.dispatchEvent(new Event('blur'));};
  canvas.setPointerCapture = () => {};
  const camera = new THREE.PerspectiveCamera();
  const controls = new FlyControls(camera, canvas);
  const emit = (type, props) => canvas.dispatchEvent(Object.assign(new Event(type, {cancelable:true}), props));
  const step = () => controls.update(controls.lastTime + 50);
  assert.equal(document.activeElement, canvas, 'flight should accept movement immediately');
  emit('keydown', {code:'KeyW'}); step();
  assert.ok(Math.abs(camera.position.z + 3.6) < 1e-8);
  emit('keyup', {code:'KeyW'});
  for (const [code,axis,sign] of [['ArrowUp','z',-1],['ArrowDown','z',1],['ArrowLeft','x',-1],['ArrowRight','x',1]]) {
    camera.position.set(0,0,0);
    emit('keydown',{code}); step();
    assert.ok(Math.abs(camera.position[axis]-sign*3.6)<1e-8);
    emit('keyup',{code});
  }
  camera.position.set(0,0,0);
  emit('keydown', {code:'KeyW'});
  emit('keydown', {code:'ArrowUp'});
  emit('keydown', {code:'KeyD'}); step();
  assert.ok(Math.abs(camera.position.length() - 3.6) < 1e-8);
  emit('keydown', {code:'Escape'});
  const stopped = camera.position.clone(); step();
  assert.deepEqual(camera.position, stopped);
  canvas.focus(); camera.position.set(0,0,0); camera.rotation.y = Math.PI/2;
  emit('keydown', {code:'KeyW'}); emit('keydown', {code:'ShiftLeft'}); step();
  assert.ok(Math.abs(camera.position.x + 14.4) < 1e-8);
  canvas.blur(); canvas.focus();
  const blurred = camera.position.clone(); step(); assert.deepEqual(camera.position, blurred);
  emit('pointerdown', {button:0,pointerId:1,clientX:0,clientY:0});
  emit('pointermove', {pointerId:1,clientX:100,clientY:10000});
  const rotation = new THREE.Euler().setFromQuaternion(camera.quaternion, 'YXZ');
  assert.ok(Math.abs(rotation.x) < Math.PI/2);
  controls.dispose();
  emit('keydown', {code:'KeyW'}); step(); assert.deepEqual(camera.position, blurred);
  delete globalThis.window; delete globalThis.document;
});
