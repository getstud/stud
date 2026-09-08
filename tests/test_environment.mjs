import {test} from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {createEnvironment, disposeEnvironment} from '../web/environment.js';
import {create as createTree} from '../examples/environment/assets/tree.js';
const asset = overrides => ({id:'tree', name:'Tree', source:'assets/tree.js', revision:'a', origin:[10,20,30], rotation:[0,0,0], parameters:{radius:12}, visible:true, ...overrides});
const box = () => new THREE.Mesh(new THREE.BoxGeometry(2,4,6), new THREE.MeshStandardMaterial());

test('Z-up placement, design isolation, visibility, picking and removal', async () => {
  const scene = new THREE.Scene(), construction = new THREE.Group(); scene.add(construction);
  const env = createEnvironment({THREE, scene, importer:async () => ({create:box})});
  await env.update([asset()]);
  const center = env.bounds().getCenter(new THREE.Vector3());
  assert.ok(center.distanceTo(new THREE.Vector3(10,30,-20)) < 1e-8);
  assert.equal(construction.children.length, 0);
  const ray = new THREE.Raycaster(new THREE.Vector3(10,30,100), new THREE.Vector3(0,0,-1));
  assert.equal(env.pick(ray).entry.asset.id, 'tree');
  env.setVisible('tree',false); assert.equal(env.pick(ray),null); assert.ok(env.bounds().isEmpty());
  env.setVisible('tree',true); env.setEnabled(false); assert.ok(env.bounds().isEmpty());
  env.setEnabled(true); assert.ok(!env.bounds().isEmpty());
  const mesh = env.entries.get('tree').object.children[0]; let disposed=0;
  mesh.geometry.addEventListener('dispose',()=>disposed++);
  await env.update([]); assert.equal(disposed,1); assert.equal(env.group.children.length,0);
});

test('factory parameters, asset URLs, revision reload and last good fallback', async () => {
  const urls=[]; let fail=false, calls=0;
  const env=createEnvironment({THREE,scene:new THREE.Scene(),importer:async url=>{
    urls.push(url); return {create: context => {
      calls++; assert.equal(context.parameters.radius,12);
      assert.equal(context.assetUrl('./bark.png'),url.replace('tree.js','bark.png'));
      assert.throws(()=>context.assetUrl('../../private.txt'));
      if(fail)throw new Error('bad tree'); return box();
    }};
  }});
  await env.update([asset()]); const old=env.entries.get('tree').object;
  await env.update([asset()]); assert.equal(calls,1);
  fail=true; await env.update([asset({revision:'b'})]);
  assert.equal(env.entries.get('tree').object,old); assert.equal(env.entries.get('tree').error,'bad tree');
  fail=false; await env.update([asset({revision:'c'})]);
  assert.notEqual(env.entries.get('tree').object,old); assert.equal(old.parent,null);
  assert.deepEqual(urls,['/environment/a/assets/tree.js','/environment/b/assets/tree.js','/environment/c/assets/tree.js']);
});

test('late asynchronous factories cannot resurrect removed or superseded objects', async () => {
  const resolvers=[];
  const env=createEnvironment({THREE,scene:new THREE.Scene(),importer:async()=>({create:()=>new Promise(resolve=>resolvers.push(resolve))})});
  const first=env.update([asset()]); await Promise.resolve();
  const second=env.update([asset({revision:'b'})]); await Promise.resolve();
  const newer=box(); resolvers[1](newer); await second;
  const stale=box(); let disposed=0; stale.geometry.addEventListener('dispose',()=>disposed++);
  resolvers[0](stale); await first;
  assert.equal(env.entries.get('tree').object.children[0],newer); assert.equal(disposed,1);
  const third=env.update([asset({revision:'c'})]); await Promise.resolve();
  await env.update([]); resolvers[2](box()); await third;
  assert.equal(env.group.children.length,0);
});

