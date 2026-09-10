import * as THREE from 'three';
import {OrbitControls} from '/vendor/OrbitControls.js';
import {CadScene} from '/cad-scene.js';

// Each side retains its own immutable geometry; camera changes are shared.
export class ComparisonScene {
 constructor(root,onSelect=()=>{}){this.root=root;this.onSelect=onSelect;this.sides=[];this.frame=null;this.syncing=false;}
 async load(result){
  const allBounds=new THREE.Box3(),changes=new Map(result.objects.map(row=>[row.id,row]));
  this.root.replaceChildren();
  for(let index=0;index<2;index++){
   const section=document.createElement('section'),title=document.createElement('p'),host=document.createElement('div');
   title.textContent=`${index?'B':'A'} · ${result[index?'right_checkpoint':'left_checkpoint'].slice(0,12)}`;
   host.className='comparison-canvas';host.setAttribute('aria-label',`${index?'B':'A'} model; drag to orbit both views`);
   section.append(title,host);this.root.append(section);
   const model=result.views[index];
   if(!model){host.textContent=result.view_errors.find(error=>error.side===(index?'right':'left'))?.message||'Saved geometry is unavailable.';continue;}
   const renderer=new THREE.WebGLRenderer({antialias:true,logarithmicDepthBuffer:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));
   renderer.outputColorSpace=THREE.SRGBColorSpace;host.append(renderer.domElement);
   const scene=new THREE.Scene(),group=new THREE.Group();scene.add(group);scene.add(new THREE.HemisphereLight('#fffff0','#768371',2.6));
   const sun=new THREE.DirectionalLight('#fff4dc',3);sun.position.set(150,230,100);scene.add(sun);
   const camera=new THREE.PerspectiveCamera(40,1,.1,100000),controls=new OrbitControls(camera,renderer.domElement);
   const cad=new CadScene({THREE,group}),side={renderer,scene,camera,controls,cad,host,index};this.sides.push(side);
   controls.addEventListener('change',()=>this.sync(side));
   let down=null;
   renderer.domElement.addEventListener('pointerdown',event=>{down=[event.clientX,event.clientY];});
   renderer.domElement.addEventListener('pointerup',event=>{
    if(!down||Math.hypot(event.clientX-down[0],event.clientY-down[1])>4)return;
    const box=host.getBoundingClientRect(),ray=new THREE.Raycaster();
    ray.setFromCamera(new THREE.Vector2((event.clientX-box.left)/box.width*2-1,1-(event.clientY-box.top)/box.height*2),camera);
    const hit=ray.intersectObjects([...cad.objects.values()],false)[0];if(hit)this.select(hit.object.userData.id);
   });
   const patch=await cad.prepare(model);if(this.closed)return;patch?.();
   for(const mesh of cad.objects.values()){
    const row=changes.get(mesh.userData.id),color=row?.status==='added'?'#4b9975':row?.status==='removed'?'#bc7364':row?.changes.includes('reshaped')?'#d19b50':row?.changes.includes('moved')?'#6d9fb3':null;
    if(color)mesh.material.color.set(color);
    else if(row?.status==='unchanged'){mesh.material.transparent=true;mesh.material.opacity=.36;}
   }
   group.updateMatrixWorld(true);allBounds.union(new THREE.Box3().setFromObject(group));
  }
  if(this.closed)return;
  const center=allBounds.isEmpty()?new THREE.Vector3():allBounds.getCenter(new THREE.Vector3());
  const extent=allBounds.isEmpty()?100:Math.max(allBounds.getSize(new THREE.Vector3()).length(),1);
  for(const side of this.sides){side.camera.position.copy(center).add(new THREE.Vector3(1,.7,1).normalize().multiplyScalar(extent*1.4));side.controls.target.copy(center);side.controls.update();}
  const render=()=>{
   if(this.closed)return;
   const color=getComputedStyle(document.documentElement).getPropertyValue('--stage').trim();
   for(const side of this.sides){const width=side.host.clientWidth,height=side.host.clientHeight;if(!width||!height)continue;
    if(side.width!==width||side.height!==height){side.renderer.setSize(width,height);side.camera.aspect=width/height;side.camera.updateProjectionMatrix();side.width=width;side.height=height;}
    side.renderer.setClearColor(color);side.renderer.render(side.scene,side.camera);
   }
   this.frame=requestAnimationFrame(render);
  };render();
 }
 sync(source){
  if(this.syncing)return;this.syncing=true;
  for(const side of this.sides){if(side===source)continue;side.camera.position.copy(source.camera.position);side.camera.quaternion.copy(source.camera.quaternion);side.camera.zoom=source.camera.zoom;side.camera.updateProjectionMatrix();side.controls.target.copy(source.controls.target);side.controls.update();}
  this.syncing=false;
 }
 setCamera({position,target,zoom=1}){
  if(position.every((v,i)=>v===target[i]))throw new Error('Camera position and target must differ.');
  const side=this.sides[0];side.camera.position.set(position[0],position[2],-position[1]);side.controls.target.set(target[0],target[2],-target[1]);side.camera.zoom=zoom;side.camera.lookAt(side.controls.target);side.camera.updateProjectionMatrix();side.controls.update();this.sync(side);
 }
 select(id){this.selected=id;for(const side of this.sides)for(const mesh of side.cad.objects.values())mesh.material.emissive.set(mesh.userData.id===id?'#68400f':'#000000');this.onSelect(id);}
 dispose(){this.closed=true;cancelAnimationFrame(this.frame);for(const side of this.sides){side.controls.dispose();side.cad.dispose();side.renderer.dispose();side.renderer.forceContextLoss();}this.sides=[];}
}
