import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import { outlineGeometry, bandedGeometry, layeredGeometry } from '../web/profile-geometry.js';

test('renderer cut profile preserves a notch and the validator volume', () => {
  const part = { size: [1.5, 40, 7.25], outline: [[0,0],[10,0],[10,2],[14,2],[14,0],[40,0],[40,7.25],[0,7.25]] };
  for (const outline of [part.outline, [...part.outline].reverse()]) {
    const geometry = outlineGeometry(THREE, { ...part, outline });
    const positions = geometry.getAttribute('position');
    let volume = 0;
    const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
    for (let i = 0; i < positions.count; i += 3) {
      a.fromBufferAttribute(positions, i); b.fromBufferAttribute(positions, i+1); c.fromBufferAttribute(positions, i+2);
      volume += a.dot(b.cross(c))/6;
    }
    assert.ok(Math.abs(volume - 1.5*(40*7.25-8)) < 1e-5);
    geometry.computeBoundingBox();
    assert.deepEqual(geometry.boundingBox.getSize(new THREE.Vector3()).toArray(),part.size);
    geometry.dispose();
  }
});


test('depth bands render the retained volume through both notches', () => {
  for (const mirror of [false,true]) {
    const bands=[{x:[0,1.5],bottom:[0,0],top:[4,5]}, {x:[1.5,3],bottom:[3.5,3.5],top:[10,11]}, {x:[3,3.5],bottom:[0,0],top:[10,11]}];
    if(mirror) for(const band of bands) {band.top.reverse();band.bottom.reverse();}
    const geometry=bandedGeometry(THREE,{size:[3.5,1.5,11],profile:{bands}});
    const positions=geometry.getAttribute('position');
    const a=new THREE.Vector3(),b=new THREE.Vector3(),c=new THREE.Vector3();
    let volume=0;
    for(let i=0;i<positions.count;i+=3){
      a.fromBufferAttribute(positions,i);b.fromBufferAttribute(positions,i+1);c.fromBufferAttribute(positions,i+2);
      volume+=a.dot(b.cross(c))/6;
    }
    assert.ok(Math.abs(volume-33.75)<1e-5);
    geometry.dispose();
  }
});


test('scribed trim renders only exposed layer caps and preserves volume', () => {
  const outer=[[0,0],[3.5,0],[3.5,4],[1.25,4],[1.25,8],[3.5,8],[3.5,12],[0,12]];
  const lower=[[0,0],[3.5,0],[3.5,4],[0,4]],upper=[[1.25,8],[3.5,8],[3.5,12],[1.25,12]];
  for(const reverse of [false,true]) {
    const ring=poly=>reverse?[...poly].reverse():poly;
    const part={size:[.75,3.5,12],profile:{layers:[{x:[0,.5],outlines:[ring(outer)]},{x:[.5,.75],outlines:[ring(lower),ring(upper)]}]}};
    const geometry=layeredGeometry(THREE,part),positions=geometry.getAttribute('position');
    const a=new THREE.Vector3(),b=new THREE.Vector3(),c=new THREE.Vector3();
    let volume=0,capArea=0;
    for(let i=0;i<positions.count;i+=3){
      a.fromBufferAttribute(positions,i);b.fromBufferAttribute(positions,i+1);c.fromBufferAttribute(positions,i+2);
      volume+=a.dot(b.clone().cross(c))/6;
      if([a,b,c].every(p=>Math.abs(p.x-.125)<1e-6))capArea+=b.clone().sub(a).cross(c.clone().sub(a)).length()/2;
    }
    assert.ok(Math.abs(volume-22.25)<1e-5);
    assert.ok(Math.abs(capArea-10)<1e-5,`expected only 10 square inches exposed at layer seam, got ${capArea}`);
    geometry.dispose();
  }
});

test('shared polygon edges inside one layer are omitted', () => {
  const geometry=layeredGeometry(THREE,{size:[1,2,2],profile:{layers:[{x:[0,1],outlines:[[[0,0],[1,0],[1,2],[0,2]],[[1,0],[2,0],[2,2],[1,2]]]}]}});
  const positions=geometry.getAttribute('position');
  for(let i=0;i<positions.count;i+=3)assert.ok(![i,i+1,i+2].every(j=>Math.abs(positions.getY(j))<1e-8));
  geometry.dispose();
});