test('procedural tree is repeatable and has the requested lower trunk diameter', () => {
  const parameters={trunk_diameter:24,height:360,seed:42,trunk_reference_height:106};
  const a=createTree({THREE,parameters}), b=createTree({THREE,parameters});
  const wood = a.children[0].geometry.getAttribute('position');
  const reference = [];
  for (let i=0;i<wood.count;i++) {
    assert.ok(Number.isFinite(wood.getX(i)) && Number.isFinite(wood.getY(i)) && Number.isFinite(wood.getZ(i)));
    if (Math.abs(wood.getZ(i)-106)<1e-5) reference.push(Math.hypot(wood.getX(i),wood.getY(i)));
  }
  assert.equal(reference.length,72);
  assert.ok(reference.every(r=>Math.abs(r-12)<1e-5));
  assert.deepEqual(wood.array,b.children[0].geometry.getAttribute('position').array);
  assert.deepEqual(a.children[1].instanceMatrix.array,b.children[1].instanceMatrix.array);
  assert.deepEqual(a.children[1].instanceColor.array,b.children[1].instanceColor.array);
  assert.ok(new THREE.Box3().setFromObject(a).min.z >= -1e-5);
  assert.equal(a.children.length,2);
  assert.ok(a.children[1].count < 10000);
  const other=createTree({THREE,parameters:{...parameters,seed:43}});
  assert.notDeepEqual(a.children[1].instanceMatrix.array,other.children[1].instanceMatrix.array);
  assert.throws(()=>createTree({THREE,parameters:{...parameters,trunk_reference_height:200}}));
  disposeEnvironment(a); disposeEnvironment(b); disposeEnvironment(other);
  assert.throws(()=>createTree({THREE,parameters:{height:-1}}));
});


test('disposal releases shared geometry, material and texture once', () => {
  const root = new THREE.Group(), geometry = new THREE.BoxGeometry(), texture = new THREE.Texture();
  const material = new THREE.MeshStandardMaterial({map:texture});
  const instances = new THREE.InstancedMesh(geometry,material,2);
  root.add(new THREE.Mesh(geometry,material),instances);
  const released = [];
  for (const [name, resource] of Object.entries({geometry,material,texture,instances})) resource.addEventListener('dispose',()=>released.push(name));
  disposeEnvironment(root);
  assert.deepEqual(released.sort(),['geometry','instances','material','texture']);
});

test('every child branch meets the solid of its bent parent', () => {
  const tree = createTree({THREE, parameters:{seed:42}});
  const vertices = tree.children[0].geometry.getAttribute('position');
  // Wood emits three nine-vertex rings per branch, in depth-first order.
  const branchCount = 16 * 13, first = vertices.count - branchCount * 27;
  const branches = Array.from({length:branchCount}, (_, branch) =>
    Array.from({length:3}, (_, ring) => {
      const points = Array.from({length:9}, (_, side) => new THREE.Vector3().fromBufferAttribute(vertices,first+branch*27+ring*9+side));
      const center = points.reduce((sum,p)=>sum.add(p),new THREE.Vector3()).divideScalar(9);
      return {center,radius:Math.max(...points.map(p=>p.distanceTo(center)))};
    }));
  let cursor = 0;
  function check(depth, parent) {
    const child = branches[cursor++];
    if (parent) {
      const connected = [0,1].some(i => {
        const segment = new THREE.Line3(parent[i].center,parent[i+1].center);
        const t = segment.closestPointToPointParameter(child[0].center,true);
        const radius = THREE.MathUtils.lerp(parent[i].radius,parent[i+1].radius,t);
        return segment.at(t,new THREE.Vector3()).distanceTo(child[0].center) <= radius;
      });
      assert.ok(connected,`Branch ${cursor-1} must start inside its parent`);
    }
    if (depth) for(let i=0;i<3;i++)check(depth-1,child);
  }
  for(let i=0;i<16;i++)check(2,null);
  disposeEnvironment(tree);
});
