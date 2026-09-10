// Immutable worker meshes and persistent object patches for the established UI.
// Native project units are explicit; only GPU/camera coordinates use inches.
export function viewerFactor(units){
  if(units==='in')return 1;
  if(units==='mm')return 1/25.4;
  throw new Error('Mesh asset must declare in or mm units');
}

export function decodeMesh(buffer,units) {
  const factor=viewerFactor(units);
  const view=new DataView(buffer);
  if(buffer.byteLength<16||new TextDecoder().decode(new Uint8Array(buffer,0,8))!=='STUDMESH')throw new Error('Invalid mesh asset header');
  const vertices=view.getUint32(8,true),triangles=view.getUint32(12,true);
  const expected=16+vertices*12+triangles*12;
  if(!vertices||!triangles||expected!==buffer.byteLength)throw new Error('Missing or corrupt mesh asset');
  const positions=new Float32Array(vertices*3),indices=new Uint32Array(triangles*3);
  for(let i=0;i<positions.length;i++){
    const value=view.getFloat32(16+i*4,true);
    if(!Number.isFinite(value))throw new Error('Mesh has a nonfinite vertex');
    positions[i]=value*factor;
  }
  for(let i=0;i<indices.length;i++){
    const value=view.getUint32(16+vertices*12+i*4,true);
    if(value>=vertices)throw new Error('Mesh triangle references a missing vertex');
    indices[i]=value;
  }
  return {positions,indices};
}

async function sha256(buffer){
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256',buffer))].map(v=>v.toString(16).padStart(2,'0')).join('');
}

export class CadScene {
  constructor({THREE,group,fetcher=fetch}){
    this.THREE=THREE;this.group=group;this.fetcher=(...args)=>fetcher(...args);
    this.objects=new Map();this.assets=new Map();this.generation=0;this.buildId=null;
  }

  invalidate(){this.generation++;}

  dispose(){
    this.disposed=true;this.invalidate();
    for(const mesh of this.objects.values()){
      this.group.remove(mesh);mesh.material.dispose();for(const child of mesh.children)child.material.dispose();
    }
    for(const asset of this.assets.values()){asset.geometry?.dispose();asset.edges?.dispose();}
    this.objects.clear();this.assets.clear();
  }

  asset(part){
    if(this.disposed)throw new Error('The model view has closed.');
    const {shape_key:key,mesh_url,mesh_sha256,units}=part.cad;
    if(!this.assets.has(key)){
      const record={sha256:mesh_sha256,units};
      record.promise=(async()=>{
        const response=await this.fetcher(mesh_url);
        if(!response.ok)throw new Error(`Mesh asset unavailable (${response.status}): ${part.id}`);
        const buffer=await response.arrayBuffer();
        if(await sha256(buffer)!==mesh_sha256)throw new Error(`Mesh asset is corrupt: ${part.id}`);
        const {positions,indices}=decodeMesh(buffer,units),T=this.THREE;
        const geometry=new T.BufferGeometry();
        geometry.setAttribute('position',new T.BufferAttribute(positions,3));
        geometry.setIndex(new T.BufferAttribute(indices,1));geometry.computeVertexNormals();
        record.geometry=geometry;record.edges=new T.EdgesGeometry(geometry);
        if(this.disposed){record.geometry.dispose();record.edges.dispose();throw new Error('The model view has closed.');}
        return record;
      })().catch(error=>{this.assets.delete(key);throw error;});
      this.assets.set(key,record);
    }
    const cached=this.assets.get(key);
    if(cached.sha256!==mesh_sha256||cached.units!==units)throw new Error(`Mesh identity has conflicting contents: ${part.id}`);
    return cached.promise;
  }

  async prepare(data){
    const generation=++this.generation;
    const assets=await Promise.all(data.parts.map(part=>this.asset(part)));
    if(generation!==this.generation)return null;
    // Asset I/O completes before mutating the visible scene. A missing mesh is
    // an explicit display error, never a silently omitted physical part.
    return ()=>{
      if(generation!==this.generation)return null;
      const T=this.THREE,ids=new Set(data.parts.map(part=>part.id)),additions=[],changed=[];
      const basis=new T.Matrix4().makeRotationX(-Math.PI/2);
      const complete=data.cad.completion.geometry==='complete';
      for(const [id,mesh] of this.objects){
        if(ids.has(id))continue;
        if(complete){
          this.group.remove(mesh);mesh.material.dispose();for(const child of mesh.children)child.material.dispose();
          this.objects.delete(id);
        }else{
          mesh.userData.previousContext=true;mesh.material.transparent=true;mesh.material.opacity=.12;mesh.material.depthWrite=false;
          for(const edge of mesh.children)edge.material.opacity=.06;
        }
      }
      for(let index=0;index<data.parts.length;index++){
        const part=data.parts[index],asset=assets[index];let mesh=this.objects.get(part.id);
        if(!mesh){
          mesh=new T.Mesh(asset.geometry,new T.MeshStandardMaterial({color:part.color||data.stocks[part.stock].color,roughness:.82,metalness:0}));
          const edge=new T.LineSegments(asset.edges,new T.LineBasicMaterial({color:'#554b3f',transparent:true,opacity:.24}));
          mesh.add(edge);this.group.add(mesh);this.objects.set(part.id,mesh);additions.push(mesh);
        }else{
          if(mesh.userData.cad?.shape_key!==part.cad.shape_key){mesh.geometry=asset.geometry;mesh.children[0].geometry=asset.edges;changed.push(mesh);}
          if(JSON.stringify(mesh.userData.cad?.placement)!==JSON.stringify(part.cad.placement))changed.push(mesh);
        }
        const matrix=part.cad.placement.map(row=>row.slice());
        for(let row=0;row<3;row++)matrix[row][3]*=viewerFactor(part.cad.units);
        const placement=new T.Matrix4().set(...matrix.flat());
        placement.premultiply(basis);placement.decompose(mesh.position,mesh.quaternion,mesh.scale);
        mesh.userData={...part,basePosition:mesh.position.clone(),color:part.color||data.stocks[part.stock].color,previousContext:false};
        mesh.material.color.set(mesh.userData.color);mesh.material.opacity=1;mesh.material.transparent=false;mesh.material.depthWrite=true;
        for(const edge of mesh.children)edge.material.opacity=.24;
        mesh.updateMatrixWorld(true);
      }
      this.buildId=data.cad.build_id;
      const used=new Set([...this.objects.values()].map(mesh=>mesh.userData.cad.shape_key));
      for(const [key,asset] of this.assets)if(!used.has(key)&&asset.geometry){asset.geometry.dispose();asset.edges.dispose();this.assets.delete(key);}
      return {meshes:data.parts.map(part=>this.objects.get(part.id)),additions,changed,
              contextCount:[...this.objects.values()].filter(mesh=>mesh.userData.previousContext).length};
    };
  }
}
