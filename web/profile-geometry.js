/** Cut member profile in local Y/Z, extruded along X, centered like a stock box. */
export function outlineGeometry(THREE, part) {
  const [w, d, h] = part.size;
  const points = part.outline.map(([y, z]) => new THREE.Vector2(y - d / 2, z - h / 2));
  // Use a consistent winding for outer faces and side walls.
  if (THREE.ShapeUtils.isClockWise(points)) points.reverse();
  const triangles = THREE.ShapeUtils.triangulateShape(points, []);
  const vertices = [];
  const add = (x, i) => vertices.push(x, points[i].x, points[i].y);
  for (const [a, b, c] of triangles) {
    for (const i of [c, b, a]) add(-w / 2, i);
    for (const i of [a, b, c]) add(w / 2, i);
  }
  for (let a = 0; a < points.length; a++) {
    const b = (a + 1) % points.length;
    add(-w / 2, a); add(w / 2, b); add(w / 2, a);
    add(-w / 2, a); add(-w / 2, b); add(w / 2, b);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
  geometry.computeVertexNormals();
  return geometry;
}

/** Exterior boundary of scribed sections; shared faces stay internal. */
export function layeredGeometry(THREE, part) {
  const [w,d,h]=part.size,vertices=[],eps=1e-8;
  const area=poly=>poly.reduce((sum,p,i)=>{const q=poly[(i+1)%poly.length];return sum+p[0]*q[1]-p[1]*q[0];},0)/2;
  const clean=poly=>{
    const result=poly.filter((p,i)=>!i||Math.hypot(p[0]-poly[i-1][0],p[1]-poly[i-1][1])>eps);
    if(result.length>1&&Math.hypot(result[0][0]-result.at(-1)[0],result[0][1]-result.at(-1)[1])<eps)result.pop();
    return result;
  };
  const half=(poly,a,b,sign)=>{
    const side=p=>sign*((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]));
    const result=[];
    for(let i=0;i<poly.length;i++){
      const p=poly[i],q=poly[(i+1)%poly.length],dp=side(p),dq=side(q);
      if(dp>=-eps)result.push(p);
      if((dp<-eps&&dq>=-eps)||(dp>=-eps&&dq<-eps)){
        const t=dp/(dp-dq);result.push([p[0]+t*(q[0]-p[0]),p[1]+t*(q[1]-p[1])]);
      }
    }
    return clean(result);
  };
  const subtract=(poly,boundary)=>{
    let inside=poly;const outside=[];
    for(let i=0;i<boundary.length&&inside.length>=3;i++){
      const a=boundary[i],b=boundary[(i+1)%boundary.length],piece=half(inside,a,b,-1);
      if(piece.length>=3&&Math.abs(area(piece))>eps)outside.push(piece);
      inside=half(inside,a,b,1);
    }
    return outside;
  };
  const layers=part.profile.layers.map(layer=>{
    const rings=layer.outlines.map(poly=>area(poly)<0?[...poly].reverse():poly);
    const triangles=rings.flatMap(ring=>THREE.ShapeUtils.triangulateShape(ring.map(([y,z])=>new THREE.Vector2(y,z)),[]).map(ids=>ids.map(i=>ring[i])));
    return {...layer,rings,triangles};
  });
  const add=(x,p)=>vertices.push(x-w/2,p[0]-d/2,p[1]-h/2);
  for(let index=0;index<layers.length;index++){
    const layer=layers[index],[lo,hi]=layer.x;
    for(const [x,neighbor,positive] of [[lo,layers[index-1],false],[hi,layers[index+1],true]]){
      for(const triangle of layer.triangles){
        let pieces=[triangle];
        for(const cutter of neighbor?.triangles??[])pieces=pieces.flatMap(piece=>subtract(piece,cutter));
        for(const piece of pieces){
          if(area(piece)<0)piece.reverse();
          for(let i=1;i<piece.length-1;i++)for(const p of positive?[piece[0],piece[i],piece[i+1]]:[piece[0],piece[i+1],piece[i]])add(x,p);
        }
      }
    }
    for(let ringIndex=0;ringIndex<layer.rings.length;ringIndex++){
      const ring=layer.rings[ringIndex];
      for(let i=0;i<ring.length;i++){
        const a=ring[i],b=ring[(i+1)%ring.length],delta=[b[0]-a[0],b[1]-a[1]],length2=delta[0]**2+delta[1]**2;
        const cross=p=>delta[0]*(p[1]-a[1])-delta[1]*(p[0]-a[0]);
        let intervals=[[0,1]];
        for(let j=0;j<layer.rings.length;j++)if(j!==ringIndex){
          const other=layer.rings[j];
          for(let k=0;k<other.length;k++){
            const c=other[k],e=other[(k+1)%other.length];
            if(Math.abs(cross(c))>eps||Math.abs(cross(e))>eps)continue;
            const t=p=>((p[0]-a[0])*delta[0]+(p[1]-a[1])*delta[1])/length2;
            const start=Math.min(t(c),t(e)),end=Math.max(t(c),t(e));
            intervals=intervals.flatMap(([p,q])=>end<=p+eps||start>=q-eps?[[p,q]]:[[p,Math.min(q,start)],[Math.max(p,end),q]].filter(([u,v])=>v-u>eps));
          }
        }
        for(const [start,end] of intervals){
          const p=[a[0]+start*delta[0],a[1]+start*delta[1]],q=[a[0]+end*delta[0],a[1]+end*delta[1]];
          add(lo,p);add(hi,q);add(hi,p);add(lo,p);add(lo,q);add(hi,q);
        }
      }
    }
  }
  const geometry=new THREE.BufferGeometry();
  geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));
  geometry.computeVertexNormals();return geometry;
}

