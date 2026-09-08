import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {BuildCamera, stopOnCameraInput} from '../web/build-camera.js';

function fixture() {
  const camera = new THREE.PerspectiveCamera(38, 1.5, .1, 10000);
  camera.position.set(50, 40, 70);
  const controls = {target: new THREE.Vector3()};
  const box = new THREE.Box3(new THREE.Vector3(0, 0, 0), new THREE.Vector3(100, 60, 40));
  return {camera, controls, box, follow: new BuildCamera()};
}

test('build tracking eases to new bounds without jumping and fits the final model', () => {
  const {camera, controls, box, follow} = fixture();
  const initial = camera.position.clone();
  follow.follow(box, camera, controls, 0);
  assert.deepEqual(camera.position, initial);
  follow.update(camera, controls, 100);
  assert.ok(controls.target.x > 0 && controls.target.x < 50);
  assert.ok(camera.position.distanceTo(initial) > 0);
  for (let now = 200; now <= 15000; now += 100) follow.update(camera, controls, now);
  assert.deepEqual(controls.target, box.getCenter(new THREE.Vector3()));
  assert.equal(follow.destination, null);
  assert.ok(camera.position.distanceTo(controls.target) > box.getSize(new THREE.Vector3()).length() / 2);
});

test('user takeover stops immediately and persists across later revisions', () => {
  const {camera, controls, box, follow} = fixture();
  follow.follow(box, camera, controls, 0);
  follow.update(camera, controls, 100);
  follow.stop();
  const position = camera.position.clone(), target = controls.target.clone();
  follow.follow(box, camera, controls, 200);
  follow.update(camera, controls, 300);
  assert.deepEqual(camera.position, position);
  assert.deepEqual(controls.target, target);
});

test('reduced motion and fly controls do not start automatic motion', () => {
  const {camera, controls, box, follow} = fixture();
  follow.follow(box, camera, controls, 0, true);
  assert.equal(follow.destination, null);
  follow.follow(box, camera, {}, 0);
  assert.equal(follow.destination, null);
});

test('successive builds retarget smoothly from the current camera', () => {
  const {camera, controls, box, follow} = fixture();
  follow.follow(box, camera, controls, 0);
  follow.update(camera, controls, 100);
  const position = camera.position.clone();
  box.max.x = 200;
  follow.follow(box, camera, controls, 100);
  assert.deepEqual(camera.position, position);
  assert.equal(follow.destination.center.x, 100);
});

test('selection clicks preserve tracking; dragging and wheel zoom take over', () => {
  const canvas = new EventTarget(), follow = new BuildCamera();
  stopOnCameraInput(canvas, follow);
  const emit = (type, x = 10, y = 10) => {
    const event = new Event(type);
    Object.assign(event, {pointerId: 1, clientX: x, clientY: y});
    canvas.dispatchEvent(event);
  };
  emit('pointerdown'); emit('pointerup');
  assert.equal(follow.enabled, true);
  emit('pointermove', 20);
  assert.equal(follow.enabled, true, 'hovering after selection is not camera movement');
  emit('pointerdown'); emit('pointermove', 12);
  assert.equal(follow.enabled, true);
  emit('pointermove', 20);
  assert.equal(follow.enabled, false);
  const zoom = new BuildCamera();
  stopOnCameraInput(canvas, zoom);
  emit('wheel');
  assert.equal(zoom.enabled, false);
});
