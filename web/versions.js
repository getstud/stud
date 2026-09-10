import {request,command,waitJob,restoreCheckpoint} from '/project-operations.js';
import {ComparisonScene} from '/comparison-scene.js';

const el=(tag,text,attrs={})=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;for(const [key,value] of Object.entries(attrs))node.setAttribute(key,value);return node;};
const short=value=>value?.slice(0,12)||'Unavailable';
const amount=(value,currency='USD')=>value===null||value===undefined?'Incomplete':new Intl.NumberFormat(undefined,{style:'currency',currency}).format(Number(value));

export function installVersions({showWorkspace,refreshModel}){
 if(document.getElementById('design-versions'))return;
 const stylesheet=el('link',undefined,{rel:'stylesheet',href:'/versions.css'});document.head.append(stylesheet);
 document.querySelector('.page-links').append(el('a','Versions',{href:'#design-versions','data-page':'design-versions'}));
 document.getElementById('page-select').append(el('option','Versions',{value:'design-versions'}));
 const section=el('section',undefined,{id:'design-versions',class:'materials',hidden:''});
 section.innerHTML=`<div class="materialhead"><h2>Design versions</h2><button type="button" id="version-live">Return to current design</button></div>
 <p class="sub">Inspect saved designs, compare alternatives, and make a plan packet from a fixed checkpoint.</p>
 <p id="version-status" role="status"></p><p id="version-error" role="alert"></p>
 <div class="version-toolbar"><label>Design option<select id="version-option"></select></label><button id="version-activate">Activate option</button><label>Option name<input id="version-name" maxlength="120"></label><button id="version-rename">Rename</button></div>
 <div class="version-toolbar"><label>New option name<input id="version-new-name" maxlength="120" placeholder="For example, Wider workbench"></label><label>Start from checkpoint<select id="version-base"></select></label><button id="version-create">Create option</button></div>
 <h3>Saved checkpoints</h3><div class="tablewrap"><table><thead><tr><th>Saved change</th><th>Outcome</th><th>Options</th><th>Actions</th></tr></thead><tbody id="version-checkpoints"></tbody></table></div>
 <h3>Compare two checkpoints</h3><div class="version-toolbar"><label>A<select id="version-left"></select></label><label>B<select id="version-right"></select></label><label>Price basis<select id="version-price-mode"><option value="historical">Original saved estimates</option><option value="common_price">Same current saved quotes</option></select></label><button id="version-compare">Compare</button></div>
 <p class="sub">Comparison leaves the active editing request open. Orbit either view to move both cameras.</p><p id="comparison-summary" role="status"></p>
 <div id="comparison-views" class="comparison-views"></div><div id="comparison-legend" class="comparison-legend" hidden><span><i style="background:#4b9975"></i>Added</span><span><i style="background:#bc7364"></i>Removed</span><span><i style="background:#d19b50"></i>Reshaped</span><span><i style="background:#6d9fb3"></i>Moved</span><span>Faded: unchanged</span></div>
 <p id="comparison-selected" class="comparison-details"></p><div id="comparison-details"></div>
 <h3>Plan packets</h3><div class="version-toolbar"><label>Checkpoint<select id="version-plan-checkpoint"></select></label><label>Paper<select id="version-paper"><option value="letter">US Letter</option><option value="a4">A4</option></select></label><label>Layout<select id="version-plan-layout"><option value="compact">Compact</option><option value="expanded">Expanded drawings</option></select></label><button id="version-plans">Generate packet</button></div>
 <p class="sub">Packets retain their model, quoted prices, scale and completeness findings. Later changes leave saved packets intact.</p><div class="tablewrap"><table><thead><tr><th>Checkpoint</th><th>Packet</th><th>Files</th></tr></thead><tbody id="version-exports"></tbody></table></div>`;
 document.getElementById('reports').append(section);
 const $=id=>document.getElementById(id);let state=null,options=[],checkpoints=[],refreshing=null,scene=null,comparison=null,busy=false;
 const status=text=>{$('version-status').textContent=text;};
 const action=(button,handler)=>{button.onclick=async()=>{button.disabled=true;busy=true;$('version-error').textContent='';try{await handler();await refresh();}catch(error){$('version-error').textContent=error.message;}finally{busy=false;button.disabled=false;}};};
 function fill(id,values,label,preferred){const select=$(id),previous=select.value;select.replaceChildren(...values.map(value=>el('option',label(value),{value:value.checkpoint||value.id})));if(values.some(v=>(v.checkpoint||v.id)===previous))select.value=previous;else if(preferred)select.value=preferred;}
 function table(headers,rows){const wrap=el('div',undefined,{class:'tablewrap'}),table=el('table'),head=el('thead'),tr=el('tr'),body=el('tbody');headers.forEach(text=>tr.append(el('th',text)));head.append(tr);for(const cells of rows){const row=el('tr');for(const content of cells){const cell=el('td');if(content instanceof Node)cell.append(content);else cell.textContent=String(content??'—');row.append(cell);}body.append(row);}table.append(head,body);wrap.append(table);return wrap;}
 function details(title,content){const node=el('details');node.append(el('summary',title),content);return node;}
 function populate(){
  fill('version-option',options,o=>`${o.label}${o.id===state.active_option?' · active':''}`,state.active_option);
  if(document.activeElement!==$('version-name'))$('version-name').value=options.find(o=>o.id===$('version-option').value)?.label||'';
  const label=c=>`${short(c.checkpoint)} · ${c.summary}`;
  for(const id of ['version-base','version-left','version-right','version-plan-checkpoint'])fill(id,checkpoints,label,id==='version-left'?(checkpoints[1]?.checkpoint||state.option.head):state.option.head);
  const names=new Map(options.map(o=>[o.id,o.label]));$('version-checkpoints').replaceChildren();
  for(const checkpoint of checkpoints){
   const row=el('tr'),title=el('td',checkpoint.summary);title.append(el('small',`${short(checkpoint.checkpoint)} · ${new Date(checkpoint.created_at*1000).toLocaleString()}`,{class:'checkpoint-code'}));
   const controls=el('td'),inspect=el('button','Inspect'),restore=el('button','Restore as new checkpoint');
   inspect.dataset.checkpoint=checkpoint.checkpoint;restore.dataset.restore=checkpoint.checkpoint;
   action(inspect,async()=>{status('Opening saved design…');await waitJob(await command('inspect_checkpoint',{checkpoint:checkpoint.checkpoint}),status);await refreshModel();showWorkspace();status(`Inspecting ${short(checkpoint.checkpoint)}. The editing request is unchanged.`);});
   restore.disabled=Boolean(state.request)||state.pending_records.length>0;restore.title=restore.disabled?'Finish the current editing request before restoring a checkpoint.':'';
   action(restore,async()=>{status('Preparing restored source…');const result=await restoreCheckpoint({checkpoint:checkpoint.checkpoint,option_id:state.active_option,expected_head:state.option.head},status);await refreshModel();status(`Restored design saved as ${short(result.checkpoint||result.result?.checkpoint)}.`);});
   controls.append(inspect,restore);row.append(title,el('td',checkpoint.outcome.replaceAll('_',' ')),el('td',checkpoint.options.map(id=>names.get(id)||id).join(', ')),controls);$('version-checkpoints').append(row);
  }
  $('version-activate').disabled=Boolean(state.request)||state.pending_records.length>0;
  if(!busy)status(`${state.option.label} · ${state.view_mode==='history'?`inspecting ${short(state.view_checkpoint)}`:'current design'}${state.request?`\nEditing: ${state.request.intent} (${state.request.status}).`:''}`);
 }
 async function refresh(){if(refreshing)return refreshing;refreshing=(async()=>{const [snapshot,allOptions,allCheckpoints,exports]=await Promise.all([request('/api/v1/status'),request('/api/v1/options'),request('/api/v1/checkpoints'),request('/api/v1/exports')]);state=snapshot;options=allOptions;checkpoints=allCheckpoints;populate();$('version-exports').replaceChildren();for(const job of exports.sort((a,b)=>b.created_at-a.created_at)){const row=el('tr'),links=el('td');if(job.status==='complete'){for(const [file,label] of [['plans.pdf','PDF'],['manifest.json','Packet record'],['parts.csv','Parts CSV']])if(file==='manifest.json'||job.result.files[file])links.append(el('a',label,{href:`/api/v1/exports/${encodeURIComponent(job.id)}/${file}`,download:''}),document.createTextNode('  '));}else if(job.error)links.textContent=job.error.message;row.append(el('td',short(job.arguments.checkpoint)),el('td',job.status==='complete'?`${job.result.review?.status||job.result.completeness?.status||'Saved'} · ${job.result.sheets?.length||0} sheets`:job.status),links);$('version-exports').append(row);}})().finally(()=>{refreshing=null;});return refreshing;}
 $('version-option').onchange=()=>{$('version-name').value=options.find(o=>o.id===$('version-option').value)?.label||'';};
 action($('version-live'),async()=>{await command('return_live');await refreshModel();showWorkspace();status('Returned to the current design.');});
 action($('version-activate'),async()=>{const option=options.find(o=>o.id===$('version-option').value);await command('activate_option',{option_id:option.id,expected_head:option.head});await refreshModel();status(`Activated ${option.label}.`);});
 action($('version-rename'),async()=>{const option=options.find(o=>o.id===$('version-option').value);await command('rename_option',{option_id:option.id,name:$('version-name').value,expected_revision:option.revision});status('Option name saved.');});
 action($('version-create'),async()=>{const option=await command('create_option',{name:$('version-new-name').value,base_checkpoint:$('version-base').value});status(`Created ${option.label}. Activate it when ready to edit.`);$('version-new-name').value='';});
 action($('version-compare'),async()=>{
  const job=await waitJob(await command('compare',{left:$('version-left').value,right:$('version-right').value,mode:$('version-price-mode').value}),status);
  await displayComparison(job.result);
 });
 async function displayComparison(result){
  comparison=result;$('version-left').value=result.left_checkpoint;$('version-right').value=result.right_checkpoint;$('version-price-mode').value=result.estimates.mode||'historical';scene?.dispose();scene=new ComparisonScene($('comparison-views'),selectPart);await scene.load(comparison);
  const estimate=comparison.estimates,changed=comparison.objects.filter(row=>row.status!=='unchanged');
  $('comparison-summary').textContent=`${changed.length} changed parts. ${estimate.mode==='common_price'?'Both estimates use the same saved quotes.':'Original saved estimates.'} A: ${amount(estimate.left_total,estimate.left_currency)} · B: ${amount(estimate.right_total,estimate.right_currency)}${estimate.assumptions_changed?' Design quantity assumptions also differ.':''}`;
  $('comparison-legend').hidden=!comparison.views.some(Boolean);$('comparison-selected').textContent='';$('comparison-details').replaceChildren();
  const objectRows=changed.map(row=>{const button=el('button',row.right?.label||row.left?.label||row.id);button.onclick=()=>scene.select(row.id);return [button,row.changes.join(', '),row.id];});
  $('comparison-details').append(details(`Changed parts (${changed.length})`,table(['Part','Change','Stable ID'],objectRows)));
  const lines=(estimate.lines||[]).filter(row=>row.status!=='unchanged');
  $('comparison-details').append(details(`Estimate changes (${lines.length})`,table(['Material','Change','A quantity / price','B quantity / price','Purchase basis'],lines.map(row=>[row.product_id,row.changes.join(', ')||row.status,`${row.left?.quantity??'—'} / ${amount(row.left?.unit_price,estimate.left_currency)}`,`${row.right?.quantity??'—'} / ${amount(row.right?.unit_price,estimate.right_currency)}`,row.right?.basis||row.left?.basis]))));
  for(const [field,label] of [['requirements','Requirements'],['findings','Measured findings'],['materials','Material demands']]){const rows=comparison[field].filter(row=>row.status!=='unchanged');$('comparison-details').append(details(`${label} (${rows.length} changes)`,table(['Reference','Change','A','B'],rows.map(row=>[row.id,row.status,describe(row.left),describe(row.right)]))));}
  status('Comparison is ready. The current editing request is unchanged.');$('comparison-views').scrollIntoView({block:'center',behavior:'instant'});
 }
 function describe(record){if(!record)return 'Absent';if(record.measured!==undefined)return `${record.status}: ${record.measured??'unresolved'} ${record.units||''}`;if(record.threshold!==undefined)return `${record.kind}: ${record.threshold} ${record.units}`;return `${record.product_id}: ${record.object_ids?.length||0} referenced parts${record.quantity!==null?`, ${record.quantity} items`:''}`;}
 function selectPart(id){const row=comparison.objects.find(row=>row.id===id);const size=(blank,index)=>blank.size.map(v=>`${Number(v.toFixed(4))} ${comparison.units[index]}`).join(' × ');$('comparison-selected').textContent=`${row.right?.label||row.left?.label||id}\n${id}\n${row.changes.join(', ')}${row.left?.blank?.size?`\nA blank: ${size(row.left.blank,0)}`:''}${row.right?.blank?.size?`\nB blank: ${size(row.right.blank,1)}`:''}`;}
 action($('version-plans'),async()=>{await waitJob(await command('plans',{checkpoint:$('version-plan-checkpoint').value,print_spec:{paper:$('version-paper').value,layout:$('version-plan-layout').value}}),status);status('The fixed-checkpoint packet is saved below.');});
 const schedule=()=>{if(location.hash==='#design-versions')void refresh().catch(error=>{$('version-error').textContent=error.message;});};
 window.addEventListener('hashchange',schedule);window.addEventListener('studprojectchange',schedule);
 window.addEventListener('beforeunload',()=>scene?.dispose(),{once:true});
 void refresh().catch(error=>{$('version-error').textContent=error.message;});
 window.dispatchEvent(new HashChangeEvent('hashchange'));
 return {refresh,displayComparison,
  presentPacket:job=>{$('version-plan-checkpoint').value=job.arguments.checkpoint;$('version-paper').value=job.arguments.print_spec.paper;$('version-plan-layout').value=job.arguments.print_spec.layout;},
  comparisonContext:()=>comparison?{left_checkpoint:comparison.left_checkpoint,right_checkpoint:comparison.right_checkpoint,units:comparison.units,selected_part_id:scene?.selected||null,cameras:scene?.sides.map(side=>({side:side.index,position:side.camera.position.toArray(),target:side.controls.target.toArray(),quaternion:side.camera.quaternion.toArray(),zoom:side.camera.zoom,units:'viewer inches: X right, Y up, Z toward front'}))}:null,
  selectComparison:id=>{if(!comparison?.objects.some(row=>row.id===id))throw new Error('Comparison part not found.');scene.select(id);$('comparison-views').scrollIntoView({block:'center',behavior:'instant'});return {part:comparison.objects.find(row=>row.id===id)};},
  moveComparison:input=>{if(!scene?.sides.length)throw new Error('Open a comparison first.');scene.setCamera(input);$('comparison-views').scrollIntoView({block:'center',behavior:'instant'});return {};},
  get comparisonSelection(){return scene?.selected||null}
 };
}
