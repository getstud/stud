import * as THREE from 'three';
import {createSequencePlayer} from './sequence-player.js';
import {request,versionOperation,command,waitJob,packetLinks} from './project-operations.js';

const fail=(message,code='INVALID_TARGET')=>{throw Object.assign(new Error(message),{code});};
const vector=p=>new THREE.Vector3(p[0],p[2],-p[1]);
const point=v=>[v.x,-v.z,v.y];
// Presentation operations act on the installed scene, never a newly fetched model
// that the user has not seen. Native writes retain their existing server guards.
export function createViewerOperations(a){
 const past=[];let editing=null;
 function ensure(){if(!a.model||!a.camera)fail('No displayed model is available.','MODEL_UNAVAILABLE');}
 function cameraState(){const c=a.camera;return c?{view:a.view,position:c.position.toArray(),quaternion:c.quaternion.toArray(),up:c.up.toArray(),target:a.controls.target?.toArray(),zoom:c.zoom,projection:c.isPerspectiveCamera?'perspective':'orthographic',fov:c.fov,aspect:c.aspect,left:c.left,right:c.right,top:c.top,bottom:c.bottom,near:c.near,far:c.far,view_offset:c.view?{...c.view}:null,units:'viewer inches: X right, Y up, Z toward front'}:null;}
 function context(){return {model_revision:a.model?.revision,project_name:a.model?.name,displayed_version:a.model?.cad||null,editing_target:editing,page:a.page,camera:cameraState(),framed_region:a.framedRegion,visible_part_ids:a.meshes.filter(m=>m.visible).map(m=>m.userData.id),selected_part_id:a.selected?.userData.id||null,highlighted_part_ids:a.highlights(),exploded:a.exploded,dimensions:a.dimensions,environment_enabled:a.environmentEnabled,assembly_drawing:a.drawing?{assembly:a.drawing.assembly,view:a.drawing.view,level:a.drawing.level}:null,environment:[...a.environment.entries].map(([id,e])=>({id,name:e.asset.name,visible:a.environment.isVisible(e),error:e.error||null})),comparison:a.page==='design-versions'?a.versions?.comparisonContext():null,comparison_selected_part_id:a.page==='design-versions'?a.versions?.comparisonSelection:null,units:'in',display_units:a.model?.display_units||'in'};}
 function targets(input){
  ensure();let ids=input.part_ids||[];
  if(input.assemblies){const known=new Set(a.meshes.map(m=>m.userData.assembly));const missing=input.assemblies.filter(n=>!known.has(n));if(missing.length)fail(`Unknown assemblies: ${missing.join(', ')}`);ids=[...ids,...a.meshes.filter(m=>input.assemblies.includes(m.userData.assembly)).map(m=>m.userData.id)];}
  if(!ids.length){if(a.selected)ids=[a.selected.userData.id];else fail('No part is selected. Read viewer_context, highlight candidates and clarify the reference.','AMBIGUOUS_REFERENCE');}
  const missing=ids.filter(id=>!a.meshes.some(m=>m.userData.id===id));if(missing.length)fail(`Unknown parts: ${missing.join(', ')}`,'PART_NOT_FOUND');
  return a.meshes.filter(m=>ids.includes(m.userData.id));
 }
 function measurement(mesh){const r=a.measurement(mesh),p=r.part;return {id:p.id,label:a.label(p),assembly:p.assembly,stock:p.stock,dimensions:p.size,blank_size:p.blank_size,cut:r.spec,cut_length:p.cut_length,operations:p.cad?.operations||[],operation_units:p.cad?.units||'in',profile:p.profile,outline:p.outline,seats:p.seats,origin:p.origin,rotation:p.rotation,bounds:{min:point(new THREE.Vector3(r.box.min.x,r.box.min.y,r.box.max.z)),max:point(new THREE.Vector3(r.box.max.x,r.box.max.y,r.box.min.z))},mounting:{reference:'lowest point of the entire design, including hidden parts',design_base:a.designBase(),height:r.box.min.y-a.designBase(),edge:r.flatBottom?'bottom edge':'lowest point'},units:'in',note:p.note};}
 function snapshot(){
  const drawing=a.drawing;
  return {revision:a.model.revision,camera:cameraState(),visibility:[...a.visibility],hidden:[...a.hiddenParts],explode:a.exploded,dimensions:a.dimensions,selected:a.selected?.userData.id,highlighted:a.highlights(),grid:a.gridVisible,
   drawing:drawing?{assembly:drawing.assembly,view:drawing.view,level:drawing.level}:null,
   drawingReturn:drawing?{visibility:[...drawing.visibility],hidden:[...drawing.hiddenParts],explode:drawing.explode,dimensions:drawing.dimensions,grid:drawing.grid}:null,
   environmentEnabled:a.environmentEnabled,environment:[...a.environment.entries].map(([id])=>[id,a.environment.visibilityFor(id)])};
 }
 function remember(){past.push(snapshot());if(past.length>30)past.shift();}
 function restoreCamera(s){if(a.view!==s.view)a.setView(s.view);const c=a.camera;c.position.fromArray(s.position);c.up.fromArray(s.up);c.quaternion.fromArray(s.quaternion);c.zoom=s.zoom;for(const k of ['fov','aspect','left','right','top','bottom','near','far'])if(s[k]!==undefined)c[k]=s[k];c.view=s.view_offset?{...s.view_offset}:null;c.updateProjectionMatrix();if(s.target&&a.controls.target)a.controls.target.fromArray(s.target);a.controls.update();c.position.fromArray(s.position);c.quaternion.fromArray(s.quaternion);}
 function restore(s){
  if(s.revision!==a.model.revision)fail('This view belongs to a different displayed revision. Inspect that version before returning to the saved view.','REVISION_CONFLICT');
  a.endDrawing(false);const base=s.drawingReturn||s;
  a.visibility.clear();base.visibility.forEach(([k,v])=>a.visibility.set(k,v));a.hiddenParts.clear();base.hidden.forEach(id=>a.hiddenParts.add(id));a.exploded=base.explode;a.dimensions=base.dimensions;a.gridVisible=base.grid;
  a.setEnvironmentEnabled(s.environmentEnabled);s.environment.forEach(([id,v])=>a.environment.setVisible(id,v));
  a.applyDisplay();if(s.drawing){a.openDrawing(s.drawing.assembly,s.drawing.view,s.drawing.level);a.dimensions=s.dimensions;a.applyDisplay();}
  a.select(a.meshes.find(m=>m.userData.id===s.selected&&m.visible));a.highlight(a.meshes.filter(m=>s.highlighted.includes(m.userData.id)));restoreCamera(s.camera);

 }
 // Prepared scene snapshots keep replay deterministic and geometry tied to a revision.
 function captureSequence(){return {...snapshot(),meshes:a.meshes.map(m=>({id:m.userData.id,position:m.position.toArray(),visible:m.visible,opacity:m.material.opacity}))};}
 let blendEnd=null,blendStart=null,blendCamera=null;
 function restoreSequence(s){restore(s);for(const item of s.meshes){const m=a.meshes.find(m=>m.userData.id===item.id);m.position.fromArray(item.position);m.visible=item.visible;m.material.opacity=item.opacity;m.material.transparent=item.opacity<1;m.material.depthWrite=item.opacity===1;}blendEnd=null;blendStart=null;a.updateHighlights?.();a.render();}
 function blendSequence(start,end,t){
  if(blendEnd!==end||blendStart!==start){
   restoreSequence(end);blendEnd=end;blendStart=start;blendCamera={...start.camera};
   if(start.camera.projection==='orthographic'){
    const target=new THREE.Vector3().fromArray(start.camera.target||end.camera.target),position=new THREE.Vector3().fromArray(start.camera.position);
    const height=(start.camera.top-start.camera.bottom)/start.camera.zoom,depth=height/(2*Math.tan(end.camera.fov*Math.PI/360));
    blendCamera.position=position.sub(target).normalize().multiplyScalar(depth).add(target).toArray();blendCamera.zoom=1;
   }
  }
  const c=a.camera,cs=blendCamera,ce=end.camera;
  c.position.fromArray(cs.position).lerp(new THREE.Vector3().fromArray(ce.position),t);
  const target=new THREE.Vector3().fromArray(cs.target||ce.target).lerp(new THREE.Vector3().fromArray(ce.target),t);
  c.up.fromArray(cs.up).lerp(new THREE.Vector3().fromArray(ce.up),t).normalize();
  // Opposite up vectors need a stable midpoint rather than a zero vector.
  if(c.up.lengthSq()<.01)c.up.fromArray(ce.up);
  c.zoom=cs.zoom+(ce.zoom-cs.zoom)*t;c.updateProjectionMatrix();a.controls.target?.copy(target);c.lookAt(target);
  for(let i=0;i<end.meshes.length;i++){
   const item=end.meshes[i],old=start.meshes[i],m=a.meshes[i];
   m.position.fromArray(old.position).lerp(new THREE.Vector3().fromArray(item.position),t);
   const opacity=(old.visible?old.opacity:0)*(1-t)+(item.visible?item.opacity:0)*t;
   m.visible=opacity>0;m.material.opacity=opacity;m.material.transparent=opacity<1;m.material.depthWrite=opacity===1;
   for(const edge of m.children)if(edge.isLineSegments)edge.material.opacity=.24*opacity;
  }
  a.updateHighlights?.();a.render();
 }
 function compileSequence(input){
  ensure();a.assertAvailable();
  if(a.view!=='perspective')fail('Switch to perspective before preparing a presentation.','UNSUPPORTED_VIEW');
  const reduced=a.sequenceReducedMotion?.()===true;
  const total=input.steps.reduce((sum,s)=>sum+(reduced?0:s.duration??2)+(s.hold??2),0);
  if(total>180)fail('Presentations must last at most 180 seconds.');
  for(const step of input.steps)for(const field of ['part_ids','hide','reveal','highlight'])if(step[field])targets({part_ids:step[field]});
  const start=captureSequence(),steps=[];
  try{
   for(const step of input.steps){
    a.endDrawing(false);
    if(step.reset){a.visibility.clear();a.hiddenParts.clear();a.exploded=false;a.select(null);a.highlight([]);}
    if(step.explode!==undefined)a.exploded=step.explode;
    for(const id of step.hide||[])a.hiddenParts.add(id);
    for(const id of step.reveal||[]){const m=a.meshes.find(m=>m.userData.id===id);a.hiddenParts.delete(id);a.visibility.set(m.userData.assembly,true);}
    a.applyDisplay();
    if(step.highlight)a.highlight(targets({part_ids:step.highlight}));else a.highlight([]);
    const subject=step.part_ids?targets(step):a.meshes.filter(m=>m.visible);
    if(!subject.length||subject.some(m=>!m.visible))fail(`Step “${step.label}” needs visible subjects. Reveal them first.`);
    const box=new THREE.Box3();for(const m of subject){m.updateMatrixWorld(true);box.expandByObject(m);}
    const center=box.getCenter(new THREE.Vector3()),radius=Math.max(box.getSize(new THREE.Vector3()).length()/2,1);
    const directions={overview:[1,.65,1.3],detail:[.7,.4,1],front:[0,.05,1],side:[1,.05,0],top:[0,1,.001]};
    const c=a.camera,angle=Math.min(c.fov*Math.PI/360,Math.atan(Math.tan(c.fov*Math.PI/360)*c.aspect));
    c.zoom=1;c.position.copy(center).add(new THREE.Vector3(...directions[step.view||'overview']).normalize().multiplyScalar(radius/Math.sin(angle)*1.2));
    c.up.set(0,1,0);a.controls.target.copy(center);c.lookAt(center);c.updateProjectionMatrix();
    steps.push({...step,duration:reduced?0:step.duration??2,hold:step.hold??2,end:captureSequence()});
   }
  }finally{restoreSequence(start);}
  return {title:input.title,reducedMotion:reduced,revision:a.model.revision,duration:total,start,steps};
 }
 const sequence=createSequencePlayer({revision:()=>a.model?.revision,compile:compileSequence,capture:captureSequence,restore:restoreSequence,blend:blendSequence,
  activity:operation=>a.sequenceActivity?a.sequenceActivity(operation):operation(),onChange:state=>a.sequenceChanged?.(state),
  raf:callback=>requestAnimationFrame(callback),caf:frame=>cancelAnimationFrame(frame)});
 async function syncEditing(){if(a.model?.cad){const status=await request('/api/v1/status');editing={option:status.option,request:status.request,active_request:status.active_request,pending_records:status.pending_records};return status;}editing=null;return null;}
 async function readEstimate(){
  ensure();const before=a.model.revision,data=await a.priceRequest();
  if(a.model.revision!==before||data.build_id&&(data.build_id!==a.model.cad?.build_id||(data.view_checkpoint||null)!==(a.model.cad?.presentation==='history'?a.model.cad.checkpoint:null))||!data.build_id&&data.revision&&data.revision!==before)fail('The estimate and displayed design differ. Refresh the displayed context and retry.','REVISION_CONFLICT');
  a.renderPrices(data);return data;
 }
 const operations={
  sequence(input){const action=input.action;if(action==='stop'||action==='dismiss'){const state=sequence[action]();a.stopAll?.();return {sequence:state};}if(action==='prepare')return {sequence:sequence.prepare(input)};if(action==='status')return {sequence:sequence.state()};if(action==='next'||action==='previous')return {sequence:sequence.seek(action==='next'?1:-1)};return {sequence:sequence[action==='resume'?'play':action]()};},
  async viewer_context(input){ensure();await syncEditing();const q=input.query?.toLowerCase();return {exports:['parts','materials','costs'].map(kind=>({kind,url:new URL(`/api/${kind}.csv`,location.href).href,model_revision:a.model.revision,dynamic:true})),parts:a.meshes.filter(m=>(!input.visible_only||m.visible)&&(!q||`${m.userData.id} ${a.label(m.userData)} ${m.userData.assembly} ${m.userData.stock}`.toLowerCase().includes(q))).map(m=>({id:m.userData.id,label:a.label(m.userData),assembly:m.userData.assembly,stock:m.userData.stock,visible:m.visible,bounds:measurement(m).bounds})),materials:a.model.materials,capabilities:{versions:!!a.model.cad,plans:!!a.model.cad,saved_plan_sections:false}};},
  viewer(input){
   ensure();a.assertAvailable();const action=input.action;
   let parts;if(['hide','reveal','isolate','select','highlight'].includes(action))parts=targets(input);
   if(action==='select'&&parts.length!==1)fail('Select exactly one part. Use highlight for multiple candidates.');
   if(action==='drawing'&&!a.meshes.some(m=>m.userData.assembly===input.assembly))fail('Assembly not found.');
   if(action==='drawing'&&input.level!=null&&!a.meshes.some(m=>m.userData.assembly===input.assembly&&a.measurement(m).level===input.level))fail('Mounting level not found. Use the assembly parts’ absolute elevations.');
   if(['environment','inspect_environment'].includes(action)&&input.asset_id&&!a.environment.entries.has(input.asset_id))fail('Environment asset not found.');
   if(action==='page'&&input.page==='design-versions'&&!a.versions)fail('Versions require a CadQuery project.','UNSUPPORTED_CAPABILITY');
   remember();a.stop();if(action!=='page')a.showWorkspace();
   if(['hide','reveal','isolate','reset','explode','highlight'].includes(action))a.endDrawing(false);
   if(action==='reset'){a.visibility.clear();a.hiddenParts.clear();a.exploded=false;a.select(null);a.highlight([]);a.clearWarnings();a.setEnvironmentEnabled(true);for(const [id] of a.environment.entries)a.environment.setVisible(id,true);}
   if(action==='hide'){for(const name of input.assemblies||[])a.visibility.set(name,false);for(const m of parts)if(!input.assemblies?.includes(m.userData.assembly))a.hiddenParts.add(m.userData.id);}
   if(['reveal','select','highlight'].includes(action))for(const m of parts){a.visibility.set(m.userData.assembly,true);a.hiddenParts.delete(m.userData.id);}
   if(action==='isolate'){a.visibility.clear();a.hiddenParts.clear();for(const m of a.meshes){a.visibility.set(m.userData.assembly,parts.some(p=>p.userData.assembly===m.userData.assembly));if(!parts.includes(m))a.hiddenParts.add(m.userData.id);}}
   if(action==='explode')a.exploded=input.enabled;
   if(action==='dimensions')a.dimensions=input.enabled;
   if(action==='drawing'){a.openDrawing(input.assembly,input.view,input.level);}
   else a.applyDisplay();
   if(action==='select')a.selectPart(parts[0]);
   if(action==='highlight')a.highlight(parts);
   if(action==='environment'){if(input.asset_id)a.environment.setVisible(input.asset_id,input.enabled);else a.setEnvironmentEnabled(input.enabled);}
   if(action==='inspect_environment')a.inspectEnvironment(input.asset_id);
   if(action==='page')a.showPage(input.page);
   if(action==='parts_panel')a.setModelPanel(input.enabled,{focus:false});
   a.render();return {};
  },
  camera(input,{signal}={}){
   ensure();a.assertAvailable();const action=input.action;
   if(action==='back'&&!past.length)fail('No previous view is available.');
   if(action==='back'&&past.at(-1).revision!==a.model.revision)fail('The previous view belongs to a different displayed revision.','REVISION_CONFLICT');
   if(action==='zoom'&&!a.camera.isOrthographicCamera&&!a.controls.target)fail('Use move or a pose while flying.');
   if(action==='pose'&&(vector(input.position).distanceTo(vector(input.target))<.001||input.up&&vector(input.up).cross(vector(input.target).sub(vector(input.position))).length()<.001))fail('Camera position and target must differ, and up must be nonzero.');
   a.stop();a.showWorkspace();
   if(action==='stop')return {};
   if(action==='back'){const previous=past.at(-1);restore(previous);past.pop();a.render();return {};}
   remember();
   if(action==='fit'){a.endDrawing(false);a.clearShow();const box=a.bounds();if(input.environment)box.union(a.environment.bounds());a.setView(a.view,box);}
   if(action==='preset')a.setView(input.view,a.bounds(),true);
   if(action==='pose'){a.endDrawing(false);a.setView(input.view||'perspective');const c=a.camera;c.position.copy(vector(input.position));if(input.up)c.up.copy(vector(input.up).normalize());if(a.controls.target)a.controls.target.copy(vector(input.target));c.lookAt(vector(input.target));}
   if(action==='move'){
    const delta=vector(input.delta);
    if(input.duration>0){
     const camera=a.camera,controls=a.controls,start=camera.position.clone(),target=controls.target?.clone(),began=performance.now();
     return new Promise((resolve,reject)=>{
      let frame;const cancel=()=>{cancelAnimationFrame(frame);signal?.removeEventListener('abort',cancel);reject(signal.reason);};
      if(signal?.aborted){reject(signal.reason);return;}
      signal?.addEventListener('abort',cancel,{once:true});
      const step=now=>{
       const t=Math.min(1,(now-began)/(input.duration*1000)),ease=t*t*(3-2*t);
       camera.position.copy(start).addScaledVector(delta,ease);if(target)controls.target.copy(target).addScaledVector(delta,ease);
       controls.update();a.render();
       if(t<1)frame=requestAnimationFrame(step);else{signal?.removeEventListener('abort',cancel);resolve({});}
      };
      frame=requestAnimationFrame(step);
     });
    }
    a.camera.position.add(delta);a.controls.target?.add(delta);
   }
   if(action==='orbit'){if(!a.controls.target||a.view!=='perspective')a.setView('perspective',a.bounds(),true);const target=a.controls.target;a.camera.position.sub(target).applyAxisAngle(new THREE.Vector3(0,1,0),THREE.MathUtils.degToRad(input.degrees)).add(target);a.camera.lookAt(target);}
   if(action==='zoom'){if(a.camera.isOrthographicCamera){a.camera.zoom*=input.factor;a.camera.updateProjectionMatrix();}else if(a.controls.target)a.camera.position.sub(a.controls.target).divideScalar(input.factor).add(a.controls.target);else fail('Use move or a pose while flying.');}
   a.controls.update();a.render();return {};
  },
  inspect_parts(input){const parts=targets(input);if(input.show){a.assertAvailable();remember();a.stop();a.displayShow({part_ids:parts.map(m=>m.userData.id)});}return {parts:parts.map(measurement)};},
  checks(input){ensure();const report=a.validation;if(report?.revision!==a.model.revision)fail('Checks are unavailable for this displayed revision.','REVISION_CONFLICT');const findings=report.findings||[];
   if(input.action==='show'){const finding=input.rule?findings.find(f=>f.rule===input.rule):null;if(input.rule&&!finding)fail('Finding not found.');a.assertAvailable();a.stop();a.showWorkspace();a.showWarnings(findings.some(f=>f.status!=='PASS'&&(f.status!=='UNVERIFIED'||f.parts?.length>0)));if(finding)a.showFinding(finding);}
   if(input.action==='hide')a.showWarnings(false);
   return {report};
  },
  async estimate(input){const data=await readEstimate();if(input.action==='read')return {estimate:data};
   if(data.editable===false)fail('Return to the current design before editing estimate overrides.','HISTORICAL_READ_ONLY');
   if(a.hasPriceDrafts())fail('An estimate cell has an unsaved draft. Finish that edit before changing quotes through conversation.','UNSAVED_EDIT');
   const row=data.rows.find(r=>r.key===input.key);if(!row)fail('Estimate row not found.');
   const payload={key:row.key,client_key:crypto.randomUUID(),expected_estimate:input.expected_estimate||data.estimate_id,expected_build:data.build_id,expected_revision:a.model.revision};
   if(input.action==='set')Object.assign(payload,{kind:'manual',unit_price:input.unit_price,source:input.source||'Manual entry',observed_on:input.observed_on||new Date().toISOString().slice(0,10),note:input.note??row.quote?.note??'',url:input.url??row.quote?.url??'',...(input.quantity!==undefined?{quantity:input.quantity}:!a.model.cad?{quantity:row.quote?.quantity??null}:{})});
   else payload.action=input.action;
   const updated=await a.priceRequest(payload);a.renderPrices(updated);return {estimate:updated};
  },
  async versions(input,{signal}={}){ensure();if(input.action==='inspect'&&Boolean(input.checkpoint)===Boolean(input.option_id))fail('Specify one checkpoint or option_id.','INVALID_INPUT');if(!a.model.cad)fail('Versions require a CadQuery project.','UNSUPPORTED_CAPABILITY');
   if(input.action==='comparison_select'){a.assertAvailable();a.showPage('design-versions');return a.versions.selectComparison(input.part_id);}
   if(input.action==='comparison_camera'){a.assertAvailable();a.showPage('design-versions');return a.versions.moveComparison(input);}
   if(input.action==='list'){const result=await versionOperation(input);editing={option:result.status.option,request:result.status.request,active_request:result.status.active_request,pending_records:result.status.pending_records};return result;}
   a.assertAvailable();a.stop();const cameraBefore=cameraState();
   const result=input.action==='inspect'&&input.option_id&&a.optionComparison
    ?await a.optionComparison.switchOption(input.option_id,{signal}):await versionOperation(input);
   signal?.throwIfAborted();
   const warnings=[];
   try{
    if(input.action==='compare'){a.showPage('design-versions');await a.versions.displayComparison(result.result);}
    else if(['inspect','live','activate','restore'].includes(input.action)){await a.refreshModel();signal?.throwIfAborted();if(!a.model)fail('No model was displayed.');a.showWorkspace();restoreCamera(cameraBefore);a.render();}
   }catch(error){return {ok:false,error:{code:'DISPLAY_FAILED',message:`The version operation completed, but the viewer could not display it: ${error.message}. Refresh the view; do not repeat the completed mutation.`},completed_result:result};}
   try{await syncEditing();}catch(error){warnings.push(`Operation completed; editing context refresh failed: ${error.message}`);}
   try{await a.versions.refresh();}catch(error){warnings.push(`Operation completed; Versions table refresh failed: ${error.message}`);}
   return {result,warnings};
  },
  async plans(input,{signal}={}){ensure();if(!a.model.cad)fail('Plan generation requires a CadQuery project.','UNSUPPORTED_CAPABILITY');
   if(input.action==='list'){const packets=await request('/api/v1/exports');return {packets:packets.map(job=>({...job,downloads:packetLinks(job)}))};}
   const status=await syncEditing();const checkpoint=input.checkpoint||a.model.cad.checkpoint;
   if(!checkpoint)fail('The displayed draft has no saved checkpoint. Save the design first or choose an explicit checkpoint from versions.list.','CHECKPOINT_REQUIRED');
   // The build ID ties default generation to the geometry being discussed.
   signal?.throwIfAborted();
   const job=await waitJob(await command('plans',{checkpoint,...(!input.checkpoint?{build_id:a.model.cad.build_id}:{}),print_spec:{paper:input.paper||'letter',layout:input.layout||'compact'},estimate_mode:input.estimate_mode||'historical'}));
   signal?.throwIfAborted();
   const warnings=[];try{await a.versions.refresh();signal?.throwIfAborted();a.versions.presentPacket?.(job);}catch(error){warnings.push(`Packet saved; Versions table refresh failed: ${error.message}`);}
   return {packet:job,downloads:packetLinks(job),editing_option:status.option.id,warnings};
  }
 };
 return {operations,context,sequence};
}
