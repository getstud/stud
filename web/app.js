import {workshopInches,cutSpecification,mountingLevel,groupAssemblyCuts} from '/assembly-instructions.js';
import {placeAnnotation,editorPosition} from '/annotation-layout.js';
import * as THREE from 'three';
import {outlineGeometry,bandedGeometry,layeredGeometry} from '/profile-geometry.js';
import {createEnvironment} from '/environment.js';
import {OrbitControls} from '/vendor/OrbitControls.js';
import {createShowTool, registerShowTool} from '/show.js';
import {installAreaCapture, snapshotViewer} from '/area-capture.js';
import {preserveCamera} from '/camera-transition.js';
import {FlyControls} from '/fly-controls.js';
import {BuildAnimation} from '/build-animation.js';
import {BuildCamera, stopOnCameraInput} from '/build-camera.js';
const buildCamera=new BuildCamera();
const buildAnimation=new BuildAnimation();
const reducedMotion=matchMedia('(prefers-reduced-motion: reduce)');
const $=id=>document.getElementById(id);
const viewport=$('viewport'), labelRoot=$('labels');
let warningAnnotations=[],commentMarkers=[],occupiedAnnotations=[];
// Thin roof layers need depth precision even when the exploded view is zoomed out.
const renderer=new THREE.WebGLRenderer({antialias:true,alpha:false,logarithmicDepthBuffer:true});
stopOnCameraInput(renderer.domElement,buildCamera);
renderer.setPixelRatio(Math.min(devicePixelRatio,2));
renderer.outputColorSpace=THREE.SRGBColorSpace;viewport.prepend(renderer.domElement);
const scene=new THREE.Scene();scene.add(new THREE.HemisphereLight('#fffff0','#768371',2.6));
const sun=new THREE.DirectionalLight('#fff4dc',3);sun.position.set(150,230,100);scene.add(sun);
const group=new THREE.Group();scene.add(group);
const grid=new THREE.GridHelper(320,20,'#c6cebf','#dce0d5');grid.position.set(72,-.5,48);scene.add(grid);
function applyViewerTheme() {
 const colors=getComputedStyle(document.documentElement);
 renderer.setClearColor(colors.getPropertyValue('--stage').trim());
 // GridHelper stores its two colors per vertex, so update the existing buffer.
 const positions=grid.geometry.attributes.position, colorsAttribute=grid.geometry.attributes.color;
 const major=new THREE.Color(colors.getPropertyValue('--grid-major').trim());
 const minor=new THREE.Color(colors.getPropertyValue('--grid-minor').trim());
 for(let i=0;i<positions.count;i++) {
  const color=(positions.getX(i)===0 || positions.getZ(i)===0)?major:minor;
  colorsAttribute.setXYZ(i,color.r,color.g,color.b);
 }
 colorsAttribute.needsUpdate=true;
}
applyViewerTheme();
window.addEventListener('themechange',applyViewerTheme);
let camera,controls,model,revision,meshes=[],labels=[],dimGroup=new THREE.Group(),selected=null,currentView='perspective';scene.add(dimGroup);
let selectedEnvironment = null;
let assemblyReview=null,drawingLabels=[];
const partMeasurements=new WeakMap();
const drawingDimensions=new THREE.Group();scene.add(drawingDimensions);
const environment = createEnvironment({THREE, scene, onChange: renderEnvironment});
const visibility=new Map();
function renderEnvironment() {
 if (!model) return;
 $('environmentsection').hidden = environment.entries.size === 0;
 $('fitscene').hidden = environment.entries.size === 0;
 $('environmentlist').replaceChildren();
 for (const [id, entry] of environment.entries) {
  const row = document.createElement('div');
  row.className = 'environmentitem';
  const label = document.createElement('label'), checkbox = document.createElement('input');
  checkbox.type = 'checkbox'; checkbox.checked = environment.isVisible(entry);
  checkbox.disabled = !$('environmenttoggle').checked;
  checkbox.onchange = () => environment.setVisible(id, checkbox.checked);
  label.append(checkbox, document.createTextNode(entry.asset.name));
  const inspect = document.createElement('button'); inspect.textContent = 'Inspect';
  inspect.onclick = () => inspectEnvironment(id);
  row.append(label, inspect);
  if (entry.loading || entry.error) {
   const status = document.createElement('small'); status.setAttribute('role', 'status');
   status.textContent = entry.loading ? 'Loading…' : `${entry.object ? 'Keeping last good appearance. ' : ''}${entry.error}`;
   row.append(status);
  }
  $('environmentlist').append(row);
 }
 if (selectedEnvironment) {
  const entry = environment.entries.get(selectedEnvironment);
  if (!entry || !environment.isVisible(entry)) select(null);
  else inspectEnvironment(selectedEnvironment);
 }
}
function inspectEnvironment(id) {
 const entry = environment.entries.get(id); if (!entry) return;
 select(null); selectedEnvironment = id;
 $('inspectorpanel').hidden = false;
 $('inspectortitle').textContent = 'ENVIRONMENT INSPECTOR';
 const asset = entry.asset;
 $('inspector').innerHTML = `<h2>${escape(asset.name)}</h2><span class="badge">ENVIRONMENT</span><p>Visual context. Excluded from materials and construction checks.</p><dl><dt>Origin (in.)</dt><dd>${asset.origin.map(inches).join(', ')}</dd><dt>Rotation (deg.)</dt><dd>${asset.rotation.join(', ')}</dd></dl><pre>${escape(JSON.stringify(asset.parameters, null, 2))}</pre>`;
}
$('environmenttoggle').onchange = () => {endAssemblyReview();environment.setEnabled($('environmenttoggle').checked);};
$('fitscene').onclick = () => {buildCamera.stop();endAssemblyReview();clearShow();showFrame = bounds().union(environment.bounds());setView(currentView, showFrame);};
const validationGroup=new THREE.Group();scene.add(validationGroup);
let validationReport=null,validationSignature='',validationHighlights=new Set();
function vec(v){return new THREE.Vector3(v[0],v[2],-v[1]);}
function escape(s){return String(s).replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));}
function inches(v){return `${Number(v.toFixed(3))}″`;}
function feet(v){let f=Math.floor(v/12),i=Number((v-f*12).toFixed(3));return f?`${f}′ ${i}″`:`${i}″`;}
function safeLink(url){try{const u=new URL(url);return u.protocol==='https:'?escape(u.href):'';}catch{return '';}}
function bounds(){return buildAnimation.atRest(()=>{const box=new THREE.Box3();for(const m of meshes)if(m.visible)box.expandByObject(m);if(!assemblyReview&&model&&($('dims').getAttribute('aria-pressed')==='true')&&!$('explode').checked)for(const d of model.dimensions){box.expandByPoint(vec(d.start));box.expandByPoint(vec(d.end));}return box.isEmpty()?new THREE.Box3(new THREE.Vector3(0,0,-96),new THREE.Vector3(144,160,0)):box;});}
let focusDistance = 100;
function setView(name=currentView, frame=bounds(), preserve=false){
 buildCamera.cancel();
 if(name!=='perspective')buildCamera.stop();
 if(assemblyReview&&(name==='perspective'||name==='firstperson')){endAssemblyReview(false);frame=bounds();preserve=false;}
 const leavingFlight=currentView==='firstperson' && name!=='firstperson';
 const previous=camera,previousTarget=controls?.target?.clone();
 currentView=name;const b=frame,center=b.getCenter(new THREE.Vector3()),size=b.getSize(new THREE.Vector3());
 // Report pages hide the canvas; keep the camera valid until it is visible again.
 const aspect=viewport.clientWidth && viewport.clientHeight ? viewport.clientWidth/viewport.clientHeight : 1;controls?.dispose();
 const extent=Math.max(size.x,size.y,size.z,20),radius=size.length()/2;
 if(name==='perspective'||name==='firstperson'){
  camera=new THREE.PerspectiveCamera(38,aspect,.1,10000);
  const limiting=Math.min(camera.fov*Math.PI/360,Math.atan(Math.tan(camera.fov*Math.PI/360)*aspect));
  camera.position.copy(center).add(new THREE.Vector3(1,.75,1.3).normalize().multiplyScalar(radius/Math.sin(limiting)*1.15));
 }else{
  const width=name==='side'?size.z:size.x,height=name==='top'?size.z:size.y;
  const inset=assemblyReview&&innerWidth>=1000&&!$('modelpanel').hidden?340:0;
  const drawingAspect=inset?(viewport.clientWidth-inset)/viewport.clientHeight:aspect;
  const half=Math.max(height/2,width/(2*drawingAspect),10)*1.22;
  camera=new THREE.OrthographicCamera(-half*aspect,half*aspect,half,-half,.1,10000);
  if(inset)camera.setViewOffset(viewport.clientWidth,viewport.clientHeight,-inset/2,0,viewport.clientWidth,viewport.clientHeight);
  if(name==='top'){camera.up.set(0,0,-1);camera.position.copy(center).add(new THREE.Vector3(0,extent*4,0));}
  if(name==='front')camera.position.copy(center).add(new THREE.Vector3(0,0,extent*4));
  if(name==='side')camera.position.copy(center).add(new THREE.Vector3(extent*4,0,0));
 }
 camera.lookAt(center);
 let target=center;
 // Flight has no model target; return to the framed preset instead of carrying its arbitrary focus.
 if(preserve && previous && !leavingFlight){const state=preserveCamera(previous,camera,name,previousTarget,focusDistance);target=state.focus;focusDistance=state.distance;}
 else focusDistance=camera.position.distanceTo(center);
 if(name==='firstperson')controls=new FlyControls(camera,renderer.domElement);
 else {controls=new OrbitControls(camera,renderer.domElement);controls.target.copy(target);controls.enableDamping=true;controls.enableRotate=name==='perspective';controls.minDistance=.01;controls.maxDistance=Infinity;controls.update();}
 document.querySelectorAll('[data-mode]').forEach(b=>{const active=b.dataset.mode===name;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});
 $('navigationhint').textContent=name==='firstperson'?'WASD / arrows fly · Drag to look · Q/E down/up · Shift faster · Esc release':name==='perspective'?'Drag to orbit · Click a part to inspect':'Drag to pan · Scroll to zoom · Click a part to inspect';
 $('viewlabel').textContent=`${name==='firstperson'?'FLY':name==='perspective'?'PERSPECTIVE':name.toUpperCase()+' · ORTHOGRAPHIC'} · INCHES`;
}
const showGroup = new THREE.Group();scene.add(showGroup);
let showFrame = null;
function clearShow(){disposeTree(showGroup);showFrame=null;}
function modelRegion(box){
 return {min:[box.min.x,-box.max.z,box.min.y],max:[box.max.x,-box.min.z,box.max.y]};
}
function displayShow(input){
 if(!$('areaoverlay').hidden || $('areacomment').open || $('areaimageview').open)throw new Error('Finish or close the area screenshot before showing another view.');
 showWorkspace();endAssemblyReview();
 const targets=(input.part_ids||[]).map(id=>meshes.find(m=>m.userData.id===id));
 clearShow();clearValidationHighlights();
 visibility.clear();$('assemblies').querySelectorAll('input').forEach(i=>i.checked=true);
 $('explode').checked=false;$('search').value='';buildAnimation.rebase(()=>applyDisplay(),performance.now());
 select(targets.length===1?targets[0]:null);
 const frame=new THREE.Box3();
 if(input.region){
  frame.setFromPoints([vec(input.region.min),vec(input.region.max)]);
 }else if(targets.length){
  buildAnimation.atRest(()=>{for(const mesh of targets)frame.expandByObject(mesh);});
 }else frame.copy(bounds());
 if(targets.length||input.region){
  const outline=new THREE.Box3Helper(frame.clone(),0xb05e22);
  outline.material.depthTest=false;outline.material.transparent=true;outline.material.opacity=.85;
  outline.renderOrder=10;showGroup.add(outline);
 }
 showFrame=frame.clone();setView(input.view||'perspective',showFrame);
 viewport.scrollIntoView({block:'center',behavior:'instant'});
 renderer.render(scene,camera);
 return {model_revision:revision,project_name:model.name,view:currentView,
  part_ids:targets.map(m=>m.userData.id),region:modelRegion(frame),units:'in',
  visible_part_count:meshes.filter(m=>m.visible).length};
}
function disposeTree(root){root.traverse(o=>{o.geometry?.dispose();if(o.material){for(const m of Array.isArray(o.material)?o.material:[o.material])m.dispose();}});root.clear();}
// Build a notched extrusion by subtracting each horizontal wall seat from
// the pitched Y/Z section. Keep the stock box dimensions for purchasing.
function seatedGeometry(p){
 const [w,d,h]=p.size,t=p.rotation[0]*Math.PI/180,c=Math.cos(t),sn=Math.sin(t);
 const cy=p.origin[1]+d/2,cz=p.origin[2]+h/2;
 const world=(y,z)=>[cy+y*c-z*sn,cz+y*sn+z*c];
 let polygons=[[world(-d/2,-h/2),world(d/2,-h/2),world(d/2,h/2),world(-d/2,h/2)]];
 function clip(poly,axis,limit,greater){
  const result=[];if(!poly.length)return result;
  for(let i=0;i<poly.length;i++){
   const a=poly[i],b=poly[(i+1)%poly.length],fa=(a[axis]-limit)*(greater?1:-1),fb=(b[axis]-limit)*(greater?1:-1);
   if(fa>=-1e-8)result.push(a);
   if((fa>1e-8&&fb< -1e-8)||(fa< -1e-8&&fb>1e-8)){
    const u=fa/(fa-fb);result.push(a.map((v,j)=>v+(b[j]-v)*u));
   }
  }return result;
 }
 for(const seat of p.seats){
  const [a,b]=seat.y,next=[];
  for(const poly of polygons){
   next.push(clip(poly,0,a,false),clip(clip(clip(poly,0,a,true),0,b,false),1,seat.z,true),clip(poly,0,b,true));
  }
  polygons=next.filter(poly=>poly.length>=3);
 }
 const vertices=[];
 for(const poly of polygons){
  const points=poly.map(([y,z])=>new THREE.Vector2((y-cy)*c+(z-cz)*sn,-(y-cy)*sn+(z-cz)*c));
  const tris=THREE.ShapeUtils.triangulateShape(points,[]);
  const add=(x,i)=>vertices.push(x,points[i].x,points[i].y);
  for(const [a,b,c] of tris){for(const i of [c,b,a])add(-w/2,i);for(const i of [a,b,c])add(w/2,i);}
  for(let a=0;a<points.length;a++){const b=(a+1)%points.length;
   add(-w/2,a);add(-w/2,b);add(w/2,b);add(-w/2,a);add(w/2,b);add(w/2,a);
  }
 }
 const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));geometry.computeVertexNormals();return geometry;
}
// A stepped profile keeps each notched stud one solid and one takeoff item.
// notch.side selects the local X face occupied by the end rafter.
function notchedProfileGeometry(p){
 const [w,d,h]=p.size,{bottom,top,notch}=p.profile;
 const split=notch.side==='min'?notch.depth:w-notch.depth;
 const rings=[0,1].map(j=>{
  const b=bottom[j],t=top[j],seat=notch.top[j];
  const outline=notch.side==='min'
   ?[[0,b],[w,b],[w,t],[split,t],[split,seat],[0,seat]]
   :[[0,b],[w,b],[w,seat],[split,seat],[split,t],[0,t]];
  return outline.map(([x,z])=>[x,j*d,z]);
 });
 const vertices=[];
 const add=(point)=>vertices.push(point[0]-w/2,point[1]-d/2,point[2]-h/2);
 for(let j=0;j<2;j++){
  const ring=rings[j];
  const triangles=THREE.ShapeUtils.triangulateShape(ring.map(([x,,z])=>new THREE.Vector2(x,z)),[]);
  for(const triangle of triangles)for(const i of j?triangle.slice().reverse():triangle)add(ring[i]);
 }
 for(let i=0;i<6;i++){
  const next=(i+1)%6;
  const quad=[rings[0][i],rings[1][i],rings[1][next],rings[0][next]];
  for(const index of [0,1,2,0,2,3])add(quad[index]);
 }
 const geometry=new THREE.BufferGeometry();
 geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));
 geometry.computeVertexNormals();return geometry;
}
function partGeometry(p){
 if(p.profile?.layers)return layeredGeometry(THREE,p);
 if(p.profile?.bands)return bandedGeometry(THREE,p);
 if(p.outline)return outlineGeometry(THREE,p);
 if(p.profile?.notch)return notchedProfileGeometry(p);
 if(p.seats?.length)return seatedGeometry(p);
 if(!p.profile)return new THREE.BoxGeometry(...p.size);
 const [w,d,h]=p.size,[bf,bb]=p.profile.bottom,[tf,tb]=p.profile.top;
 const points=[[0,0,bf],[w,0,bf],[w,d,bb],[0,d,bb],[0,0,tf],[w,0,tf],[w,d,tb],[0,d,tb]];
 const faces=[[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]];
 const vertices=[];for(const [a,b,c,d] of faces)for(const i of [a,b,c,a,c,d])vertices.push(...points[i].map((v,j)=>v-p.size[j]/2));
 const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));geometry.computeVertexNormals();return geometry;
}
function install(data){
 const isLiveUpdate=Boolean(model);
 const previousIds=new Set(meshes.map(m=>m.userData.id));
 buildAnimation.finish();
 clearShow();
 clearValidationHighlights();
 const oldSelected=selected?.userData.id;model=data;revision=data.revision;disposeTree(group);disposeTree(dimGroup);labelRoot.replaceChildren();labels=[];meshes=[];selected=null;
 const names=[...new Set(data.parts.map(p=>p.assembly))];
 for(const p of data.parts){
  const stock=data.stocks[p.stock];const mat=new THREE.MeshStandardMaterial({color:p.color||stock.color,roughness:.82,metalness:0});
  // Project coordinates are X,Y,Z-up; convert via parent rotation so rotations remain correct.
  const m=new THREE.Mesh(partGeometry(p),mat);
  const q=new THREE.Quaternion().setFromEuler(new THREE.Euler(...p.rotation.map(v=>v*Math.PI/180),'XYZ'));
  const basis=new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1,0,0),-Math.PI/2);
  m.quaternion.copy(basis).multiply(q);m.position.copy(vec(p.origin.map((v,i)=>v+p.size[i]/2)));
  m.userData=p;m.userData.basePosition=m.position.clone();m.userData.color=p.color||stock.color;
  const edge=new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry),new THREE.LineBasicMaterial({color:'#554b3f',transparent:true,opacity:.24}));m.add(edge);group.add(m);meshes.push(m);
 }
 const modelBounds=new THREE.Box3().setFromObject(group);
 // Order layers by their highest world elevation; geometry-average height
 // breaks ties (for example, roof surfaces and gables sharing a ridge).
 // Viewer Y is vertical; transformed vertices account for profiles and rotations.
 const elevations=new Map(names.map(name=>[name,{top:-Infinity,sum:0,count:0}]));
 const vertex=new THREE.Vector3();
 for(const mesh of meshes){
  const elevation=elevations.get(mesh.userData.assembly);
  const positions=mesh.geometry.getAttribute('position');
  for(let i=0;i<positions.count;i++){
   vertex.fromBufferAttribute(positions,i).applyMatrix4(mesh.matrixWorld);
   elevation.top=Math.max(elevation.top,vertex.y);elevation.sum+=vertex.y;elevation.count++;
  }
 }
 names.sort((a,b)=>{
  const left=elevations.get(a),right=elevations.get(b);
  const topDifference=right.top-left.top;
  return Math.abs(topDifference)>1e-6?topDifference:right.sum/right.count-left.sum/left.count;
 });
 const modelCenter=modelBounds.getCenter(new THREE.Vector3());
 if(!modelBounds.isEmpty())grid.position.set(modelCenter.x,modelBounds.min.y-.5,modelCenter.z);
 for(const d of data.dimensions){
  const a=vec(d.start),b=vec(d.end),line=new THREE.Line(new THREE.BufferGeometry().setFromPoints([a,b]),new THREE.LineBasicMaterial({color:'#577367'}));dimGroup.add(line);
  for(const pt of [a,b]){const tick=new THREE.Line(new THREE.BufferGeometry().setFromPoints([pt.clone().add(new THREE.Vector3(-1,1,0)),pt.clone().add(new THREE.Vector3(1,-1,0))]),new THREE.LineBasicMaterial({color:'#577367'}));dimGroup.add(tick);}
  const el=document.createElement('span');el.className='dimension';el.textContent=`${d.label} ${feet(d.inches)}`;labelRoot.append(el);labels.push({el,point:a.clone().lerp(b,.5),start:a,end:b});
 }
 $('partcount').textContent=data.parts.length;
 document.title=`stud – ${data.name}`;
 $('assemblycount').textContent=names.length;
 $('materials').innerHTML=data.materials.map(r=>`<tr><td>${escape(r.name)}<small>${escape(r.basis)}</small></td><td>${r.parts}</td><td>${escape(r.purchase)}<small>${escape(r.status)}</small></td><td>${safeLink(r.url)?`<a target="_blank" rel="noopener" href="${safeLink(r.url)}">Supplier ↗</a>`:'Not selected'}</td></tr>`).join('');
 if(data.validation_results)renderValidation({revision:data.revision,...data.validation_results});
 void environment.update(data.environment);
 applyDisplay();if(assemblyReview)openAssemblyDrawing(assemblyReview.assembly,assemblyReview.view);renderList();if(oldSelected)select(meshes.find(m=>m.userData.id===oldSelected));if(!camera)setView();renderComments();$('loading').hidden=true;
 if(isLiveUpdate&&!assemblyReview)buildAnimation.start(meshes.filter(m=>!previousIds.has(m.userData.id)),performance.now(),reducedMotion.matches);
 if(isLiveUpdate&&!assemblyReview)buildCamera.follow(bounds(),camera,controls,performance.now(),reducedMotion.matches);
}
reducedMotion.addEventListener('change',()=>{if(reducedMotion.matches){buildAnimation.finish();buildCamera.cancel();}});
function applyDisplay(){
 buildAnimation.finish();
 const explode=$('explode').checked;
 const names=[...new Set(meshes.map(m=>m.userData.assembly))];
 for(const m of meshes){m.visible=visibility.get(m.userData.assembly)!==false;m.position.copy(m.userData.basePosition);if(explode)m.position.y+=names.indexOf(m.userData.assembly)*17;
  if(assemblyReview&&assemblyReview.level!==null&&partMeasurement(m).level!==assemblyReview.level)m.visible=false;
  const opacity=m.userData.opacity??1;m.material.transparent=opacity<1;m.material.opacity=opacity;m.material.depthWrite=opacity===1;
  for(const edge of m.children)if(edge.isLineSegments){edge.material.opacity=assemblyReview?1:.24;edge.material.color.set(assemblyReview?getComputedStyle(document.documentElement).getPropertyValue('--ink').trim():'#554b3f');}
 }
 dimGroup.visible=!assemblyReview&&($('dims').getAttribute('aria-pressed')==='true')&&!explode;labelRoot.hidden=!dimGroup.visible;
 drawingDimensions.visible=!!assemblyReview&&$('dims').getAttribute('aria-pressed')==='true';$('assembly-labels').hidden=!drawingDimensions.visible;
 if(selected&&!selected.visible)select(null);renderList();
}
function select(mesh){
 selectedEnvironment = null; $('inspectortitle').textContent = 'PART';
 if(selected)selected.material.emissive.set('#000000');selected=mesh||null;
 $('inspectorpanel').hidden = !selected;
 if(selected) {
  const fromBrowser = $('modelpanel').contains(document.activeElement);
  if(innerWidth<1000)setModelPanel(false);
  if(fromBrowser&&innerWidth<1000) $('closeinspector').focus();
 }
 renderPartComments();
 if(!selected){$('inspector').innerHTML='<h2>Every piece,<br>accounted for.</h2><p>Select a part to inspect its dimensions.</p>';renderList();return;}
 selected.material.emissive.set('#68400f');const p=selected.userData,s=model.stocks[p.stock],fabrication=partMeasurement(selected);
 $('inspector').innerHTML=`<h2 class="partname">${escape(partLabel(p))}</h2><p class="partmaterial">${escape(s.name)}</p><div class="size">${fabrication.spec.kind==='part'?p.size.map(inches).join(' × '):escape(fabrication.spec.text)}</div><p>${placementText([fabrication],designBaseElevation())} above design base</p><span class="badge">${escape(p.status.toUpperCase())}</span><details class="parttechnical"><summary>Details</summary><div class="partid">${escape(p.id)}</div><dl><dt>Dimensions</dt><dd>${p.size.map(inches).join(" × ")}</dd><dt>Assembly</dt><dd>${escape(p.assembly)}</dd><dt>Origin (in.)</dt><dd>${p.origin.map(n=>Number(n.toFixed(2))).join(', ')}</dd><dt>Rotation (deg.)</dt><dd>${p.rotation.map(n=>Number(n.toFixed(2))).join(', ')}</dd></dl></details>${p.profile?.layers?`<p>Scribed profile: ${p.profile.layers.length} depth layers; one stock blank.</p>`:p.profile?.bands?`<p>Notched profile: ${p.profile.bands.length} connected depth bands; one stock blank.</p>`:p.profile?`<p>Profile front → rear: bottom ${p.profile.bottom.map(inches).join(" → ")}; top ${p.profile.top.map(inches).join(" → ")}.</p>`:""}${p.outline?`<p>Cut profile: ${p.outline.length} straight-edge Y/Z vertices; one stock blank.</p>`:''}${p.blank_size?`<p>Stock blank: ${p.blank_size.map(inches).join(" × ")}</p>`:""}${p.note?`<p>${escape(p.note)}</p>`:''}${safeLink(s.url)?`<a target="_blank" rel="noopener" href="${safeLink(s.url)}">Material candidate ↗</a>`:''}`;renderList();
}
const expandedAssemblies=new Set();
function partMeasurement(mesh){
 if(partMeasurements.has(mesh))return partMeasurements.get(mesh);
 const matrix=new THREE.Matrix4().compose(mesh.userData.basePosition,mesh.quaternion,mesh.scale);
 const box=new THREE.Box3(),point=new THREE.Vector3(),vertices=mesh.geometry.getAttribute('position');
 for(let i=0;i<vertices.count;i++)box.expandByPoint(point.fromBufferAttribute(vertices,i).applyMatrix4(matrix));
 const part=mesh.userData,spec=cutSpecification(part,model.stocks[part.stock]);
 const flatBottom=!spec.shaped&&[new THREE.Vector3(1,0,0),new THREE.Vector3(0,1,0),new THREE.Vector3(0,0,1)].some(axis=>Math.abs(axis.applyQuaternion(mesh.quaternion).y)>1-1e-6);
 const record={mesh,part,box,matrix,spec,flatBottom,level:mountingLevel(box.min.y)};
 partMeasurements.set(mesh,record);return record;
}
function assemblyRecords(name,level=null){
 return meshes.filter(mesh=>mesh.userData.assembly===name).map(partMeasurement).filter(record=>level===null||record.level===level);
}
function designBaseElevation(){return Math.min(...meshes.map(mesh=>partMeasurement(mesh).box.min.y));}
function placementText(records,base){
 const heights=[...new Set(records.map(record=>mountingLevel(record.box.min.y-base)))].sort((a,b)=>a-b);
 const flat=records.every(record=>record.flatBottom);
 return `${flat?'Bottom edge':'Lowest point'}${heights.length>1?'s':''} ${heights.map(workshopInches).join(' / ')}`;
}
function assemblyReviewControls(name){
 const all=assemblyRecords(name),base=designBaseElevation(),levels=[...new Set(all.map(record=>record.level))].sort((a,b)=>a-b);
 const level=assemblyReview?.assembly===name?assemblyReview.level:null;
 const records=all.filter(record=>level===null||record.level===level),groups=groupAssemblyCuts(records,model.stocks);
 return `<div class="assembly-review"><span class="drawing-label">2D drawings</span><div class="assembly-views" role="group" aria-label="${escape(name)} drawings">${[['top','Plan'],['front','Front'],['side','Side']].map(([view,label])=>`<button data-drawing="${escape(JSON.stringify([name,view]))}" data-scope="${escape(name)}" data-projection="${view}" aria-pressed="${assemblyReview?.assembly===name&&assemblyReview.view===view}">${label}</button>`).join('')}</div>${levels.length>1?`<label class="mounting-level">Mounting level<select data-level-scope="${escape(name)}" aria-label="${escape(name)} mounting level"><option value="all" ${level===null?'selected':''}>All levels</option>${levels.map(height=>`<option value="${height}" ${level===height?'selected':''}>${all.filter(r=>r.level===height).every(r=>r.flatBottom)?'Bottom':'Lowest point'} ${workshopInches(height-base)} · ${all.filter(r=>r.level===height).length} parts</option>`).join('')}</select></label>`:''}<details class="assembly-details" open><summary>Cut & placement</summary><p class="height-reference" title="Heights are measured from the lowest point of the complete design, including hidden assemblies. Environment objects are excluded.">Heights from design base</p><ul>${groups.map(group=>`<li><strong>${group.mark} · ${group.records.length} × ${escape(group.spec.text)}</strong><small>${escape(model.stocks[group.stock].name)}</small><span>${placementText(group.records,base)}</span>${group.spec.shaped?'<small>Shaped blank · inspect the part for profile details.</small>':''}</li>`).join('')}</ul></details></div>`;
}
function endAssemblyReview(returnTo3D=true){
 if(!assemblyReview)return;
 const previous=assemblyReview;assemblyReview=null;
 visibility.clear();for(const [name,visible] of previous.visibility)visibility.set(name,visible);
 $('explode').checked=previous.explode;$('dims').setAttribute('aria-pressed',String(previous.dimensions));
 grid.visible=previous.grid;environment.setEnabled($('environmenttoggle').checked);
 disposeTree(drawingDimensions);drawingLabels=[];$('assembly-labels').replaceChildren();$('drawing-context').hidden=true;
 applyDisplay();if(returnTo3D)setView('perspective');
}
function drawAssemblyInstructions(records,view,frame){
 disposeTree(drawingDimensions);drawingLabels=[];$('assembly-labels').replaceChildren();
 const box=frame.clone(),base=designBaseElevation(),groups=groupAssemblyCuts(records,model.stocks);
 const horizontal=view==='side'?'z':'x',vertical=view==='top'?'z':'y',depth=view==='top'?'y':view==='front'?'z':'x';
 const rightSign=view==='side'?-1:1,upSign=view==='top'?-1:1;
 const offset=Math.max(box.getSize(new THREE.Vector3()).length()*.08,2),lanes={horizontal:0,vertical:0,callout:0};
 const line=(a,b)=>{drawingDimensions.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([a,b]),new THREE.LineBasicMaterial({color:'#768179',depthTest:false})));frame.expandByPoint(a);frame.expandByPoint(b);};
 const label=(text,a,b,rotate=false,title='')=>{
  const el=document.createElement('span');el.className=`dimension fabrication-dimension${rotate?' vertical-dimension':''}`;el.textContent=text;el.title=title;
  $('assembly-labels').append(el);drawingLabels.push({el,drawing:true,vertical:rotate,point:a.clone().lerp(b,.5),start:a,end:b});
 };
 const dimension=(a,b,sourceA,sourceB,text,rotate=false,title='')=>{
  line(a,b);line(sourceA,a);line(sourceB,b);
  const delta=b.clone().sub(a),tick=new THREE.Vector3();tick[horizontal]=-delta[vertical];tick[vertical]=delta[horizontal];tick.normalize().multiplyScalar(offset*.12);
  for(const point of [a,b])line(point.clone().sub(tick),point.clone().add(tick));
  label(text,a,b,rotate,title);
 };
 for(const group of groups){
  const candidates=group.records.map(record=>{
   const a=new THREE.Vector3(),b=new THREE.Vector3();
   if(record.spec.axis>=0){a.setComponent(record.spec.axis,-record.part.size[record.spec.axis]/2);b.setComponent(record.spec.axis,record.part.size[record.spec.axis]/2);}
   a.applyMatrix4(record.matrix);b.applyMatrix4(record.matrix);
   const alongHorizontal=Math.abs(b[horizontal]-a[horizontal])>=Math.abs(b[vertical]-a[vertical]);
   const center=record.box.getCenter(new THREE.Vector3());
   return {record,a,b,projected:Math.hypot(b[horizontal]-a[horizontal],b[vertical]-a[vertical]),outward:alongHorizontal?upSign*center[vertical]:-rightSign*center[horizontal]};
  }).sort((a,b)=>Math.abs(b.projected-a.projected)>1e-6?b.projected-a.projected:b.outward-a.outward||b.record.box.max[depth]-a.record.box.max[depth]);
  const {a:sourceA,b:sourceB,projected}=candidates[0],spec=group.spec;
  const text=`${group.mark} · ${spec.text} · ×${group.records.length}`;
  const title=`${group.records.map(r=>r.part.id).join(', ')}. ${placementText(group.records,base)} above design base.`;
  if(spec.kind==='lumber'&&!spec.shaped&&projected>spec.length*.15){
   const a=sourceA.clone(),b=sourceB.clone(),alongHorizontal=Math.abs(b[horizontal]-a[horizontal])>=Math.abs(b[vertical]-a[vertical]);
   const axis=alongHorizontal?vertical:horizontal,sign=alongHorizontal?upSign:-rightSign;
   const lane=++lanes[alongHorizontal?'horizontal':'vertical'];
   const shift=sign*(offset*lane+Math.abs((sign>0?box.max[axis]:box.min[axis])-Math.max(a[axis],b[axis])));
   a[axis]+=shift;b[axis]+=shift;
   dimension(a,b,sourceA,sourceB,text,!alongHorizontal,title);
  }else{
   // End-on members and shaped blanks get a callout, never a false projected length.
   const nearest=[...group.records].sort((a,b)=>rightSign*(b.box.getCenter(new THREE.Vector3())[horizontal]-a.box.getCenter(new THREE.Vector3())[horizontal])||upSign*(b.box.getCenter(new THREE.Vector3())[vertical]-a.box.getCenter(new THREE.Vector3())[vertical]))[0];
   const anchor=nearest.box.getCenter(new THREE.Vector3()),target=anchor.clone();
   target[horizontal]=(rightSign>0?box.max[horizontal]:box.min[horizontal])+rightSign*offset*(1.5+lanes.callout++);
   target[vertical]+=upSign*offset*.75;
   line(anchor,target);label(text,anchor,target,false,title);
  }
 }
 if(view!=='top'){
  const start=box.min.clone(),end=box.max.clone();start.y=end.y=base;
  start[horizontal]-=offset*.5;end[horizontal]+=offset*.5;end[depth]=start[depth];line(start,end);
  const labelStart=start.clone(),labelEnd=end.clone();labelStart.y=labelEnd.y=base-offset*.6;
  label('Design base · 0″',labelStart,labelEnd);frame.expandByPoint(labelStart);frame.expandByPoint(labelEnd);
  const levels=[...new Set(records.map(record=>record.level))].sort((a,b)=>a-b);
  for(const [index,level] of levels.entries()){
   if(Math.abs(level-base)<1e-4)continue;
   const atLevel=records.filter(record=>record.level===level),record=atLevel[0];
   const sourceB=record.box.getCenter(new THREE.Vector3());sourceB.y=level;sourceB[horizontal]=(rightSign>0?record.box.max:record.box.min)[horizontal];const sourceA=sourceB.clone();sourceA.y=base;
   const a=sourceA.clone(),b=sourceB.clone();a[horizontal]=b[horizontal]=(rightSign>0?box.max[horizontal]:box.min[horizontal])+rightSign*offset*(index+1+lanes.callout);
   dimension(a,b,sourceA,sourceB,workshopInches(level-base),false,`Height from design base to ${atLevel.every(r=>r.flatBottom)?'bottom edge':'lowest point'}`);
  }
 }
 return {base,groups};
}
function openAssemblyDrawing(name,view,level){
 if(!meshes.some(mesh=>mesh.userData.assembly===name)){endAssemblyReview();return;}
 if(!['top','front','side'].includes(view))return;
 buildAnimation.finish();clearShow();clearValidationHighlights();clearAnnotationHover();select(null);
 const nextLevel=level===undefined?(assemblyReview?.assembly===name?assemblyReview.level:null):level;
 if(!assemblyReview){
  assemblyReview={visibility:new Map(visibility),explode:$('explode').checked,dimensions:$('dims').getAttribute('aria-pressed')==='true',grid:grid.visible};
  $('dims').setAttribute('aria-pressed','true');
 }
 Object.assign(assemblyReview,{assembly:name,view,level:assemblyRecords(name,nextLevel).length?nextLevel:null});expandedAssemblies.add(name);
 for(const mesh of meshes)visibility.set(mesh.userData.assembly,mesh.userData.assembly===name);
 $('explode').checked=false;grid.visible=false;environment.setEnabled(false);applyDisplay();
 const records=assemblyRecords(name,assemblyReview.level),frame=new THREE.Box3();for(const record of records)frame.union(record.box);
 const {base,groups}=drawAssemblyInstructions(records,view,frame);
 const placements=[...new Set(groups.map(group=>placementText(group.records,base)))];
 $('drawing-context').innerHTML=`<span>${escape(name)} · ${view==='top'?'Plan':view==='front'?'Front elevation':'Side elevation'}</span><small>${view==='top'?(placements.length===1?placements[0]:groups.map(group=>`${group.mark}: ${placementText(group.records,base)}`).join(' · '))+' above design base':(records.every(record=>record.flatBottom)?'Heights from design base to bottom edges':'Height references labeled on drawing')}</small>`;$('drawing-context').hidden=false;
 setView(view,frame);renderList();
 if(innerWidth<1000){setModelPanel(false);$('modeltoggle').focus({preventScroll:true});}
}
function partLabel(part){
 return part.name || part.id.split(/[._-]+/).join(' ');
}
function renderList(){
 if(!model)return;
 const q=$('search').value.trim().toLowerCase();
 const groups=new Map();
 for(const mesh of meshes){
  const p=mesh.userData;
  if(q&&!`${p.id} ${partLabel(p)} ${p.assembly} ${model.stocks[p.stock].name}`.toLowerCase().includes(q))continue;
  if(!groups.has(p.assembly))groups.set(p.assembly,[]);
  groups.get(p.assembly).push(mesh);
 }
 const focused=document.activeElement?.dataset;
 const focusKey=focused?.assembly||focused?.isolate||focused?.drawing||focused?.levelScope||focused?.id;
 const focusType=focused?.assembly?'assembly':focused?.isolate?'isolate':focused?.drawing?'drawing':focused?.levelScope?'levelScope':'id';
 $('assemblies').innerHTML=[...groups].map(([name,parts])=>{
  const visible=visibility.get(name)!==false,open=q||expandedAssemblies.has(name)||parts.includes(selected)||assemblyReview?.assembly===name;
  return `<section class="assembly-group"><div class="assembly-row"><button class="assembly-expand" data-expand="${escape(name)}" aria-expanded="${!!open}" aria-label="${open?'Collapse':'Expand'} ${escape(name)}"><span class="tree-chevron" aria-hidden="true">›</span><span>${escape(name)}</span><small>${parts.length}</small></button><label class="assembly-eye" title="${visible?'Hide':'Show'} ${escape(name)}"><input type="checkbox" data-assembly="${escape(name)}" aria-label="Show ${escape(name)}" ${visible?'checked':''}><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg></label><button class="assembly-isolate" data-isolate="${escape(name)}" title="Isolate ${escape(name)}" aria-label="Isolate ${escape(name)}">◎</button></div><div class="assembly-parts" ${open?'':'hidden'}>${assemblyReviewControls(name)}${parts.map(mesh=>`<button class="partitem ${mesh===selected?'selected':''}" data-id="${escape(mesh.userData.id)}" aria-pressed="${mesh===selected}" title="${escape(mesh.userData.id)}">${escape(partLabel(mesh.userData))}</button>`).join('')}</div></section>`;
 }).join('')||'<p class="sub">No parts match your search.</p>';
 $('assemblies').querySelectorAll('[data-expand]').forEach(button=>button.onclick=()=>{
  const open=button.getAttribute('aria-expanded')!=='true';
  button.setAttribute('aria-label',`${open?'Collapse':'Expand'} ${button.dataset.expand}`);
  button.setAttribute('aria-expanded',String(open));button.closest('.assembly-group').querySelector('.assembly-parts').hidden=!open;
  if(open)expandedAssemblies.add(button.dataset.expand);else expandedAssemblies.delete(button.dataset.expand);
 });
 $('assemblies').querySelectorAll('input').forEach(input=>input.onchange=()=>{endAssemblyReview();visibility.set(input.dataset.assembly,input.checked);applyDisplay();});
 $('assemblies').querySelectorAll('[data-isolate]').forEach(button=>button.onclick=()=>{
  endAssemblyReview();for(const mesh of meshes)visibility.set(mesh.userData.assembly,mesh.userData.assembly===button.dataset.isolate);
  applyDisplay();
 });
 $('assemblies').querySelectorAll('[data-drawing]').forEach(button=>button.onclick=()=>{openAssemblyDrawing(button.dataset.scope,button.dataset.projection);});
 $('assemblies').querySelectorAll('[data-level-scope]').forEach(select=>select.onchange=()=>openAssemblyDrawing(select.dataset.levelScope,assemblyReview?.assembly===select.dataset.levelScope?assemblyReview.view:'top',select.value==='all'?null:Number(select.value)));
 $('assemblies').querySelectorAll('[data-id]').forEach(button=>button.onclick=()=>{
  const mesh=meshes.find(m=>m.userData.id===button.dataset.id);if(assemblyReview&&assemblyReview.assembly!==mesh.userData.assembly)endAssemblyReview();else if(assemblyReview&&assemblyReview.level!==null&&partMeasurement(mesh).level!==assemblyReview.level)openAssemblyDrawing(assemblyReview.assembly,assemblyReview.view,partMeasurement(mesh).level);visibility.set(mesh.userData.assembly,true);applyDisplay();select(mesh);
 });
 if(focusKey){const replacement=[...$('assemblies').querySelectorAll(`[data-${focusType==='levelScope'?'level-scope':focusType}]`)].find(el=>el.dataset[focusType]===focusKey);replacement?.focus({preventScroll:true});}
}
let down;renderer.domElement.addEventListener('pointerdown',e=>down=[e.clientX,e.clientY]);renderer.domElement.addEventListener('pointerup',e=>{if(!camera||!down||Math.hypot(e.clientX-down[0],e.clientY-down[1])>4)return;const r=renderer.domElement.getBoundingClientRect();const ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1),camera);const partHit=ray.intersectObjects(meshes.filter(m=>m.visible),false)[0], environmentHit=environment.pick(ray);if(environmentHit&&(!partHit||environmentHit.distance<partHit.distance))inspectEnvironment(environmentHit.entry.asset.id);else select(partHit?.object);});
$('search').oninput=renderList;$('explode').onchange=()=>{const checked=$('explode').checked;endAssemblyReview();$('explode').checked=checked;applyDisplay();};
$('dims').onclick=()=>{ $('dims').setAttribute('aria-pressed',String($('dims').getAttribute('aria-pressed')!=='true')); applyDisplay(); };
$('reset').onclick=()=>{endAssemblyReview();visibility.clear();$('assemblies').querySelectorAll('input').forEach(i=>i.checked=true);applyDisplay();};
$('fit').onclick=()=>{buildCamera.stop();clearShow();if(assemblyReview)openAssemblyDrawing(assemblyReview.assembly,assemblyReview.view);else setView();};document.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{buildCamera.stop();setView(b.dataset.mode,bounds(),true);});

