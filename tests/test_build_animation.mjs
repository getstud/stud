import test from 'node:test';
import assert from 'node:assert/strict';
import {BuildAnimation} from '../web/build-animation.js';

function mesh(opacity = 1) {
  return {position: {x: 3, y: 12, z: -7}, material: {opacity, transparent: opacity < 1, depthWrite: opacity === 1},
    children: [{material: {opacity: .24, transparent: true, depthWrite: true}}]};
}

test('parts drop and fade in order, restoring their positions and material state', () => {
  const animation = new BuildAnimation(), first = mesh(), second = mesh(.18);
  animation.start([first, second], 100);
  assert.equal(first.material.opacity, 0);
  assert.equal(first.position.y, 60);
  assert.equal(first.children[0].material.opacity, 0);
  animation.update(150);
  assert.ok(first.material.opacity > 0);
  assert.ok(first.position.y < 60 && first.position.y > 12);
  assert.equal(second.position.y, 60);
  assert.equal(second.material.opacity, 0);
  animation.update(2100);
  assert.deepEqual(first.position, {x: 3, y: 12, z: -7});
  assert.equal(second.position.y, 12);
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
  assert.equal(old.position.y, 12);
  assert.equal(next.material.opacity, 0);
  animation.finish();
  assert.equal(next.material.opacity, 1);
  assert.equal(next.position.y, 12);
});

test('reduced motion is immediate and large builds finish in bounded time', () => {
  const animation = new BuildAnimation(), part = mesh();
  animation.start([part], 0, true);
  assert.equal(part.material.opacity, 1);
  assert.equal(part.position.y, 12);
  animation.start(Array.from({length: 1000}, () => mesh()), 0);
  animation.update(12651);
  assert.equal(animation.entries.length, 0);
});

test('camera bounds during a layout resize do not cancel falling parts', async () => {
  const THREE = await import('three');
  const {readFileSync} = await import('node:fs');
  const {runInNewContext} = await import('node:vm');
  const source = readFileSync(new URL('../web/app.js', import.meta.url), 'utf8');
  const boundsSource = source.slice(source.indexOf('function bounds()'), source.indexOf('function setView('));
  const part = new THREE.Mesh(new THREE.BoxGeometry(2, 4, 2), new THREE.MeshStandardMaterial());
  part.position.y = 12;
  const animation = new BuildAnimation();
  animation.start([part], 0);
  animation.update(100);
  const fallingY = part.position.y;
  const bounds = runInNewContext(`${boundsSource}; bounds`, {
    THREE, buildAnimation: animation, meshes: [part], model: null, assemblyReview: null,
  });
  const frame = bounds();
  assert.equal(animation.entries.length, 1, 'layout measurement must preserve the animation');
  assert.equal(part.position.y, fallingY);
  assert.equal(frame.max.y, 14, 'camera must frame the final position');
  animation.update(200);
  assert.ok(part.position.y < fallingY && part.position.y > 12);
});

test('showing a newly built assembly preserves its reveal and frames resting parts', async () => {
  const THREE = await import('three');
  const {readFileSync} = await import('node:fs');
  const {runInNewContext} = await import('node:vm');
  const source = readFileSync(new URL('../web/app.js', import.meta.url), 'utf8');
  const part = new THREE.Mesh(new THREE.BoxGeometry(2, 4, 2), new THREE.MeshStandardMaterial());
  part.position.y = 12;
  part.userData = {id: 'beam', assembly: 'Frame', basePosition: part.position.clone()};
  const animation = new BuildAnimation();
  animation.start([part], 0);
  animation.update(100);
  const fallingY = part.position.y;
  const elements = new Map();
  const $ = id => {
    if (!elements.has(id)) elements.set(id, {hidden: true, checked: false, open: false, getAttribute: () => "false", querySelectorAll: () => [], close() {}});
    return elements.get(id);
  };
  let framed;
  const displayShow = runInNewContext([
    source.slice(source.indexOf('function bounds()'), source.indexOf('let focusDistance')),
    source.slice(source.indexOf('function displayShow('), source.indexOf('function disposeTree(')),
    source.slice(source.indexOf('function applyDisplay('), source.indexOf('function select(')),
    'displayShow',
  ].join('\n'), {THREE, $, buildAnimation: animation, performance: {now: () => 100},
    meshes: [part], model: {name: 'Test', dimensions: []}, revision: 'r2', currentView: 'perspective',
    visibility: new Map(), selected: null, dimGroup: {}, labelRoot: {}, showFrame: null, assemblyReview: null,
    endAssemblyReview() {}, drawingDimensions: {},
    showWorkspace() {}, clearShow() {}, clearValidationHighlights() {}, select() {}, renderList() {},
    setView: (view, frame) => {framed = frame;}, modelRegion: () => ({}),
    showGroup: new THREE.Group(), viewport: {scrollIntoView() {}}, renderer: {render() {}}, scene: {}, camera: {},
  });
  displayShow({part_ids: ['beam']});
  assert.equal(animation.entries.length, 1, 'show must not finish the new assembly before its first frame');
  assert.equal(part.position.y, fallingY);
  assert.equal(framed.max.y, 14, 'target framing uses the resting geometry');
  animation.update(200);
  assert.ok(part.position.y < fallingY && part.position.y > 12);
});

test('display rebasing keeps stagger timing and restores the new material settings', () => {
  const animation = new BuildAnimation(), first = mesh(.18), second = mesh();
  animation.start([first, second], 0);
  animation.rebase(() => {
    first.position.y = 20;
    Object.assign(first.material, {opacity: 1, transparent: false, depthWrite: true});
  }, 100);
  assert.ok(first.position.y > 20 && first.position.y < 68);
  assert.equal(second.material.opacity, 0);
  animation.update(150);
  assert.equal(second.material.opacity, 0);
  animation.finish();
  assert.equal(first.position.y, 20);
  assert.deepEqual(first.material, {opacity: 1, transparent: false, depthWrite: true});
});