/** Connected depth bands: one board with slope cuts and open edge notches. */
export function bandedGeometry(THREE, part) {
  const [w,d,h]=part.size, bands=part.profile.bands, vertices=[];
  const add=([x,y,z])=>vertices.push(x-w/2,y-d/2,z-h/2);
  const quad=(points,reverse=false)=>{
    const ids=reverse?[0,2,1,0,3,2]:[0,1,2,0,2,3];
    for(const i of ids)add(points[i]);
  };
  const side=(x,bottom,top,positive)=>{
    quad([[x,0,bottom[0]],[x,d,bottom[1]],[x,d,top[1]],[x,0,top[0]]],!positive);
  };
  for(const band of bands){
    const [a,b]=band.x;
    for(const key of ['bottom','top']){
      const [z0,z1]=band[key];
      quad([[a,0,z0],[b,0,z0],[b,d,z1],[a,d,z1]],key==='bottom');
    }
  }
  side(bands[0].x[0],bands[0].bottom,bands[0].top,false);
  const last=bands.at(-1);side(last.x[1],last.bottom,last.top,true);
  for(let i=1;i<bands.length;i++){
    const left=bands[i-1],right=bands[i],x=right.x[0];
    for(const key of ['bottom','top']){
      const a=left[key],b=right[key];
      const delta=(a[0]+a[1])-(b[0]+b[1]);
      if(Math.abs(delta)<1e-8)continue;
      const low=delta>0?b:a,high=delta>0?a:b;
      side(x,low,high,key==='top'?delta>0:delta<0);
    }
  }
  for(const j of [0,1]){
    const raw=[];
    for(const band of bands)raw.push([band.x[0],band.bottom[j]],[band.x[1],band.bottom[j]]);
    for(const band of [...bands].reverse())raw.push([band.x[1],band.top[j]],[band.x[0],band.top[j]]);
    const ring=raw.filter((p,i)=>!i||Math.hypot(p[0]-raw[i-1][0],p[1]-raw[i-1][1])>1e-8);
    const points=ring.map(([x,z])=>new THREE.Vector2(x,z));
    for(const triangle of THREE.ShapeUtils.triangulateShape(points,[])){
      for(const i of j?[...triangle].reverse():triangle)add([ring[i][0],j*d,ring[i][1]]);
    }
  }
  const geometry=new THREE.BufferGeometry();
  geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));
  geometry.computeVertexNormals();return geometry;
}
