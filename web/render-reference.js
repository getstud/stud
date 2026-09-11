// Geometry references are conversation inputs, not a replacement viewer mode.
const fail=(code,message)=>Object.assign(new Error(message),{code});
export const renderReferenceSchema={type:'object',properties:{
 expected_revision:{type:'string',minLength:1,description:'The displayed revision returned by show or viewer context. Capture refuses a different revision.'},
 finishes:{type:'string',maxLength:4000,description:'Surface/finish descriptions for this design. Change modeled materials in the project first; this text only guides image generation.'},
 lighting:{type:'string',maxLength:1000,description:'Requested illumination. Defaults to soft neutral daylight.'},
},required:['expected_revision'],additionalProperties:false};

export function renderBrief(model,partIds,camera,input){
 if(!model.cad)throw fail('UNSUPPORTED_MODEL','A CadQuery model is required for a render reference.');
 const parts=model.parts.filter(part=>partIds.includes(part.id));
 const assignments=new Map();
 for(const part of parts){
  const id=part.stock,stock=model.stocks[id];
  // Material demands belong to object IDs, even when the product ID is shared.
  const specifications=part.material_specifications??[];
  const key=JSON.stringify([id,specifications]);
  if(!assignments.has(key))assignments.set(key,{id,name:stock?.name||id,specifications,parts:[]});
  assignments.get(key).parts.push({id:part.id,name:part.name,assembly:part.assembly,color:part.color||stock?.color});
 }
 const materials=[...assignments.values()];
 const lighting=input.lighting||'Soft neutral daylight, gentle shadows, realistic material response.';
 const finishes=input.finishes||'Use the specified design materials; keep unspecified finishes neutral and identify any assumptions.';
 const prompt=[
  'Use case: sketch-to-render',
  'Create a realistic high-resolution visualization of the stud design from the attached untextured geometry reference.',
  'Image 1 is the authoritative geometry and camera reference. Preserve its silhouette, proportions, dimensions, openings, part count, joints, roof pitch, placement and exact viewpoint, framing and projection. Keep the same image aspect ratio.',
  `Camera: ${camera.projection||'reference'} projection, ${camera.view||'current'} view. An orthographic reference must retain parallel lines and its flat projection; reveal only surfaces visible in the reference.`,
  `Design: ${model.name}.`,
  ...materials.map(material=>`Material ${material.name} (${material.id}): ${JSON.stringify(material.specifications)}. Applies to ${[...new Set(material.parts.map(part=>`${part.assembly}: ${part.name}`))].join('; ')}.`),
  `Finishes: ${finishes}`,
  `Lighting: ${lighting}`,
  'Backdrop: plain neutral studio background. Only the design is the subject; preserve visible construction details and openings. No added landscaping, furnishings, props, people, text, dimensions, interface, watermark or surroundings photo.',
  'Apply appearance to existing surfaces. Do not add, remove, move, resize or redesign geometry. A realistic visualization is an appearance study; the 3D design remains the dimensional authority.',
  'Respect omissions in the reference: do not invent corner boards, extra trim, hardware, frame subdivisions or structural parts. Material grain and surface seams may enrich existing faces only.',
 ].join('\n');
 return {schema_version:1,kind:'stud-render-reference',project_name:model.name,revision:model.revision,
  displayed:structuredClone(model.cad),
  camera:structuredClone(camera),geometry_units:'in',visible_part_ids:partIds,
  hidden_part_ids:model.parts.filter(part=>!partIds.includes(part.id)).map(part=>part.id),
  materials:structuredClone(materials),finishes,lighting,prompt};
}

// Separate scene + cloned camera: no overlay/material/camera state to restore,
// even when rendering fails. Shared mesh buffers remain owned by the live viewer.
export function assertAssembledMeshes(meshes){
 // Paused tours may leave positions between endpoints after the exploded
 // checkbox has already changed. Inspect geometry, not just that checkbox.
 if(meshes.some(mesh=>mesh.userData.basePosition&&mesh.position.distanceToSquared(mesh.userData.basePosition)>1e-12))
  throw fail('ASSEMBLED_VIEW_REQUIRED','Parts are still displaced by a presentation. Use viewer reset or show to restore the assembled design before capturing.');
}

