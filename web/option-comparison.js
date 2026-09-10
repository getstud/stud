// Shared actions for the option tabs and voice/WebMCP. Saved display and writer
// identity are deliberately separate; no comparison action activates an option.
export async function comparisonRequest(url, payload) {
 const response=await fetch(url,{cache:'no-store',signal:AbortSignal.timeout(30000),...(payload?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}:{})});
 const data=await response.json();
 if(!response.ok)throw Object.assign(new Error(data.error?.message||`Request failed (${response.status}).`),{code:data.error?.category});
 return data;
}
const command=(operation,args)=>comparisonRequest('/api/v1/command',{operation,key:crypto.randomUUID(),arguments:args});
const fail=(code,message,extra={})=>Object.assign(new Error(message),{code,...extra});
const normalize=value=>value.toLowerCase().replace(/[^\p{L}\p{N}]+/gu,' ').trim();
export function resolveOption(options,reference) {
 if(typeof reference!=='string'||!reference.trim())throw fail('INVALID_INPUT','Provide an option ID or name.');
 let candidates=options.filter(option=>option.id===reference);
 if(!candidates.length)candidates=options.filter(option=>normalize(option.label)===normalize(reference));
 if(!candidates.length){const words=normalize(reference).split(' ').filter(word=>!['the','version','option','design'].includes(word));
  if(words.length)candidates=options.filter(option=>words.every(word=>normalize(option.label).split(' ').includes(word)));
 }
 if(candidates.length!==1)throw fail(candidates.length?'AMBIGUOUS_OPTION':'OPTION_NOT_FOUND',candidates.length?'Several options match. Ask the user which one they mean.':'No option name matches. Ask the user to choose from the available options.',{candidates:candidates.length?candidates:options});
 return candidates[0];
}
export function visualDifferences(left,right) {
 const a=new Map(left.parts.map(part=>[part.id,part])),b=new Map(right.parts.map(part=>[part.id,part]));
 return [...new Set([...a.keys(),...b.keys()])].flatMap(id=>{
  const before=a.get(id),after=b.get(id),changes=[];
  if(!before)changes.push('added');else if(!after)changes.push('removed');else{
   if(before.cad.shape_key!==after.cad.shape_key)changes.push('reshaped');
   if(JSON.stringify(before.cad.placement)!==JSON.stringify(after.cad.placement))changes.push('moved');
   if(before.stock!==after.stock||before.color!==after.color)changes.push('appearance');
   if(before.name!==after.name||before.assembly!==after.assembly)changes.push('label_or_assembly');
  }
  const describe=part=>part?{name:part.name,assembly:part.assembly,material:part.stock,color:part.color,size:part.size,origin:part.origin,rotation:part.rotation}:null;
  return changes.length?[{id,changes,before:describe(before),after:describe(after)}]:[];
 });
}
export class OptionComparison {
 constructor({request=comparisonRequest,run=command,refreshModel,displayPrepared,readViewer,prepare=async()=>{},beforeSwitch=()=>{},onChange=()=>{}}){
  Object.assign(this,{request,run,refreshModel,displayPrepared,readViewer,prepare,beforeSwitch,onChange});
  this.options=[];this.checkpoints=[];this.saved=null;this.pending=null;this.cache=new Map();this.sequence=0;this.refreshSequence=0;this.commit=Promise.resolve();
 }
 refresh(){
  const sequence=++this.refreshSequence;
  this.refreshTask=(async()=>{
   try{
    const [saved,options,checkpoints]=await Promise.all([this.request('/api/v1/status'),this.request('/api/v1/options'),this.request('/api/v1/checkpoints')]);
    if(sequence!==this.refreshSequence)return this.refreshTask;
    this.saved=saved;this.options=options;this.checkpoints=checkpoints;
    const heads=new Set(options.map(option=>option.head));for(const key of this.cache.keys())if(!heads.has(key))this.cache.delete(key);
    this.onChange(this.state());return this.state();
   }catch(error){if(sequence!==this.refreshSequence)return this.refreshTask;throw error;}
  })();
  return this.refreshTask;
 }
 state(){
  const viewer=this.readViewer(),cad=viewer.model?.cad;
  return {options:this.options.map(option=>({...option,summary:this.checkpoints.find(c=>c.checkpoint===option.head)?.summary||'',editing_target:option.id===this.saved?.active_option,displayed:cad?.presentation==='history'&&cad?.option_id===option.id&&cad?.checkpoint===option.head})),
   displayed:{mode:cad?.presentation||'live',option_id:cad?.option_id||null,checkpoint:cad?.checkpoint||null,build_id:cad?.build_id||null,source_id:cad?.source_id||null,revision:viewer.model?.revision||null},
   editing:{option_id:this.saved?.active_option,label:this.saved?.option?.label,request_id:this.saved?.request?.id||null,intent:this.saved?.request?.intent||null},
   pending:this.pending,viewpoint:viewer.camera,selected_part:viewer.selected||null,visible_part_ids:viewer.visible_part_ids||[]};
 }
 async wait(job){
  while(['queued','running'].includes(job.status)){
   await new Promise(resolve=>setTimeout(resolve,150));job=await this.request(`/api/v1/jobs/${encodeURIComponent(job.id)}`);
  }
  if(job.status!=='complete')throw fail('OPTION_UNAVAILABLE',job.error?.message||'Saved geometry is unavailable. Keeping the last successfully opened design.');
  return job;
 }
 async prepared(option){
  if(!this.cache.has(option.head)){
   const promise=(async()=>{
    const job=await this.wait(await this.run('prepare_option',{option_id:option.id,expected_head:option.head}));
    const model=job.result?.views?.[0];
    if(!model)throw fail('OPTION_UNAVAILABLE',job.result?.view_errors?.[0]?.message||'Saved geometry is unavailable.');
    await this.prepare(model);return {job,model};
   })().catch(error=>{this.cache.delete(option.head);throw error;});this.cache.set(option.head,promise);
  }
  return this.cache.get(option.head);
 }
 async switchOption(reference,{expected_head}={}){
  if(!this.saved)await this.refresh();
  const option=resolveOption(this.options,reference);
  if(expected_head&&expected_head!==option.head)throw fail('CHANGED_HEAD','The option changed; read its current checkpoint before comparing.');
  this.beforeSwitch();const sequence=++this.sequence;this.pending=option.id;this.onChange(this.state());
  try{
   const prepared=await this.prepared(option);
   // Serialize only the display commit. Slow preparation cannot steal the view
   // back from a newer tab; later selections never queue behind unused builds.
   const apply=this.commit.catch(()=>{}).then(async()=>{
    if(sequence!==this.sequence)throw fail('SUPERSEDED','A newer tab selection replaced this one.');
    const response=await this.run('inspect_option',{option_id:option.id,expected_head:option.head,comparison_id:prepared.job.id});
    if(response?.editing){
     this.saved.active_option=response.editing.option_id;this.saved.option=this.options.find(o=>o.id===response.editing.option_id);
     this.saved.request=response.editing.request_id?{id:response.editing.request_id,intent:response.editing.intent}:null;
    }
    if(this.displayPrepared)await this.displayPrepared({...prepared.model,cad:{...prepared.model.cad,presentation:'history',option_id:option.id}},response);
    else await this.refreshModel();
    if(sequence!==this.sequence)throw fail('SUPERSEDED','A newer tab selection replaced this one.');
    const displayed=this.readViewer().model?.cad;
    if(displayed?.option_id!==option.id||displayed?.checkpoint!==option.head||displayed?.build_id!==prepared.model.cad.build_id)throw fail('DISPLAY_INTERRUPTED','The requested option is not displayed yet. Select the tab again.');
    this.pending=null;
    return this.state();
   });this.commit=apply;return await apply;
  }catch(error){
   // A previously accepted tab may still be arriving when preparation fails.
   // Settle that last successful display before reporting the failed request.
   await this.commit.catch(()=>{});
   if(error.code==='changed_head')await this.refresh();
   throw error;
  }finally{if(sequence===this.sequence){this.pending=null;this.onChange(this.state());}}
 }
 async returnLive(){
  this.beforeSwitch();const sequence=++this.sequence;this.pending='live';this.onChange(this.state());
  const apply=this.commit.catch(()=>{}).then(async()=>{
   if(sequence!==this.sequence)throw fail('SUPERSEDED','A newer tab selection replaced this one.');
   await this.run('return_live',{});await this.refreshModel();
   if(sequence!==this.sequence)throw fail('SUPERSEDED','A newer tab selection replaced this one.');
   if(this.readViewer().model?.cad?.presentation!=='live')throw fail('DISPLAY_INTERRUPTED','The live editing view is not displayed yet. Try returning to it again.');
   this.pending=null;return this.state();
  });this.commit=apply;
  try{return await apply;}finally{if(sequence===this.sequence){this.pending=null;this.onChange(this.state());}}
 }
 async compare(reference){
  await this.refresh();const before=this.readViewer().model,baseline=this.state().displayed;
  if(!before)throw fail('MODEL_UNAVAILABLE','Load a design before comparing.');
  const state=await this.switchOption(reference),after=this.readViewer().model;
  return {baseline,comparison:state.displayed,units:'in',changes:visualDifferences(before,after),state,
   guidance:'The baseline is the actual previously displayed model, including any draft. Inspect the canvas at this retained viewpoint and explain relevant visible differences; do not infer unseen details. The editing target is unchanged.'};
 }
}
export function createComparisonTools(controller){
 const tool=(name,description,properties,execute,required=[])=>({name,description,inputSchema:{type:'object',properties,required,additionalProperties:false},annotations:{readOnlyHint:name==='list_options'},execute:async(input={})=>{
  try{
   if(!input||typeof input!=='object'||Array.isArray(input)||Object.keys(input).some(key=>!Object.hasOwn(properties,key))||required.some(key=>typeof input[key]!=='string'||!input[key].trim())||('expected_head' in input&&(typeof input.expected_head!=='string'||!input.expected_head)))throw fail('INVALID_INPUT','Provide only the documented comparison arguments.');
   return {ok:true,...await execute(input)};
  }catch(error){return {ok:false,error:{code:error.code||'COMPARISON_FAILED',message:error.message,...(error.candidates?{candidates:error.candidates}:{})}};}
 }});
 const option={type:'string',minLength:1,description:'Exact option ID or an unambiguous name. Read list_options to resolve natural references; clarify ambiguous names with the user.'};
 return [
  tool('list_options','Read stud option names, branch heads, checkpoint summaries, the displayed design, active editing target, selected part and exact camera. Use these to resolve references such as “the dormered version”.',{},async()=>({state:await controller.refresh()})),
  tool('switch_option','Switch the visible stud comparison tab to a saved option. Retains the exact viewpoint, projection and scale. Does not change the editing target or design. Return only after the model is displayed.',{option,expected_head:{type:'string',minLength:1}},input=>controller.switchOption(input.option,input).then(state=>({state})),['option']),
  tool('compare_options','Compare the actual displayed design (including a draft) with a named option and switch to its tab at the exact same viewpoint. Returns changed parts and both displayed identities for a visual explanation. Use switch_option to flip back; clarify ambiguous names. Leaves editing target unchanged.',{option},input=>controller.compare(input.option),['option']),
  tool('return_to_editing_view','Return the viewer to the live editing design at the same viewpoint, without activating another option.',{},()=>controller.returnLive().then(state=>({state}))),
 ];
}
