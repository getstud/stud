import test from 'node:test';
import assert from 'node:assert/strict';
import {BuildAnimation} from '../web/build-animation.js';

function mesh(opacity = 1) {
  return {material: {opacity, transparent: opacity < 1, depthWrite: opacity === 1},
    children: [{material: {opacity: .24, transparent: true, depthWrite: true}}]};
}

test('parts reveal in order, including edges, and restore material state', () => {
  const animation = new BuildAnimation(), first = mesh(), second = mesh(.18);
  animation.start([first, second], 100);
  assert.equal(first.material.opacity, 0);
  assert.equal(first.children[0].material.opacity, 0);
  animation.update(150);
  assert.ok(first.material.opacity > 0);
  assert.equal(second.material.opacity, 0);
  animation.update(1000);
  assert.deepEqual(first.material, {opacity: 1, transparent: false, depthWrite: true});
  assert.deepEqual(second.material, {opacity: .18, transparent: true, depthWrite: false});
  assert.equal(first.children[0].material.opacity, .24);
  assert.equal(animation.entries.length, 0);
});

test('new revisions and user actions finish an interrupted reveal', () => {
  const animation = new BuildAnimation(), old = mesh(), next = mesh();
  animation.start([old], 0);
  animation.start([next], 10);
  assert.equal(old.material.opacity, 1);
  assert.equal(next.material.opacity, 0);
  animation.finish();
  assert.equal(next.material.opacity, 1);
});

test('reduced motion is immediate and large builds finish in bounded time', () => {
  const animation = new BuildAnimation(), part = mesh();
  animation.start([part], 0, true);
  assert.equal(part.material.opacity, 1);
  animation.start(Array.from({length: 1000}, () => mesh()), 0);
  animation.update(2151);
  assert.equal(animation.entries.length, 0);
});
