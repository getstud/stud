import * as THREE from 'three';
import {outlineGeometry,bandedGeometry,layeredGeometry} from '/profile-geometry.js';
import {createEnvironment} from '/environment.js';
import {OrbitControls} from '/vendor/OrbitControls.js';
import {createShowTool, registerShowTool} from '/show.js';
import {installAreaCapture, snapshotViewer} from '/area-capture.js';
import {preserveCamera} from '/camera-transition.js';
import {FlyControls} from '/fly-controls.js';
import {BuildAnimation} from '/build-animation.js';
const buildAnimation=new BuildAnimation();
const reducedMotion=matchMedia('(prefers-reduced-motion: reduce)');
const $=id=>document.getElementById(id);
const viewport=$('viewport'), labelRoot=$('labels');
// Thin roof layers need depth precision even when the exploded view is zoomed out.
const renderer=new THREE.WebGLRenderer({antialias:true,alpha:false,logarithmicDepthBuffer:true});
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
$('environmenttoggle').onchange = () => environment.setEnabled($('environmenttoggle').checked);
$('fitscene').onclick = () => {clearShow();showFrame = bounds().union(environment.bounds());setView(currentView, showFrame);};
const validationGroup=new THREE.Group();scene.add(validationGroup);
let validationReport=null,validationSignature='',validationHighlights=new Set();
function vec(v){return new THREE.Vector3(v[0],v[2],-v[1]);}
function escape(s){return String(s).replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));}
function inches(v){return `${Number(v.toFixed(3))}″`;}
function feet(v){let f=Math.floor(v/12),i=Number((v-f*12).toFixed(3));return f?`${f}′ ${i}″`:`${i}″`;}
function safeLink(url){try{const u=new URL(url);return u.protocol==='https:'?escape(u.href):'';}catch{return '';}}
function bounds(){return buildAnimation.atRest(()=>{const box=new THREE.Box3();for(const m of meshes)if(m.visible)box.expandByObject(m);if(model&&$('dims').checked&&!$('explode').checked)for(const d of model.dimensions){box.expandByPoint(vec(d.start));box.expandByPoint(vec(d.end));}return box.isEmpty()?new THREE.Box3(new THREE.Vector3(0,0,-96),new THREE.Vector3(144,160,0)):box;});}
let focusDistance = 100;
function setView(name=currentView, frame=bounds(), preserve=false){
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
  const half=Math.max(height/2,width/(2*aspect),10)*1.22;
  camera=new THREE.OrthographicCamera(-half*aspect,half*aspect,half,-half,.1,10000);
  if(name==='top'){camera.up.set(0,0,-1);camera.position.copy(center).add(new THREE.Vector3(0,extent*4,0));}
  if(name==='front')camera.position.copy(center).add(new THREE.Vector3(0,0,extent*4));
  if(name==='side')camera.position.copy(center).add(new THREE.Vector3(extent*4,0,0));
 }
 camera.lookAt(center);
 let target=center;
 if(preserve && previous){const state=preserveCamera(previous,camera,name,previousTarget,focusDistance);target=state.focus;focusDistance=state.distance;}
 else focusDistance=camera.position.distanceTo(center);
 if(name==='firstperson')controls=new FlyControls(camera,renderer.domElement);
 else {controls=new OrbitControls(camera,renderer.domElement);controls.target.copy(target);controls.enableDamping=true;controls.enableRotate=name==='perspective';controls.minDistance=.01;controls.maxDistance=Infinity;controls.update();}
 document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===name));
 $('navigationhint').textContent=name==='firstperson'?'Click scene · WASD fly · Drag to look · Q/E down/up · Shift faster · Esc release':'Drag to orbit · Click a part to inspect';
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
 showWorkspace();
 const targets=(input.part_ids||[]).map(id=>meshes.find(m=>m.userData.id===id));
 clearShow();clearValidationHighlights();
 visibility.clear();$('assemblies').querySelectorAll('input').forEach(i=>i.checked=true);
 $('explode').checked=false;$('ghost').checked=false;$('search').value='';applyDisplay();
 select(targets.length===1?targets[0]:null);
 const frame=new THREE.Box3();
 if(input.region){
  frame.setFromPoints([vec(input.region.min),vec(input.region.max)]);
 }else if(targets.length){
  for(const mesh of targets)frame.expandByObject(mesh);
 }else frame.copy(bounds());
 if(targets.length||input.region){
  const outline=new THREE.Box3Helper(frame.clone(),0xb05e22);
  outline.material.depthTest=false;outline.material.transparent=true;outline.material.opacity=.85;
  outline.renderOrder=10;showGroup.add(outline);
 }
 showFrame=frame.clone();setView(input.view||'perspective',showFrame);
 $('notes').close();viewport.scrollIntoView({block:'center',behavior:'instant'});
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
 $('projectname').textContent=data.name;
 document.title=`${data.name} / stud`;
 $('assemblycount').textContent=names.length;
 $('assemblies').innerHTML=names.map((name,i)=>`<label class="assembly"><input type="checkbox" data-assembly="${escape(name)}" ${visibility.get(name)!==false?'checked':''}><span>${escape(name)}</span><small>${data.parts.filter(p=>p.assembly===name).length}</small></label>`).join('');
 $('assemblies').querySelectorAll('input').forEach(input=>input.onchange=()=>{visibility.set(input.dataset.assembly,input.checked);applyDisplay();});
 $('materials').innerHTML=data.materials.map(r=>`<tr><td>${escape(r.name)}<small>${escape(r.basis)}</small></td><td>${r.parts}</td><td>${escape(r.purchase)}<small>${escape(r.status)}</small></td><td>${safeLink(r.url)?`<a target="_blank" rel="noopener" href="${safeLink(r.url)}">Supplier ↗</a>`:'Not selected'}</td></tr>`).join('');
 $('notelist').innerHTML=data.notes.map(n=>`<li>${escape(n)}</li>`).join('');
 if(data.validation_results)renderValidation({revision:data.revision,...data.validation_results});
 void environment.update(data.environment);
 applyDisplay();renderList();if(oldSelected)select(meshes.find(m=>m.userData.id===oldSelected));if(!camera)setView();renderComments();$('loading').hidden=true;
 if(isLiveUpdate)buildAnimation.start(meshes.filter(m=>!previousIds.has(m.userData.id)),performance.now(),reducedMotion.matches);
}
reducedMotion.addEventListener('change',()=>{if(reducedMotion.matches)buildAnimation.finish();});
function applyDisplay(){
 buildAnimation.finish();
 const explode=$('explode').checked,ghost=$('ghost').checked;
 const names=[...new Set(meshes.map(m=>m.userData.assembly))];
 for(const m of meshes){m.visible=visibility.get(m.userData.assembly)!==false;m.position.copy(m.userData.basePosition);if(explode)m.position.y+=names.indexOf(m.userData.assembly)*17;
  const transparent=ghost&&['Wall finish','Floor surface','Roof membrane','Deck boards'].includes(m.userData.assembly);const opacity=transparent?.18:(m.userData.opacity??1);m.material.transparent=opacity<1;m.material.opacity=opacity;m.material.depthWrite=opacity===1;
 }
 dimGroup.visible=$('dims').checked&&!explode;labelRoot.hidden=!dimGroup.visible;
 if(selected&&!selected.visible)select(null);renderList();
}
function select(mesh){
 selectedEnvironment = null; $('inspectortitle').textContent = 'PART INSPECTOR';
 rememberDraft();
 if(selected)selected.material.emissive.set('#000000');selected=mesh||null;
 $('inspectorpanel').hidden = !selected;
 if(selected) {
  const fromBrowser = $('modelpanel').contains(document.activeElement);
  setModelPanel(false);
  if(fromBrowser) $('closeinspector').focus();
 }
 renderPartComments();
 if(!selected){$('inspector').innerHTML='<h2>Every piece,<br>accounted for.</h2><p>Select a part to inspect its dimensions.</p>';renderList();return;}
 selected.material.emissive.set('#68400f');const p=selected.userData,s=model.stocks[p.stock];
 $('inspector').innerHTML=`<div class="partid">${escape(p.id)}</div><span class="badge">${escape(p.status.toUpperCase())}</span><div class="size">${p.size.map(inches).join(' × ')}</div><p>${escape(s.name)}</p><dl><dt>Assembly</dt><dd>${escape(p.assembly)}</dd><dt>Origin (in.)</dt><dd>${p.origin.map(n=>Number(n.toFixed(2))).join(', ')}</dd><dt>Rotation (deg.)</dt><dd>${p.rotation.map(n=>Number(n.toFixed(2))).join(', ')}</dd></dl>${p.profile?.layers?`<p>Scribed profile: ${p.profile.layers.length} depth layers; one stock blank.</p>`:p.profile?.bands?`<p>Notched profile: ${p.profile.bands.length} connected depth bands; one stock blank.</p>`:p.profile?`<p>Profile front → rear: bottom ${p.profile.bottom.map(inches).join(" → ")}; top ${p.profile.top.map(inches).join(" → ")}.</p>`:""}${p.outline?`<p>Cut profile: ${p.outline.length} straight-edge Y/Z vertices; one stock blank.</p>`:''}${p.blank_size?`<p>Stock blank: ${p.blank_size.map(inches).join(" × ")}</p>`:""}${p.note?`<p>${escape(p.note)}</p>`:''}${safeLink(s.url)?`<a target="_blank" rel="noopener" href="${safeLink(s.url)}">Material candidate ↗</a>`:''}`;renderList();
}
function renderList(){if(!model)return;const q=$('search').value.toLowerCase();const filtered=meshes.filter(m=>m.visible&&`${m.userData.id} ${m.userData.assembly} ${model.stocks[m.userData.stock].name}`.toLowerCase().includes(q));$('partlist').innerHTML=filtered.map(m=>`<button class="partitem ${m===selected?'selected':''}" data-id="${escape(m.userData.id)}">${escape(m.userData.id)}</button>`).join('')||'<p>No matching visible parts.</p>';$('partlist').querySelectorAll('button').forEach(b=>b.onclick=()=>select(meshes.find(m=>m.userData.id===b.dataset.id)));}
let down;renderer.domElement.addEventListener('pointerdown',e=>down=[e.clientX,e.clientY]);renderer.domElement.addEventListener('pointerup',e=>{if(!camera||!down||Math.hypot(e.clientX-down[0],e.clientY-down[1])>4)return;const r=renderer.domElement.getBoundingClientRect();const ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1),camera);const partHit=ray.intersectObjects(meshes.filter(m=>m.visible),false)[0], environmentHit=environment.pick(ray);if(environmentHit&&(!partHit||environmentHit.distance<partHit.distance))inspectEnvironment(environmentHit.entry.asset.id);else select(partHit?.object);});
$('search').oninput=renderList;for(const id of ['dims','ghost','explode'])$(id).onchange=applyDisplay;
$('reset').onclick=()=>{visibility.clear();$('assemblies').querySelectorAll('input').forEach(i=>i.checked=true);applyDisplay();};
$('fit').onclick=()=>{clearShow();setView();};document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>setView(b.dataset.view,bounds(),true));
$('notesbutton').onclick=()=>{ $('projectmenu').open=false; $('notes').showModal(); };$('closenotes').onclick=()=>$('notes').close();
// Keep occasional tools off the canvas until requested.
function setModelPanel(open) {
 $('modelpanel').hidden = !open;
 $('modeltoggle').setAttribute('aria-expanded', String(open));
}
$('modeltoggle').onclick=()=>{setModelPanel($('modelpanel').hidden); $('viewmenu').open=false;};
$('closemodel').onclick=()=>{setModelPanel(false); $('modeltoggle').focus();};
$('closeinspector').onclick=()=>{select(null); $('modeltoggle').focus();};
function showPage(id) {
 const page = ['materials-section','validation','review','costs'].includes(id) ? id : 'workspace';
 $('workspace').hidden = page !== 'workspace';
 $('reports').hidden = page === 'workspace';
 document.querySelectorAll('#reports > .materials').forEach(section=>section.hidden=section.id!==page);
 document.querySelectorAll('[data-page]').forEach(link=>{
  if(link.dataset.page===page) link.setAttribute('aria-current','page');
  else link.removeAttribute('aria-current');
 });
 $('projectmenu').open=false;
 $('viewmenu').open=false;
 $('reports').scrollTop=0;
}
function showWorkspace() {
 if($('workspace').hidden) {
  history.pushState(null, '', '#workspace');
  showPage('workspace');
 }
}
for(const id of ['viewmenu','projectmenu']) {
 $(id).addEventListener('toggle',()=>{
  if($(id).open) $(id==='viewmenu'?'projectmenu':'viewmenu').open=false;
 });
}
document.addEventListener('pointerdown',event=>{
 for(const id of ['viewmenu','projectmenu']) if(!$(id).contains(event.target)) $(id).open=false;
});
document.addEventListener('keydown',event=>{
 if(event.key!=='Escape' || document.querySelector('dialog[open]')) return;
 for(const id of ['viewmenu','projectmenu']) if($(id).open) {$(id).open=false; $(id).querySelector('summary').focus(); return;}
 if(!$('inspectorpanel').hidden) {select(null); $('modeltoggle').focus();}
 else if(!$('modelpanel').hidden) {setModelPanel(false); $('modeltoggle').focus();}
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
   $('error').hidden=true;$('connection').textContent=`Live model · ${data.revision.slice(0,6)}`;
   return data;
  } catch (error) {
   $('error').hidden=false;$('error').textContent=`${model?'Keeping last good model.':'Unable to load model.'} ${error.message}`;
   $('connection').textContent='Model needs attention';
   throw error;
  } finally { modelRequest = null; }
 })();
 return modelRequest;
}
async function refresh(){try{await loadModel();}catch{}finally{setTimeout(refresh,2000);}}