// Keep occasional tools off the canvas until requested.
const widePartsLayout=matchMedia('(min-width: 1000px)');
function partsPreferenceKey(){return `stud.parts-panel.${widePartsLayout.matches?'wide':'narrow'}`;}
function restorePartsPanel(){
 let saved=null;
 try{saved=localStorage.getItem(partsPreferenceKey());}catch{}
 setModelPanel(saved==='open'||(saved!=='closed'&&widePartsLayout.matches),{focus:false,animate:false});
}
function setModelPanel(open,{remember=false,focus=true,animate=true}={}) {
 $('modelpanel').hidden = !open;
 $('modeltoggle').setAttribute('aria-expanded', String(open));
 if(remember){try{localStorage.setItem(partsPreferenceKey(),open?'open':'closed');}catch{}}
 if(open){
  if(innerWidth<1000)select(null);
  if(focus)$('closemodel').focus({preventScroll:true});
  if(animate&&!reducedMotion.matches)$('modelpanel').animate([{opacity:0,transform:'translateX(-12px)'},{opacity:1,transform:'translateX(0)'}],{duration:180,easing:'ease-out'});
 }
}
$('modeltoggle').onclick=()=>{setModelPanel($('modelpanel').hidden,{remember:true});};
$('closemodel').onclick=()=>{setModelPanel(false,{remember:true}); $('modeltoggle').focus();};
widePartsLayout.addEventListener('change',restorePartsPanel);
$('closeinspector').onclick=()=>{select(null); $('modeltoggle').focus();};
$('page-select').onchange=()=>{ location.hash=$('page-select').value; };
function showPage(id) {
 const page = ['materials-section','costs'].includes(id) ? id : 'workspace';
 $('page-select').value=page;
 $('workspace').hidden = page !== 'workspace';
 $('reports').hidden = page === 'workspace';
 document.querySelectorAll('#reports > .materials').forEach(section=>section.hidden=section.id!==page);
 document.querySelectorAll('[data-page]').forEach(link=>{
  if(link.dataset.page===page) link.setAttribute('aria-current','page');
  else link.removeAttribute('aria-current');
 });
 $('thememenu').open=false;

 $('reports').scrollTop=0;
}
function showWorkspace() {
 if($('workspace').hidden) {
  history.pushState(null, '', '#workspace');
  showPage('workspace');
 }
}
document.addEventListener('pointerdown',event=>{
 if(!$('thememenu').contains(event.target)) $('thememenu').open=false;
});
document.addEventListener('keydown',event=>{
 if(event.key!=='Escape' || document.querySelector('dialog[open]')) return;
 if($('thememenu').open) {$('thememenu').open=false; $('thememenu').querySelector('summary').focus(); return;}
 if(!$('inspectorpanel').hidden) {select(null); $('modeltoggle').focus();}
 else if(!$('modelpanel').hidden) {setModelPanel(false,{remember:true}); $('modeltoggle').focus();}
});
function pageFromHash() { showPage(location.hash.slice(1)); }
window.addEventListener('hashchange',pageFromHash);
window.addEventListener('popstate',pageFromHash);
pageFromHash();
let viewportSize = null;
new ResizeObserver(()=>{
 const width=viewport.clientWidth, height=viewport.clientHeight;
 if(!width || !height) return;
 // Revealing the same canvas should preserve the user’s orbit, pan, and zoom.
 if(viewportSize?.width===width && viewportSize?.height===height) return;
 viewportSize={width,height};
 renderer.setSize(width,height);
 if(assemblyReview){openAssemblyDrawing(assemblyReview.assembly,assemblyReview.view);return;}
 if(camera){
  if(camera.isPerspectiveCamera)camera.aspect=width/height;
  else {const half=(camera.top-camera.bottom)/2;camera.left=-half*width/height;camera.right=half*width/height;}
  camera.updateProjectionMatrix();
 }
}).observe(viewport);
let modelRequest = null;
function loadModel() {
 if (modelRequest) return modelRequest;
 modelRequest = (async () => {
  try {
   const response = await fetch('/api/model', {cache:'no-store', signal:AbortSignal.timeout(25000)});
   const data = await response.json();
   if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
   if (data.schema_version !== 1 || data.units !== 'in' || !Array.isArray(data.parts)) throw new Error('Unsupported model');
   if (data.revision !== revision) install(data);
   $('error').hidden=true;
   return data;
  } catch (error) {
   $('error').hidden=false;$('error').textContent=`${model?'Keeping last good model.':'Unable to load model.'} ${error.message}`;
   throw error;
  } finally { modelRequest = null; }
 })();
 return modelRequest;
}
async function refresh(){try{await loadModel();}catch{}finally{setTimeout(refresh,2000);}}

