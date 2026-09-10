// WebMCP contracts are independent of DOM and transport. Application operations
// are injected so buttons and conversation use the same state and mutations.
const string={type:'string',minLength:1,maxLength:200};
const bool={type:'boolean'};
const number={type:'number'};
const point={type:'array',items:number,minItems:3,maxItems:3};
const ids={type:'array',items:string,minItems:1,maxItems:100,uniqueItems:true};
const choice=(...values)=>({type:'string',enum:values});
const object=(properties={},required=[])=>({type:'object',properties,required,additionalProperties:false});
const revision={expected_revision:string};
const actions=variants=>({oneOf:Object.entries(variants).map(([action,[properties={},required=[]]])=>object({action:{const:action},...revision,...properties},['action',...required]))});
export const viewerSchemas={
 viewer_context:object({query:string,visible_only:bool}),
 viewer:actions({hide:[{part_ids:ids,assemblies:ids}],reveal:[{part_ids:ids,assemblies:ids}],isolate:[{part_ids:ids,assemblies:ids}],reset:[],select:[{part_ids:ids},['part_ids']],highlight:[{part_ids:ids},['part_ids']],explode:[{enabled:bool},['enabled']],dimensions:[{enabled:bool},['enabled']],drawing:[{assembly:string,view:choice('front','side','top'),level:{oneOf:[number,{const:null}]}},['assembly','view']],environment:[{enabled:bool,asset_id:string},['enabled']],inspect_environment:[{asset_id:string},['asset_id']],page:[{page:choice('workspace','materials-section','costs','design-versions')},['page']],parts_panel:[{enabled:bool},['enabled']]}),
 camera:actions({preset:[{view:choice('perspective','firstperson','front','side','top')},['view']],fit:[{environment:bool}],pose:[{position:point,target:point,up:point,view:choice('perspective','firstperson','front','side','top')},['position','target']],move:[{delta:point,duration:{type:'number',minimum:0,maximum:20}},['delta']],orbit:[{degrees:{type:'number',minimum:-360,maximum:360}},['degrees']],zoom:[{factor:{type:'number',exclusiveMinimum:0,maximum:100}},['factor']],stop:[],back:[]}),
 inspect_parts:object({...revision,part_ids:ids,show:bool}),
 checks:actions({read:[],show:[{rule:string}],hide:[]}),
 estimate:actions({read:[],set:[{key:string,unit_price:{type:'number',minimum:0},quantity:{type:'integer',minimum:1},source:string,observed_on:string,note:{type:'string',maxLength:1000},url:{type:'string',maxLength:2000},expected_estimate:string},['key','unit_price']],clear_manual:[{key:string,expected_estimate:string},['key']],clear_quantity:[{key:string,expected_estimate:string},['key']]}),
 versions:actions({list:[],comparison_select:[{part_id:string},['part_id']],comparison_camera:[{position:point,target:point,zoom:{type:'number',exclusiveMinimum:0,maximum:100}},['position','target']],inspect:[{checkpoint:string,option_id:string}],live:[],activate:[{option_id:string,expected_head:string},['option_id','expected_head']],create:[{name:string,base_checkpoint:string},['name','base_checkpoint']],rename:[{option_id:string,name:string,option_revision:{type:'integer',minimum:0}},['option_id','name','option_revision']],restore:[{checkpoint:string,option_id:string,expected_head:string},['checkpoint','option_id','expected_head']],compare:[{left:string,right:string,mode:choice('historical','common_price')},['left','right']]}),
 plans:actions({list:[],generate:[{checkpoint:string,paper:choice('letter','a4'),layout:choice('compact','expanded'),estimate_mode:choice('historical','current')}]})
};
const sequenceStep=object({label:string,caption:{type:'string',maxLength:500},part_ids:ids,view:choice('overview','detail','front','side','top'),duration:{type:'number',minimum:0,maximum:20},hold:{type:'number',minimum:0,maximum:30},explode:bool,hide:ids,reveal:ids,highlight:ids,reset:bool},['label']);
viewerSchemas.sequence=actions({prepare:[{title:string,steps:{type:'array',minItems:1,maxItems:20,items:sequenceStep}},['title','steps']],play:[],pause:[],resume:[],replay:[],stop:[],next:[],previous:[],dismiss:[],status:[]});
export function validate(schema,value,path='input'){
 const fail=()=>{throw Object.assign(new Error(`Invalid ${path}. Check the tool's input schema.`),{code:'INVALID_INPUT'});};
 if(schema.oneOf){if(schema.oneOf.filter(s=>{try{validate(s,value,path);return true;}catch{return false;}}).length!==1)fail();return;}
 if('const' in schema&&value!==schema.const)fail();
 if(schema.enum&&!schema.enum.includes(value))fail();
 if(schema.type==='object'){
  if(!value||typeof value!=='object'||Array.isArray(value))fail();
  if((schema.required||[]).some(k=>!Object.hasOwn(value,k)))fail();
  for(const [key,entry] of Object.entries(value)){if(!Object.hasOwn(schema.properties,key))fail();validate(schema.properties[key],entry,`${path}.${key}`);}
 }else if(schema.type==='array'){
  if(!Array.isArray(value)||value.length<schema.minItems||value.length>schema.maxItems||schema.uniqueItems&&new Set(value).size!==value.length)fail();
  value.forEach((v,i)=>validate(schema.items,v,`${path}[${i}]`));
 }else if(schema.type==='number'||schema.type==='integer'){
  if(!Number.isFinite(value)||schema.type==='integer'&&!Number.isInteger(value)||value<schema.minimum||value>schema.maximum||value<=schema.exclusiveMinimum)fail();
 }else if(schema.type&&typeof value!==schema.type)fail();
 if(typeof value==='string'&&(value.length<(schema.minLength||0)||value.length>(schema.maxLength??Infinity)))fail();
}
const descriptions={
 sequence:'Prepare and play a guided presentation locally. prepare validates all exact part IDs and shows a ready card without starting playback. Steps frame the whole design or part_ids using perspective overview/detail/front/side/top angles; duration is transition seconds (default 2), hold is seconds (default 2). Scene changes reset, explode, hide, reveal and highlight animate together with the camera. Total at most 180 seconds. Use play only when asked to start, pause/resume/replay/stop/next/previous/status to control. A changed model requires preparing again. Camera commands pause playback.',
 viewer_context:'Read the actual displayed stud design, editing target, camera, visibility, selection and matching parts. Resolve natural references using this context; highlight candidates and ask the user when ambiguous. Coordinates and geometry measurements are inches, X width, Y depth, Z up, except explicitly labeled camera coordinates. Does not navigate or retarget editing.',
 viewer:'Control the shared stud viewer: hide/reveal/isolate exact parts or assemblies, highlight candidates, select a part, explode/reset, dimensions, assembly drawings and mounting levels, environment and pages. Omit targets only to use the selected part; ambiguity is an error. Drawing level is absolute model elevation in inches. Reset restores all geometry and exits exploded/drawing display. Does not edit the design.',
 camera:'Navigate stud hands-free. Presets, fit, exact pose, world-space move, orbit degrees around model Z, zoom factor (>1 zooms in), stop all motion or go back to the previous viewer action. Position/target/delta/up use model axes in inches (X width, Y depth, Z up). Back restores projection, camera, visibility and selection for the displayed revision within this viewer session. Does not change editing target.',
 inspect_parts:'Read displayed parts’ stock/finished dimensions, cut specifications, operations, profiles and mounting heights using the same measurements as the inspector. Defaults to the selected part; request exact IDs when ambiguous. show=true also reveals, frames and selects/highlights them. Never infer a finished cut from a shaped stock blank.',
 checks:'Read the displayed revision’s findings and coverage, show unresolved problems or highlight a specific rule with its explanation, or hide warnings. These are geometric checks, not a structural approval.',
 estimate:'Answer cost and material quantity questions directly in conversation from the displayed design’s estimate, including purchase sizes, units, stock allocation, missing prices and assumptions. Read does not navigate. set saves a manual unit price and optional quantity; clear_manual removes the price override; clear_quantity restores calculated quantity. Use an exact row key from read and optionally expected_estimate. Historical estimates cannot be edited.',
 versions:'List named options and checkpoints; inspect a checkpoint or an option while preserving the workspace camera and editing target; return live; compare two saved designs. comparison_select and comparison_camera operate the existing two-pane comparison (camera positions/targets in model inches, Z up). Activate explicitly chooses an editing option and requires its expected head. Restore saves old source as a NEW checkpoint on an explicitly named editing option. Create and rename reuse the Versions UI operations. Never activate merely to inspect or compare.',
 plans:'List saved plan packets or generate and deliver an immutable packet with plans PDF, cut/parts list and other exported files. Defaults to the displayed checkpoint; unsaved drafts require an explicit saved checkpoint. Returns downloadable URLs and completeness findings. Custom sections and saved print selections belong to issue #26.'
};
// One runner is shared by all feature-owned tools, including show and #19.
export function createViewerToolRunner({context,activity,before=()=>{}}){
 let queue=Promise.resolve(),epoch=0;
 const wrap=(tool,{readOnly=input=>tool.annotations?.readOnlyHint===true}={})=>({...tool,
  execute:(input={})=>{
   const queuedEpoch=epoch;
   const run=async()=>{
    try{
     if(queuedEpoch!==epoch)throw Object.assign(new Error('UI control stopped.'),{code:'CONTROL_STOPPED'});
     const operation=async signal=>{await before(tool.name,input,{readOnly:readOnly(input)});const result=await tool.execute(input,{signal});signal?.throwIfAborted();return {...result,context:context()};};
     return await (readOnly(input)?operation():activity(operation));
    }catch(error){return {ok:false,error:{code:error.code||'OPERATION_FAILED',message:error.message},context:context()};}
   };
   // Stop must not wait behind a slow plan job. All other tools run in order.
   if(tool.name==='camera'&&input?.action==='stop'||tool.name==='sequence'&&['pause','stop','dismiss'].includes(input?.action))return run();
   const result=queue.then(run);queue=result.catch(()=>{});return result;
  }
 });
 wrap.stop=()=>{epoch++;activity.stop?.();};
 return wrap;
}
export function createViewerTools({operations,context,activity,wrap=createViewerToolRunner({context,activity})}){
 return Object.entries(viewerSchemas).map(([name,inputSchema])=>{
  const readOnly=input=>name==='sequence'||name==='camera'&&input?.action==='stop'||name==='viewer_context'||['read','list'].includes(input?.action)||name==='inspect_parts'&&!input?.show;
  const tool={name,description:descriptions[name],inputSchema,annotations:{readOnlyHint:name==='viewer_context'},execute:async (input,{signal}={})=>{
   validate(inputSchema,input);
   if(input.expected_revision&&input.expected_revision!==context().model_revision)throw Object.assign(new Error('The displayed design changed. Read viewer_context again.'),{code:'REVISION_CONFLICT'});
   return {ok:true,...await operations[name](input,{signal})};
  }};
  const wrapped=wrap(tool,{readOnly});
  // Reject malformed calls before control begins. Context/revision guards run
  // again inside the shared queue, immediately before application operations.
  return {...wrapped,execute:(input={})=>{try{validate(inputSchema,input);}catch(error){return Promise.resolve({ok:false,error:{code:'INVALID_INPUT',message:error.message},context:context()});}return wrapped.execute(input);}};
 });
}
export function createControlActivity(setActive,paint=()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))){
 const active=new Set();
 const run=async operation=>{
  const controller=new AbortController();active.add(controller);
  try{if(active.size===1)setActive(true);await paint();controller.signal.throwIfAborted();return await operation(controller.signal);}
  finally{try{await paint();}finally{active.delete(controller);if(!active.size)setActive(false);}}
 };
 run.stop=()=>{
  for(const controller of active)controller.abort(Object.assign(new Error('UI control stopped.'),{code:'CONTROL_STOPPED'}));
  active.clear();setActive(false);
 };
 return run;
}
export async function registerViewerTools(context,tools){
 if(typeof context?.registerTool!=='function')return false;
 for(const tool of tools)await context.registerTool(tool);
 return true;
}

// Capture before Orbit/Fly handlers, including wheel and already-captured drags.
export function installCameraInputGuard({root,isControlled}){
 const events=['pointerdown','pointermove','pointerup','pointercancel','wheel','keydown','keyup','dblclick','contextmenu'];
 const block=event=>{
  if(!isControlled()||!event.target?.closest?.('#viewport, .comparison-canvas'))return;
  event.preventDefault();event.stopImmediatePropagation();
 };
 for(const type of events)root.addEventListener(type,block,{capture:true,passive:false});
 return ()=>{for(const type of events)root.removeEventListener(type,block,true);};
}
