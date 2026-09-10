// Shared by the Versions UI and WebMCP. Idempotency keys survive transport retries.
export async function request(url,payload){
 const options={cache:'no-store',signal:AbortSignal.timeout(30000)};
 if(payload)Object.assign(options,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
 let response;
 try{response=await fetch(url,options);}catch(error){if(!payload)throw error;response=await fetch(url,{...options,signal:AbortSignal.timeout(30000)});}
 const data=await response.json();if(!response.ok)throw Object.assign(new Error(data.error?.message||data.error||`Request failed (${response.status}).`),{code:data.error?.category});return data;
}
export const command=(operation,args={})=>request('/api/v1/command',{operation,key:crypto.randomUUID(),arguments:args});
export async function waitJob(job,onProgress=()=>{}){
 while(job.id&&['queued','running'].includes(job.status)){
  onProgress(`${job.kind?.replaceAll('_',' ')||'Job'}: ${job.stage||job.status}`);
  await new Promise(resolve=>setTimeout(resolve,350));job=await request(`/api/v1/jobs/${encodeURIComponent(job.id)}`);
 }
 if(['failed','interrupted','canceled','superseded','generation_failed'].includes(job.status))throw Object.assign(new Error(job.error?.message||job.diagnostics?.message||`Job ${job.status}; saved evidence is retained.`),{code:'JOB_FAILED'});
 return job;
}
export async function restoreCheckpoint({checkpoint,option_id,expected_head},onProgress){
 const draft=await command('restore',{checkpoint,option_id,expected_head});
 const source=await command('source',{request_id:draft.id});
 const result=await waitJob(await command('finish',{request_id:draft.id,expected_source:source.source_id,summary:`Restore design from ${checkpoint.slice(0,12)}`}),onProgress);
 await command('return_live');return result;
}
export async function versionOperation(input,onProgress){
 const {action,expected_revision,...args}=input;
 if(action==='list'){
  const [status,options,checkpoints]=await Promise.all([request('/api/v1/status'),request('/api/v1/options'),request('/api/v1/checkpoints')]);
  return {status,options,checkpoints};
 }
 if(action==='restore')return restoreCheckpoint(args,onProgress);
 if(action==='inspect'){
  if(Boolean(args.checkpoint)===Boolean(args.option_id))throw new Error('Specify one checkpoint or option_id.');
  if(args.option_id){const options=await request('/api/v1/options');const option=options.find(o=>o.id===args.option_id);if(!option)throw new Error('Option not found.');args.checkpoint=option.head;delete args.option_id;}
 }
 if(action==='rename'){args.expected_revision=args.option_revision;delete args.option_revision;}
 const operations={inspect:'inspect_checkpoint',live:'return_live',activate:'activate_option',create:'create_option',rename:'rename_option',compare:'compare'};
 const result=await waitJob(await command(operations[action],args),onProgress);
 // Activation schedules evaluation separately. Wait for its actual display.
 if(action==='activate'){const state=await request('/api/v1/status');if(state.latest_build)await waitJob(await request(`/api/v1/jobs/${encodeURIComponent(state.latest_build)}`),onProgress);}
 return result;
}
export function packetLinks(job,base=location.href){
 if(job.status!=='complete')return [];
 return [...new Set(['manifest.json',...Object.keys(job.result?.files||{})])].map(name=>({name,url:new URL(`/api/v1/exports/${encodeURIComponent(job.id)}/${encodeURIComponent(name)}`,base).href}));
}