function animate(){requestAnimationFrame(animate);if(!camera)return;buildCamera.update(camera,controls,performance.now());controls.update();buildAnimation.update(performance.now());for(const l of [...labels,...drawingLabels]){const p=l.point.clone().project(camera);const a=l.start.clone().project(camera),b=l.end.clone().project(camera);l.el.hidden=p.z< -1||p.z>1||Math.hypot((a.x-b.x)*viewport.clientWidth,(a.y-b.y)*viewport.clientHeight)<12;const margin=l.drawing?Math.max(20,(l.vertical?l.el.offsetHeight:l.el.offsetWidth)/2+8):65;l.el.style.left=`${Math.max(margin,Math.min(viewport.clientWidth-margin,(p.x*.5+.5)*viewport.clientWidth))}px`;l.el.style.top=`${(-p.y*.5+.5)*viewport.clientHeight}px`;}occupiedAnnotations=[];updateWarningPositions();updateCommentMarkers();updateEditorPosition();renderer.render(scene,camera);}animate();refresh();
// Small read-only diagnostics surface for automated verification.
window.stud=window.clubhouse={get model(){return model},get selected(){return selected?.userData.id},get visibleCount(){return meshes.filter(m=>m.visible).length},get view(){return currentView}};

let comments=[];
function renderPartComments(){
 const id=selected?.userData.id;
 $('partcomments').hidden=!comments.some(c=>!c.resolved&&c.part_id===id);
 $('partcommentlist').innerHTML=comments.filter(c=>!c.resolved&&c.part_id===id).map(c=>`<article class="comment"><p>${escape(c.text)}</p><small>${c.resolved?'Resolved':'Open'} · ${escape(new Date(c.created_at).toLocaleString())}</small></article>`).join('');
}
function renderComments(){
 renderCommentMarkers();

 renderPartComments();
}
async function commentRequest(payload){
 const r=await fetch('/api/comments',{method:payload?'POST':'GET',headers:payload?{'Content-Type':'application/json'}:{},body:payload?JSON.stringify(payload):undefined,cache:'no-store',signal:AbortSignal.timeout(10000)});
 const d=await r.json();if(!r.ok)throw new Error(d.error||'Comments unavailable');comments=d.comments.filter(c=>!c.deleted);renderComments();
}
async function refreshComments(){try{await commentRequest();}catch(e){$('commentstatus').textContent='Comments unavailable: '+e.message;}finally{setTimeout(refreshComments,5000);}}
refreshComments();

