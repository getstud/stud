import {OptionComparison,createComparisonTools} from '/option-comparison.js';

export function installOptionTabs(adapter){
 const root=document.createElement('div');root.id='option-comparison';
 root.innerHTML='<div class="option-tabs" role="tablist" aria-label="Compare design options"></div><span class="option-message" role="status"></span>';
 document.querySelector('.stage').prepend(root);
 document.getElementById('viewport').setAttribute('role','tabpanel');
 const tabs=root.querySelector('.option-tabs'),message=root.querySelector('.option-message');
 let error=null;
 const controller=new OptionComparison({...adapter,onChange:render});
 const run=async action=>{error=null;try{await action();}catch(problem){if(problem.code!=='SUPERSEDED')error=problem.message;}render(controller.state());};
 function render(state){
  const focused=document.activeElement?.dataset.option;
  const editing=`Editing: ${state.editing.label||'—'}${state.editing.request_id?' · request open':''}`;
  const entries=[{id:'live',label:'Live',active:state.displayed.mode==='live'},...state.options.map(option=>({id:option.id,label:option.label,active:option.displayed,head:option.head,editing:option.editing_target}))];
  // Keep tab nodes stable while asynchronous refreshes arrive, including focus.
  for(const node of [...tabs.children])if(!entries.some(entry=>entry.id===node.dataset.option))node.remove();
  for(const entry of entries){
   let button=[...tabs.children].find(node=>node.dataset.option===entry.id);
   if(!button){button=document.createElement('button');button.type='button';button.dataset.option=entry.id;button.setAttribute('role','tab');button.setAttribute('aria-controls','viewport');button.id=`option-tab-${entry.id}`;tabs.append(button);
    button.onclick=()=>run(()=>entry.id==='live'?controller.returnLive():controller.switchOption(entry.id));
    button.onpointerenter=()=>{const option=controller.options.find(option=>option.id===entry.id);if(option)void controller.prepared(option).catch(()=>{});};
   }
   button.textContent=entry.label;
   button.classList.toggle('is-editing',Boolean(entry.editing));
   button.setAttribute('aria-label',`${entry.label}${entry.editing?', active editing option':''}`);
   button.title=entry.head?`${entry.label} · saved ${entry.head.slice(0,12)}${entry.editing?`\n${editing}${state.editing.intent?`\n${state.editing.intent}`:''}`:''}`:`Latest design\n${editing}`;
   const becameActive=entry.active&&button.getAttribute('aria-selected')!=='true';
   button.setAttribute('aria-selected',String(entry.active));button.tabIndex=entry.active?0:-1;
   button.classList.toggle('is-pending',state.pending===entry.id);
   if(entry.active)document.getElementById('viewport').setAttribute('aria-labelledby',button.id);
   if(becameActive)button.scrollIntoView({block:'nearest',inline:'nearest'});
  }
  if(!entries.some(entry=>entry.active))tabs.firstElementChild.tabIndex=0;
  if(focused)[...tabs.children].find(node=>node.dataset.option===focused)?.focus({preventScroll:true});
  root.setAttribute('aria-busy',String(Boolean(state.pending)));
  const pending=entries.find(entry=>entry.id===state.pending);
  const shown=entries.find(entry=>entry.active);
  message.textContent=error||(pending?`Opening ${pending.label}…`:`${state.displayed.mode==='live'?'Live design':shown?.label||'Saved checkpoint'} · Same viewpoint. ${editing}`);
  message.classList.toggle('has-error',Boolean(error));
  if(!state.pending)adapter.onSettled?.();
 }
 tabs.addEventListener('keydown',event=>{
  const items=[...tabs.children],index=items.indexOf(document.activeElement);if(index<0)return;
  const next=event.key==='Home'?0:event.key==='End'?items.length-1:event.key==='ArrowRight'?(index+1)%items.length:event.key==='ArrowLeft'?(index+items.length-1)%items.length:null;
  if(next===null)return;event.preventDefault();items[next].focus();items[next].click();items[next].scrollIntoView({block:'nearest',inline:'nearest'});
 });
 const refresh=()=>void controller.refresh().catch(problem=>{error=problem.message;render(controller.state());});
 window.addEventListener('studprojectchange',event=>{
  if(['history_displayed','live_displayed','comparison_complete','plans_complete'].includes(event.detail?.type))return;
  refresh();
 });
 const tools=createComparisonTools(controller);
 // #24 can include these same descriptors in the shared tool registry.
 Promise.resolve().then(()=>adapter.registerTools?adapter.registerTools(tools):
  Promise.all(tools.map(tool=>document.modelContext?.registerTool?.(tool))))
  .catch(problem=>console.warn('stud comparison tools could not register:',problem));
 refresh();
 return {controller,tools,refresh};
}