function animate(){requestAnimationFrame(animate);if(!camera)return;controls.update();buildAnimation.update(performance.now());for(const l of labels){const p=l.point.clone().project(camera);const a=l.start.clone().project(camera),b=l.end.clone().project(camera);l.el.hidden=p.z< -1||p.z>1||Math.hypot((a.x-b.x)*viewport.clientWidth,(a.y-b.y)*viewport.clientHeight)<12;l.el.style.left=`${Math.max(65,Math.min(viewport.clientWidth-65,(p.x*.5+.5)*viewport.clientWidth))}px`;l.el.style.top=`${(-p.y*.5+.5)*viewport.clientHeight}px`;}renderer.render(scene,camera);}animate();refresh();
// Small read-only diagnostics surface for automated verification.
window.stud=window.clubhouse={get model(){return model},get selected(){return selected?.userData.id},get visibleCount(){return meshes.filter(m=>m.visible).length},get view(){return currentView}};

let comments=[],drafts=new Map(),draftPart=null,pending=false,requestIds=new Map();
function rememberDraft(){if(draftPart)drafts.set(draftPart,$('commenttext').value);}
function renderPartComments(){
 const id=selected?.userData.id;draftPart=id||null;
 $('commentform').hidden=!id;$('commenthint').hidden=!!id;
 const value=id?(drafts.get(id)||''):'';if($('commenttext').value!==value)$('commenttext').value=value;
 $('partcommentlist').innerHTML=comments.filter(c=>c.part_id===id).map(c=>`<article class="comment"><p>${escape(c.text)}</p><small>${c.resolved?'Resolved':'Open'} · ${escape(new Date(c.created_at).toLocaleString())}</small></article>`).join('');
}
function renderComments(){
 $('commentcount').textContent=comments.filter(c=>!c.resolved).length+' open';
 $('allcomments').innerHTML=comments.map(c=>{
  const area=c.kind==='area';
  const subject=area?`<button class="areathumbnail" data-area-id="${escape(c.id)}"><img loading="lazy" src="/api/comment-images/${encodeURIComponent(c.id)}" alt="Area screenshot"><span>View screenshot ↗</span></button>`:`<button data-comment-part="${escape(c.part_id)}" class="commentpart">${escape(c.part_id)} ↗</button>`;
  const removed=!area&&model&&!model.parts.some(p=>p.id===c.part_id);
  return `<article class="comment">${subject}<p>${escape(c.text)}</p><small>${escape(new Date(c.created_at).toLocaleString())} · ${c.resolved?'Resolved':'Open'}${area?` · Screenshot of model ${escape(c.revision)}`:''}${removed?' · Part removed from current model':''}</small><button class="resolve" data-comment-id="${escape(c.id)}">${c.resolved?'Reopen':'Resolve'}</button></article>`;
 }).join('')||'<p class="sub">No comments yet. Select a part or capture an area to get started.</p>';
 $('allcomments').querySelectorAll('[data-area-id]').forEach(button=>button.onclick=()=>{
  const comment=comments.find(c=>c.id===button.dataset.areaId);
  $('savedareaimage').src=`/api/comment-images/${encodeURIComponent(comment.id)}`;
  $('savedareatext').textContent=comment.text;$('areaimageview').showModal();
 });
 $('allcomments').querySelectorAll('[data-comment-part]').forEach(b=>b.onclick=()=>{const m=meshes.find(m=>m.userData.id===b.dataset.commentPart);if(!m)return;visibility.set(m.userData.assembly,true);const check=[...$('assemblies').querySelectorAll('input')].find(i=>i.dataset.assembly===m.userData.assembly);if(check)check.checked=true;applyDisplay();showWorkspace();select(m);$('partcomments').scrollIntoView({behavior:'smooth',block:'center'});});
 $('allcomments').querySelectorAll('[data-comment-id]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{const c=comments.find(c=>c.id===b.dataset.commentId);await commentRequest({action:'resolve',id:c.id,resolved:!c.resolved});}catch(e){$('commentstatus').textContent=e.message;b.disabled=false;}});
 rememberDraft();renderPartComments();
}
async function commentRequest(payload){
 const r=await fetch('/api/comments',{method:payload?'POST':'GET',headers:payload?{'Content-Type':'application/json'}:{},body:payload?JSON.stringify(payload):undefined,cache:'no-store',signal:AbortSignal.timeout(10000)});
 const d=await r.json();if(!r.ok)throw new Error(d.error||'Comments unavailable');comments=d.comments;renderComments();
}
$('commenttext').addEventListener('input',()=>{if(draftPart){drafts.set(draftPart,$('commenttext').value);requestIds.delete(draftPart);}});
$('commentform').onsubmit=async e=>{
 e.preventDefault();if(pending||!draftPart)return;
 const part=draftPart,text=$('commenttext').value.trim();if(!text){$('commentstatus').textContent='Enter a comment first.';return;}
 const id=requestIds.get(part)||crypto.randomUUID();requestIds.set(part,id);pending=true;$('savecomment').disabled=true;$('commentstatus').textContent='Saving…';
 try{await commentRequest({action:'add',id,part_id:part,text});if((drafts.get(part)||'').trim()===text){drafts.delete(part);requestIds.delete(part);if(draftPart===part)$('commenttext').value='';}renderPartComments();$('commentstatus').textContent='Saved. Tell Codex: “Read my part comments.”';}
 catch(e){$('commentstatus').textContent='Not confirmed saved: '+e.message+' Your draft is kept; retry to confirm.';}
 finally{pending=false;$('savecomment').disabled=false;}
};
async function refreshComments(){try{if(!pending)await commentRequest();}catch(e){$('commentstatus').textContent='Comments unavailable: '+e.message;}finally{setTimeout(refreshComments,5000);}}
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
 showWorkspace();
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
function renderValidation(report){
 validationReport=report;
 const counts={PASS:0,FAIL:0,WARNING:0,UNVERIFIED:0};
 for(const f of report.findings||[])counts[f.status]=(counts[f.status]||0)+1;
 $('validationsummary').textContent=`${counts.FAIL} failed · ${counts.WARNING} warnings · ${counts.UNVERIFIED} unverified · ${counts.PASS} passed`;
 const same=report.revision===revision;
 $('validationstate').textContent=report.build_error?'Build needs attention. The viewer retains the last good model; these findings may describe a newer edit.':same?`Checks for model ${revision.slice(0,6)}.`:'Checks belong to another model revision. Highlighting is disabled.';
 const c=report.coverage;
 $('validationcoverage').innerHTML=c?(c.assemblies||[]).map(a=>`<tr><td>${escape(a.name)}</td><td>${a.checked_parts}/${a.total_parts}</td>${['collisions','support','alignment','openings','stock'].map(k=>`<td>${a.categories[k]||0}/${a.total_parts}</td>`).join('')}</tr>`).join(''):'';
 const requirements=c?.requirements||[];
 $('requirementdetails').hidden=!requirements.length;
 $('requirementsummary').textContent=`Declared requirements: ${requirements.filter(r=>r.status==='PASS').length}/${requirements.length} passed`;
 $('validationrequirements').innerHTML=requirements.map(r=>`<tr><td>${escape(r.component)}</td><td>${escape(r.label)}</td><td>${escape(r.status)}</td></tr>`).join('');
 const filter=$('validationfilter').value;
 const priority={FAIL:0,WARNING:1,UNVERIFIED:2,PASS:3};
 const findings=(report.findings||[]).filter(f=>filter==='issues'?f.status!=='PASS':f.status===filter).sort((a,b)=>priority[a.status]-priority[b.status]);
 $('validationfindings').innerHTML=findings.length?findings.map((f,i)=>`<article class="validationfinding ${f.status.toLowerCase()}"><div><strong>${escape(f.status)}</strong> <span>${escape(f.rule)}</span></div><p>${escape(f.message)}</p><small>${escape(f.parts.length>6?f.parts.slice(0,6).join(', ')+` and ${f.parts.length-6} more`:f.parts.join(', '))}</small>${f.parts.length?`<button data-finding="${i}" ${same?'':'disabled'}>Highlight parts</button>`:''}</article>`).join(''):'<p>No findings in this category.</p>';
 $('validationfindings').querySelectorAll('[data-finding]').forEach(b=>b.onclick=()=>showValidationFinding(findings[Number(b.dataset.finding)]));
}
$('validationfilter').onchange=()=>{if(validationReport)renderValidation(validationReport);};
$('clearvalidation').onclick=clearValidationHighlights;
async function refreshValidation(){
 try{
  const response=await fetch('/api/validation',{cache:'no-store',signal:AbortSignal.timeout(25000)});
  if(!response.ok)throw new Error(`HTTP ${response.status}`);
  const report=await response.json(),signature=JSON.stringify(report)+revision;
  if(signature!==validationSignature){validationSignature=signature;clearValidationHighlights();renderValidation(report);}
 }catch(e){$('validationstate').textContent='Latest checks unavailable: '+e.message;}
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
 return {canvas:snapshotViewer(renderer.domElement,labelRoot),revision};
},save:commentRequest});