export function captureUntextured({THREE,meshes,camera,width,height,createRenderer=options=>new THREE.WebGLRenderer(options)}){
 const scene=new THREE.Scene(),material=new THREE.MeshStandardMaterial({color:'#999999',roughness:1,metalness:0,side:THREE.DoubleSide});
 const edgeMaterial=new THREE.LineBasicMaterial({color:'#333333',transparent:true,opacity:.2}),edges=[];
 let renderer;
 try{
  scene.background=new THREE.Color('#f3f3f3');
  scene.add(new THREE.HemisphereLight('#ffffff','#777777',1.4));
  const light=new THREE.DirectionalLight('#ffffff',2.2);light.position.copy(camera.position);scene.add(light);
  for(const source of meshes){
   source.updateWorldMatrix(true,false);
   const mesh=new THREE.Mesh(source.geometry,material);
   mesh.matrixAutoUpdate=false;mesh.matrix.copy(source.matrixWorld);scene.add(mesh);
   // Neutral physical edges retain thin trim/openings in a single-color view.
   // Rebuild these from geometry; never copy inspection/validation helpers.
   const geometry=new THREE.EdgesGeometry(source.geometry);edges.push(geometry);
   const outline=new THREE.LineSegments(geometry,edgeMaterial);
   outline.matrixAutoUpdate=false;outline.matrix.copy(source.matrixWorld);scene.add(outline);
  }
  renderer=createRenderer({antialias:true,alpha:false,logarithmicDepthBuffer:true});
  renderer.setPixelRatio(1);renderer.setSize(width,height,false);renderer.outputColorSpace=THREE.SRGBColorSpace;
  renderer.render(scene,camera.clone());
  return renderer.domElement.toDataURL('image/png');
 }finally{for(const geometry of edges)geometry.dispose();edgeMaterial.dispose();material.dispose();renderer?.dispose();renderer?.forceContextLoss();}
}

export function createRenderReferenceTool({readViewer,capture,save=saveRenderReference}){
 return {name:'capture_render_reference',
  description:'Capture an untextured PNG of the displayed stud design at its current viewpoint for realistic image generation in the conversation. Use show or camera tools first for another viewpoint. Returns local reference and brief paths plus the image-generation prompt, materials and displayed version. Preserves the interactive viewer, visibility and editing target. For a combined request such as “show me how this would look with cedar siding”, first edit the design material, explicitly evaluate the current source, inspect and finish it, display that completed build, then capture it. This tool prepares the reference; call the available image-generation tool with it and present the generated image directly in chat.',
  inputSchema:renderReferenceSchema,annotations:{readOnlyHint:false},
  execute:async(input={}, {signal}={})=>{
   try{
    if(!input||typeof input!=='object'||Array.isArray(input)||Object.keys(input).some(key=>!Object.hasOwn(renderReferenceSchema.properties,key))||
      typeof input.expected_revision!=='string'||!input.expected_revision.trim()||
      ['finishes','lighting'].some(key=>key in input&&(typeof input[key]!=='string'||input[key].length>renderReferenceSchema.properties[key].maxLength)))throw fail('INVALID_INPUT','Provide the displayed expected_revision and optional finishes/lighting text.');
    signal?.throwIfAborted();
    const viewer=readViewer(),model=viewer.model,cad=model?.cad;
    if(!model?.parts?.length||!viewer.camera)throw fail('MODEL_UNAVAILABLE','Load a design before capturing a reference.');
    if(model.revision!==input.expected_revision)throw fail('REVISION_CONFLICT',`The displayed revision is ${model.revision}. Inspect it before capturing.`);
    if(viewer.busy)throw fail('VIEWER_BUSY','Wait for the current display operation or close its dialog before capturing.');
    if(viewer.exploded||viewer.assemblyReview)throw fail('ASSEMBLED_VIEW_REQUIRED','Use show to display the assembled design before capturing its finished appearance.');
    if(viewer.loadFailed||cad&&(cad.completion?.geometry!=='complete'||cad.presentation==='live'&&(cad.latest_build_id!==cad.build_id||cad.latest_status!=='complete')))throw fail('BUILD_NOT_READY','The current design has not finished loading successfully. Display the intended complete build before capturing.');
    const ids=viewer.visible_part_ids;
    if(!ids?.length)throw fail('EMPTY_VIEW','Show at least one design part before capturing.');
    const brief=renderBrief(model,ids,viewer.camera,input);
    // Capture synchronously binds the pixels and brief to one displayed frame.
    const image=capture();
    signal?.throwIfAborted();
    const saved=await save({image,brief},{signal});
    signal?.throwIfAborted();
    return {ok:true,...saved,brief,
     next:'Inspect reference_path, then call the available image-generation tool with that PNG as the geometry reference and brief.prompt. Present the generated image directly in chat, assess geometry/proportions/viewpoint/material fidelity, and keep the viewer available. Capture again for a new viewpoint.'};
   }catch(error){return {ok:false,error:{code:signal?.aborted?'CANCELED':error.code||'CAPTURE_FAILED',message:error.message}};}
  }};
}

async function saveRenderReference(payload,{signal}={}){
 const response=await fetch('/api/render-references',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:signal?AbortSignal.any([signal,AbortSignal.timeout(30000)]):AbortSignal.timeout(30000)});
 const data=await response.json();
 if(!response.ok)throw new Error(data.error?.message||data.error||'Could not save the render reference.');
 return data;
}
