import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import * as THREE from 'three';
import {CadScene,decodeMesh} from '../web/cad-scene.js';
import {ProjectEvents} from '../web/project-events.js';

function asset(){
 const bytes=new ArrayBuffer(16+36+12),view=new DataView(bytes);
 new Uint8Array(bytes,0,8).set(new TextEncoder().encode('STUDMESH'));
 view.setUint32(8,3,true);view.setUint32(12,1,true);
 [0,0,0,25.4,0,0,0,25.4,0].forEach((value,i)=>view.setFloat32(16+4*i,value,true));
 [0,1,2].forEach((value,i)=>view.setUint32(52+4*i,value,true));
 return {bytes,hash:createHash('sha256').update(new Uint8Array(bytes)).digest('hex')};
}
const meshAsset=asset();
function part(id,x=0){return {id,stock:'wood',color:'#d8b982',cad:{units:'mm',shape_key:'shared',mesh_url:'/mesh',mesh_sha256:meshAsset.hash,
 placement:[[1,0,0,x],[0,1,0,0],[0,0,1,0],[0,0,0,1]]}};}
function manifest(parts,complete=true,id='b1'){return {parts,stocks:{wood:{color:'#d8b982'}},cad:{build_id:id,completion:{geometry:complete?'complete':'partial'}}};}
const okFetch=async()=>({ok:true,arrayBuffer:async()=>meshAsset.bytes});

test('native mesh decoding preserves physical units and rejects corrupt indices',()=>{
 assert.ok(Math.abs(decodeMesh(meshAsset.bytes,'mm').positions[3]-1)<1e-6);
 const corrupted=meshAsset.bytes.slice(0);new DataView(corrupted).setUint32(52,99,true);
 assert.throws(()=>decodeMesh(corrupted,'mm'),/missing vertex/);
 assert.throws(()=>decodeMesh(meshAsset.bytes.slice(0,-1),'mm'),/corrupt/);
});

test('patches retain object identity, reuse assets, and distinguish partial prior context',async()=>{
 let transfers=0;const group=new THREE.Group(),scene=new CadScene({THREE,group,fetcher:async(...args)=>{transfers++;return okFetch(...args);}});
 const first=(await scene.prepare(manifest([part('a'),part('b')])) )();
 const selected=first.meshes[0],geometry=selected.geometry;
 const partial=(await scene.prepare(manifest([part('a',254)],false,'b2')))();
 assert.equal(partial.meshes[0],selected);assert.equal(selected.geometry,geometry);
 assert.equal(selected.position.x,10);assert.equal(partial.contextCount,1);
 assert.equal(scene.objects.get('b').material.opacity,.12);
 const restored=(await scene.prepare(manifest([part('a',254),part('b')],false,'b2')))();
 assert.equal(scene.objects.get('b').material.opacity,1);
 assert.equal(scene.objects.get('b').children[0].material.opacity,.24);
 assert.equal(restored.contextCount,0);
 const complete=(await scene.prepare(manifest([part('a',254)],true,'b2')))();
 assert.equal(complete.additions.length,0);assert.equal(complete.contextCount,0);
 assert.equal(scene.objects.has('b'),false);assert.equal(transfers,1);
});

test('missing and conflicting assets cannot partially replace a visible scene',async()=>{
 const group=new THREE.Group(),scene=new CadScene({THREE,group,fetcher:okFetch});
 (await scene.prepare(manifest([part('a')])))();const before=scene.objects.get('a');
 const conflict=part('b');conflict.cad.mesh_sha256='invalid';
 await assert.rejects(()=>scene.prepare(manifest([conflict])),/conflicting/);
 assert.equal(scene.objects.get('a'),before);
 const missing=new CadScene({THREE,group:new THREE.Group(),fetcher:async()=>({ok:false,status:404})});
 await assert.rejects(()=>missing.prepare(manifest([part('a')])),/unavailable/);
 assert.equal(missing.objects.size,0);
});

test('a late asset response cannot replace a newer candidate',async()=>{
 let release;const pending=new Promise(resolve=>release=resolve);
 const scene=new CadScene({THREE,group:new THREE.Group(),fetcher:async()=>{await pending;return okFetch();}});
 const old=scene.prepare(manifest([part('old')],false,'old'));
 const newest=scene.prepare(manifest([part('new')],true,'new'));
 release();assert.equal(await old,null);(await newest)();
 assert.deepEqual([...scene.objects.keys()],['new']);
});

test('ordered event replay is harmless and a gap requests one snapshot',()=>{
 const events=[],stream=new ProjectEvents({onEvent:event=>events.push(event),onReset:()=>{}});
 let resets=0;stream.connect=async()=>{resets++;};
 assert.equal(stream.accept({sequence:1,type:'part_batch'}),true);
 assert.equal(stream.accept({sequence:1,type:'part_batch'}),false);
 assert.equal(stream.accept({sequence:3,type:'build_ended'}),false);
 assert.equal(events.length,1);assert.equal(resets,1);
});

test('inch assets retain inch coordinates and reject unit conflicts',async()=>{
 const inch=part('inch',10);inch.cad.units='in';
 const scene=new CadScene({THREE,group:new THREE.Group(),fetcher:okFetch});
 const result=(await scene.prepare(manifest([inch])))();
 assert.equal(result.meshes[0].position.x,10);
 assert.ok(Math.abs(result.meshes[0].geometry.attributes.position.array[3]-25.4)<1e-5);
 const metric=part('metric',254);
 await assert.rejects(()=>scene.prepare(manifest([metric])),/conflicting/);
 assert.throws(()=>decodeMesh(meshAsset.bytes),/declare in or mm/);
 assert.throws(()=>decodeMesh(meshAsset.bytes,'feet'),/declare in or mm/);
});

test('metric cut labels report native millimeters from the viewer presentation',async()=>{
 const {cutSpecification}=await import('../web/assembly-instructions.js');
 const metric={size:[1.5,3.5,24],blank_size:[1.5,3.5,24],cut_length:24,cad:{units:'mm',operations:[]}};
 assert.equal(cutSpecification(metric,{section:[1.5,3.5]}).text,'609.6 mm cut');
 assert.equal(cutSpecification({...metric,cad:{units:'in',operations:[]}},{section:[1.5,3.5]}).text,'24″ cut');
});

test('comparison cache reuses geometry across N saved shapes and bounds retained assets',async()=>{
 let transfers=0;
 const scene=new CadScene({THREE,group:new THREE.Group(),retainedAssets:2,fetcher:async()=>{transfers++;return okFetch();}});
 const variant=key=>{const p=part('roof');p.cad.shape_key=key;return manifest([p]);};
 for(const key of ['gable','dormer','porch','gable','porch','dormer'])(await scene.prepare(variant(key)))();
 assert.equal(transfers,3);assert.equal(scene.assets.size,3);
 (await scene.prepare(variant('fourth')))();assert.equal(scene.assets.size,3);
 scene.dispose();assert.equal(scene.assets.size,0);
});