let estimate=null;
const priceEdits=new Map(),priceTimers=new Map();let priceQueue=Promise.resolve();
const money=v=>v===null?'—':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(Number(v));
const fields=['quantity','unit_price','source','observed_on','note'];
const today=()=>new Date().toLocaleDateString('en-CA');
function priceValues(r){const q=r.quote;return {quantity:q?.quantity??'',unit_price:q?.unit_price??'',source:q?.source||'Manual entry',observed_on:q?.observed_on||today(),note:q?.note||'',url:q?.url||''};}
function priceRow(key){return [...$('pricerows').children].find(tr=>tr.dataset.key===key);}
function rowStatus(key,message,error=false){const el=priceRow(key)?.querySelector('.savestate');if(el){el.textContent=message;el.classList.toggle('saveerror',error);}}
function summary(data){
 const b=data.budget;
 $('costsummary').textContent=b?`${money(b.grand_total)} planned total · ${money(b.over_target)} over ${money(b.target)} budget${b.complete?'':' · incomplete pricing'}`:`${money(data.subtotal)} saved subtotal`;
 $('costbreakdown').textContent=b?`Items ${money(data.subtotal)} + estimated tax ${money(b.sales_tax)} + 10% contingency ${money(b.contingency)}. ${data.price_kinds.source.lines} sourced prices, ${data.price_kinds.manual.lines} manual prices, ${data.price_kinds.estimate.lines} estimates; ${data.unpriced_lines} unpriced.`:'';
 $('costcategories').innerHTML=Object.entries(data.categories||{}).map(([name,total])=>`<span>${escape(name)}: <b>${money(total)}</b></span>`).join(' · ');
}

function renderPrices(data){
 estimate=data;summary(data);
 const live=new Set(data.rows.map(r=>r.key));
 for(const tr of [...$('pricerows').children])if(!live.has(tr.dataset.key)&&!priceEdits.has(tr.dataset.key))tr.remove();
 for(const r of data.rows){
  let tr=priceRow(r.key);
  if(!tr){tr=document.createElement('tr');tr.dataset.key=r.key;
   const cell=(field,type='text',extra='')=>`<input data-field="${field}" type="${type}" aria-label="${escape(r.name+' '+r.unit+' '+field)}" ${extra}>`;
   tr.innerHTML=`<td class="pricename">${escape(r.name)}<small>${escape(r.unit)}</small></td><td>${cell('quantity','number','min="1" step="1"')}<small class="qtybasis"></small></td><td>${cell('unit_price','number','min="0" step=".01" placeholder="—"')}</td><td class="lineamount">—</td><td>${cell('source','text','maxlength="200"')}<details><summary>Source link</summary>${cell('url','url','placeholder="https://..." maxlength="2000"')}<span class="evidence"></span></details></td><td>${cell('observed_on','date')}</td><td>${cell('note','text','maxlength="1000" placeholder="Grade, quote reference…"')}</td><td><span class="savestate" role="status"></span><button class="retryprice" type="button">Retry</button><button class="clearprice" type="button">Reset quote</button></td>`;
   $('pricerows').append(tr);
   tr.querySelectorAll('input').forEach(input=>{
    input.addEventListener('input',()=>editPrice(tr));
    input.addEventListener('blur',()=>{if(priceEdits.has(r.key))schedulePrice(r.key,0);});
    input.addEventListener('keydown',e=>{
     const rows=[...$('pricerows').children],ri=rows.indexOf(tr),ci=fields.indexOf(input.dataset.field);
     if(e.key==='Enter'){e.preventDefault();rows[ri+(e.shiftKey?-1:1)]?.querySelector(`[data-field="${input.dataset.field}"]`)?.focus();}
     if(e.key==='Tab'&&ci>=0){const n=ri*fields.length+ci+(e.shiftKey?-1:1);if(n>=0&&n<rows.length*fields.length){e.preventDefault();rows[Math.floor(n/fields.length)].querySelector(`[data-field="${fields[n%fields.length]}"]`).focus();}}
    });
    input.addEventListener('paste',e=>pastePrices(e,tr,input));
   });
   tr.querySelector('.retryprice').onclick=()=>schedulePrice(r.key,0);
   tr.querySelector('.clearprice').onclick=()=>{clearTimeout(priceTimers.get(r.key));const edit={values:priceValues(r),version:Symbol()};priceEdits.set(r.key,edit);enqueuePrice(r.key,{key:r.key,action:'clear_manual'},edit.version);};
  }
  tr.querySelector('.qtybasis').textContent=`Model: ${r.model_quantity??'specify lot count'}`;
  tr.querySelector('[data-field="quantity"]').placeholder=r.model_quantity??'Required';
  tr.querySelector('.lineamount').textContent=money(r.total);
  tr.querySelector('.clearprice').hidden=!r.has_manual&&!priceEdits.has(r.key);
  tr.querySelector('.evidence').innerHTML=r.sourced_quote?`<small>Source: ${money(r.sourced_quote.unit_price)} · ${escape(r.sourced_quote.source)}</small>`:'';
  if(!priceEdits.has(r.key)&&!(tr.contains(document.activeElement)&&document.activeElement.matches('input'))){
   const v=priceValues(r);tr.querySelectorAll('input').forEach(i=>i.value=v[i.dataset.field]);
   rowStatus(r.key,r.quote?(r.has_manual?'Manual':r.quote_kind==='estimate'?'Estimate':'Sourced'):'Not priced');
  }
 }
}
function editPrice(tr){
 const values={};tr.querySelectorAll('input').forEach(i=>values[i.dataset.field]=i.value);
 const edit={values,version:Symbol()};priceEdits.set(tr.dataset.key,edit);rowStatus(tr.dataset.key,'Unsaved');schedulePrice(tr.dataset.key,700);
}
function schedulePrice(key,delay){clearTimeout(priceTimers.get(key));priceTimers.set(key,setTimeout(()=>savePriceRow(key),delay));}
function savePriceRow(key){
 const edit=priceEdits.get(key);if(!edit)return;
 const v=edit.values,r=estimate.rows.find(r=>r.key===key);
 if(!r){rowStatus(key,'Material removed; copy your draft.',true);return;}
 if(v.unit_price===''){rowStatus(key,'Enter price to save',true);return;}
 const tr=priceRow(key);
 if([...tr.querySelectorAll('input')].some(i=>!i.checkValidity())){rowStatus(key,'Check cell values',true);return;}
 if(!v.source.trim()||!v.observed_on){rowStatus(key,'Supplier and date needed',true);return;}
 if(r.model_quantity===null&&!v.quantity){rowStatus(key,'Enter lot quantity',true);return;}
 enqueuePrice(key,{key,kind:'manual',...v,quantity:v.quantity?Number(v.quantity):null},edit.version);
}
function enqueuePrice(key,payload,version){
 rowStatus(key,'Saving…');
 priceQueue=priceQueue.then(async()=>{
  // A newer edit supersedes an unsent save.
  if(version&&priceEdits.get(key)?.version!==version)return;
  try{
   const data=await priceRequest(payload);
   if(!version||priceEdits.get(key)?.version===version){priceEdits.delete(key);rowStatus(key,payload.action?'Reset':'Saved');}
   renderPrices(data);
  }catch(e){rowStatus(key,'Not saved — '+e.message,true);}
 });
}
async function priceRequest(payload){
 const r=await fetch('/api/pricing',{method:payload?'POST':'GET',headers:payload?{'Content-Type':'application/json'}:{},body:payload?JSON.stringify(payload):undefined,cache:'no-store',signal:AbortSignal.timeout(25000)});const d=await r.json();if(!r.ok)throw new Error(d.error||'Could not load prices');return d;
}
function pastePrices(e,tr,input){
 const text=e.clipboardData.getData('text');if(!text.includes('\t')&&!text.includes('\n'))return;
 const start=fields.indexOf(input.dataset.field);if(start<0)return;e.preventDefault();
 const rows=[...$('pricerows').children],at=rows.indexOf(tr);
 text.replace(/\r/g,'').replace(/\n$/,'').split('\n').forEach((line,n)=>{const row=rows[at+n];if(!row)return;line.split('\t').forEach((value,col)=>{const field=fields[start+col];if(!field)return;const target=row.querySelector(`[data-field="${field}"]`);target.value=field==='unit_price'?value.replace(/[$,]/g,''):value;});editPrice(row);});
}
window.addEventListener('beforeunload',e=>{if(priceEdits.size){e.preventDefault();e.returnValue='';}});
async function refreshPrices(){try{renderPrices(await priceRequest());$('priceerror').textContent='';}catch(e){$('priceerror').textContent='Prices unavailable: '+e.message;}finally{setTimeout(refreshPrices,5000);}}
refreshPrices();

function clearValidationHighlights(){
 for(const m of meshes)if(validationHighlights.has(m.userData.id))m.material.emissive.set(m===selected?'#543c1f':'#000000');
 validationHighlights.clear();disposeTree(validationGroup);
}
function showValidationFinding(f){
 clearValidationHighlights();
 if(validationReport?.revision!==revision)return;
 showWorkspace();endAssemblyReview();
 const targets=meshes.filter(m=>f.parts.includes(m.userData.id));
 for(const m of targets){visibility.set(m.userData.assembly,true);validationHighlights.add(m.userData.id);}
 $('assemblies').querySelectorAll('input').forEach(i=>i.checked=visibility.get(i.dataset.assembly)!==false);
 $('explode').checked=false;applyDisplay();
 if(targets.length)select(targets.find(m=>m.userData.id===f.parts[0])||targets[0]);
 for(const m of targets){
  m.material.emissive.set('#874015');
  const outline=new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry),new THREE.LineBasicMaterial({color:'#e66b20',depthTest:false}));
  outline.position.copy(m.position);outline.quaternion.copy(m.quaternion);outline.renderOrder=9;validationGroup.add(outline);
 }
 if(Array.isArray(f.location)&&f.location.length===3&&f.location.every(Number.isFinite)){
  const marker=new THREE.Mesh(new THREE.SphereGeometry(1.25,12,8),new THREE.MeshBasicMaterial({color:'#ed7c29',depthTest:false}));
  marker.position.copy(vec(f.location));marker.renderOrder=10;validationGroup.add(marker);
 }
}
function workspaceFindings(report){
 // General coverage gaps and author notes are not defects in the displayed model.
 // Keep specific review gaps and actual failures, including configuration failures.
 return (report.findings||[]).filter(f=>f.status!=='PASS'&&(f.status!=='UNVERIFIED'||f.parts?.length>0));
}
function renderValidation(report){
 validationReport=report;
 $('warning-detail').hidden=true;
 const findings=workspaceFindings(report);
 renderWarningAnnotations({...report,findings});
 const count=findings.length;
 const toggle=$('validation-toggle');toggle.hidden=!count;
 toggle.classList.toggle('has-warnings',count>0);
 const list=$('warning-list');list.replaceChildren();
 for(const finding of findings){
  const card=document.createElement('button');card.className='warning-card';
  const title=document.createElement('strong');title.textContent=(finding.status==='UNVERIFIED'?'Needs review':finding.status)+' · '+finding.rule;
  const message=document.createElement('span');message.textContent=finding.message;
  card.append(title,message);card.onclick=()=>showValidationFinding(finding);list.append(card);
 }
 if(!count){
  list.hidden=true;toggle.setAttribute('aria-expanded','false');toggle.setAttribute('aria-pressed','false');
  clearValidationHighlights();
 }
 $('validation-toggle').title=`Validation warnings (${count})`;
 $('validation-toggle').setAttribute('aria-label',`Validation warnings (${count})`);
}
async function refreshValidation(){
 try{
  const response=await fetch('/api/validation',{cache:'no-store',signal:AbortSignal.timeout(25000)});
  if(!response.ok)throw new Error(`HTTP ${response.status}`);
  const report=await response.json(),signature=JSON.stringify(report)+revision;
  if(signature!==validationSignature){validationSignature=signature;clearValidationHighlights();renderValidation(report);}
 }catch(e){$('validation-toggle').title='Latest checks unavailable: '+e.message;}
 finally{setTimeout(refreshValidation,5000);}
}
refreshValidation();

const showTool=createShowTool({loadModel,display:displayShow});
registerShowTool(document.modelContext,showTool).catch(error=>console.warn('stud show tool could not register:',error));

$('closeareaimage').onclick=()=>$('areaimageview').close();
installAreaCapture({viewport,capture:()=>{
 if(!model||!camera)throw new Error('Load a design before capturing an area.');
 buildAnimation.finish();
 renderer.render(scene,camera);
 return {canvas:snapshotViewer(renderer.domElement,assemblyReview?$('assembly-labels'):labelRoot),revision};
},save:commentRequest,anchorAt:(x,y)=>{
 const box=renderer.domElement.getBoundingClientRect(),ray=new THREE.Raycaster();
 ray.setFromCamera(new THREE.Vector2((x-box.left)/box.width*2-1,-(y-box.top)/box.height*2+1),camera);
 const hit=ray.intersectObjects(meshes.filter(m=>m.visible),false)[0];
 return (hit?.point || ray.ray.at(camera.position.distanceTo(bounds().getCenter(new THREE.Vector3())),new THREE.Vector3())).toArray();
},selectPart:(x,y)=>{
 if(!camera)return false;
 const box=renderer.domElement.getBoundingClientRect(),ray=new THREE.Raycaster();
 ray.setFromCamera(new THREE.Vector2((x-box.left)/box.width*2-1,-(y-box.top)/box.height*2+1),camera);
 const hit=ray.intersectObjects(meshes.filter(m=>m.visible),false)[0];
 if(!hit)return false;
 select(hit.object);return hit.object.userData.id;
}});

function renderWarningAnnotations(report){
 const root=$('warning-annotations');root.replaceChildren();warningAnnotations=[];
 if(report.revision!==revision)return;
 for(const finding of report.findings||[]){
  if(finding.status==='PASS')continue;
  const targets=meshes.filter(m=>(finding.parts||[]).includes(m.userData.id));
  if(!targets.length)continue;
  const button=document.createElement('button');button.className='warning-annotation';
  button.textContent='⚠';button.title=`${finding.status}: ${finding.message}`;
  button.setAttribute('aria-label',button.title);
  button.onclick=()=>{
   showValidationFinding(finding);
   $('warning-title').textContent=finding.status+' · '+finding.rule;
   $('warning-message').textContent=finding.message;$('warning-detail').hidden=false;
  };
  attachAnnotationHover(button,targets);
  root.append(button);warningAnnotations.push({button,targets,finding});
 }
}
function updateWarningPositions(){
 const enabled=$('validation-toggle').getAttribute('aria-pressed')==='true';
 $('warning-annotations').hidden=!enabled;
 if(!enabled)return;
 for(const {button,targets,finding} of warningAnnotations){
  if(validationReport?.revision!==revision){button.hidden=true;continue;}
  const visible=targets.filter(m=>m.visible);
  if(targets.length&&!visible.length){button.hidden=true;continue;}
  const box=new THREE.Box3();visible.forEach(m=>box.expandByObject(m));
  const point=box.getCenter(new THREE.Vector3()).project(camera);
  button.hidden=point.z < -1 || point.z > 1 || Math.abs(point.x)>1 || Math.abs(point.y)>1;
  positionAnnotation(button,point);
 }
}
$('validation-toggle').onclick=()=>{
 const button=$('validation-toggle'),list=$('warning-list');
 const open=button.getAttribute('aria-expanded')!=='true';
 button.setAttribute('aria-expanded',String(open));button.setAttribute('aria-pressed',String(open));
 list.getAnimations({subtree:true}).forEach(animation=>animation.cancel());
 if(open){
  list.hidden=false;
  if(!reducedMotion.matches)[...list.children].forEach((card,i)=>card.animate([{opacity:0,transform:'translateX(16px) scale(.96)'},{opacity:1,transform:'translateX(0) scale(1)'}],{duration:180,delay:Math.min(i,5)*35,fill:'backwards',easing:'ease-out'}));
 }else{
  $('warning-detail').hidden=true;clearValidationHighlights();
  if(reducedMotion.matches)list.hidden=true;
  else list.animate([{opacity:1,transform:'translateX(0)'},{opacity:0,transform:'translateX(12px)'}],{duration:140,easing:'ease-in'}).finished.then(()=>{if(button.getAttribute('aria-expanded')==='false')list.hidden=true;}).catch(()=>{});
 }
};
$('close-warning').onclick=()=>{$('warning-detail').hidden=true;clearValidationHighlights();};

function renderCommentMarkers(){
 const root=$('comment-markers');root.replaceChildren();commentMarkers=[];
 for(const c of comments.filter(c=>!c.resolved)){
  if(c.kind==='area'&&(!c.anchor||c.revision!==revision))continue;
  const button=document.createElement('button');button.className='comment-marker';
  button.innerHTML='<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M7 4h10a4 4 0 0 1 4 4v6a4 4 0 0 1-4 4H8l-5 3V8a4 4 0 0 1 4-4Z"/></svg>';
  button.title=c.text;button.setAttribute('aria-label','Comment: '+c.text);
  attachAnnotationHover(button,meshes.filter(m=>m.userData.id===c.part_id),c.anchor);
  button.onclick=()=>openCommentEditor(c,button);root.append(button);commentMarkers.push({button,c});
 }
}
function updateCommentMarkers(){
 for(const {button,c} of commentMarkers){
  const mesh=meshes.find(m=>m.userData.id===c.part_id);
  if(c.kind==='area'?c.revision!==revision:!mesh?.visible){button.hidden=true;continue;}
  const point=c.kind==='area'?new THREE.Vector3(...c.anchor):new THREE.Box3().setFromObject(mesh).getCenter(new THREE.Vector3());
  point.project(camera);button.hidden=Math.abs(point.x)>1||Math.abs(point.y)>1||Math.abs(point.z)>1;
  positionAnnotation(button,point);
 }
}

let editingComment=null,editingBusy=false;
function openCommentEditor(comment,marker){
 editingComment=comment.id;
 const dialog=$('comment-editor'),rect=marker.getBoundingClientRect();
 $('edit-comment-text').value=comment.text;$('edit-comment-status').textContent='';
 dialog.showModal();
 positionEditor(rect);
 $('edit-comment-text').focus();
}
$('cancel-edit-comment').onclick=()=>{if(!editingBusy)$('comment-editor').close();};
$('comment-editor').addEventListener('cancel',e=>{if(editingBusy)e.preventDefault();});
async function updateEditedComment(action){
 if(editingBusy)return;
 editingBusy=true;
 for(const id of ['save-edit-comment','delete-comment','cancel-edit-comment','edit-comment-text'])$(id).disabled=true;
 try{await commentRequest({action,id:editingComment,text:$('edit-comment-text').value});$('comment-editor').close();}
 catch(error){$('edit-comment-status').textContent=error.message;}
 finally{editingBusy=false;for(const id of ['save-edit-comment','delete-comment','cancel-edit-comment','edit-comment-text'])$(id).disabled=false;}
}
$('edit-comment-form').onsubmit=e=>{e.preventDefault();void updateEditedComment('edit');};
$('delete-comment').onclick=()=>updateEditedComment('delete');

function positionAnnotation(button,point){
 if(button.hidden)return;
 const placed=placeAnnotation((point.x*.5+.5)*viewport.clientWidth,(-point.y*.5+.5)*viewport.clientHeight,viewport.clientWidth,viewport.clientHeight,occupiedAnnotations);
 if(!placed){button.hidden=true;return;}
 button.style.left=placed.x+'px';button.style.top=placed.y+'px';
}
function positionEditor(rect){
 const dialog=$('comment-editor'),p=editorPosition(rect,dialog.offsetWidth,dialog.offsetHeight,innerWidth,innerHeight);
 dialog.style.left=p.left+'px';dialog.style.top=p.top+'px';
}
function updateEditorPosition(){
 if(!$('comment-editor').open)return;
 const marker=commentMarkers.find(m=>m.c.id===editingComment)?.button;
 if(marker&&!marker.hidden)positionEditor(marker.getBoundingClientRect());
}
const annotationHover=new THREE.Group();scene.add(annotationHover);
function clearAnnotationHover(){
 for(const child of [...annotationHover.children]){child.geometry.dispose();child.material.dispose();annotationHover.remove(child);}
}
function attachAnnotationHover(button,targets,anchor){
 const show=()=>{
  clearAnnotationHover();
  for(const mesh of targets.filter(m=>m.visible)){
   const line=new THREE.LineSegments(new THREE.EdgesGeometry(mesh.geometry),new THREE.LineBasicMaterial({color:0xff6534,depthTest:false}));
   line.position.copy(mesh.position);line.quaternion.copy(mesh.quaternion);line.renderOrder=12;annotationHover.add(line);
  }
  if(!targets.length&&anchor){
   const dot=new THREE.Mesh(new THREE.SphereGeometry(2,12,8),new THREE.MeshBasicMaterial({color:0xff6534,wireframe:true,depthTest:false}));dot.position.fromArray(anchor);dot.renderOrder=12;annotationHover.add(dot);
  }
 };
 button.addEventListener('pointerenter',show);button.addEventListener('pointerleave',clearAnnotationHover);
 button.addEventListener('focus',show);button.addEventListener('blur',clearAnnotationHover);
}
restorePartsPanel();
