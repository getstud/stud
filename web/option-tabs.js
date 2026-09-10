import {OptionComparison,createComparisonTools} from '/option-comparison.js';

export function installOptionTabs(adapter){
 const root=document.createElement('div');root.id='option-comparison';
 root.innerHTML=`<button id="optiontoggle" type="button" aria-haspopup="dialog" aria-expanded="false" aria-controls="option-menu"><span class="option-current">Current version</span><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></button>
 <div id="option-menu" role="dialog" aria-label="Design options" hidden><div class="option-menu-heading">Switch option</div><div class="option-list" role="listbox" aria-label="Design options"></div><button class="option-new" type="button">＋ Create new option</button><form class="option-create" hidden><label for="option-name">Option name</label><input id="option-name" name="name" required maxlength="120" autocomplete="off" placeholder="e.g. Wider porch"><p class="option-base"></p><div class="option-create-actions"><button class="option-cancel" type="button">Cancel</button><button type="submit">Create option</button></div></form><span class="option-message" role="status"></span></div>`;
 document.querySelector('.stage').prepend(root);
 const toggle=root.querySelector('#optiontoggle'),menu=root.querySelector('#option-menu'),list=root.querySelector('.option-list'),message=root.querySelector('.option-message'),form=root.querySelector('form'),name=root.querySelector('input'),newButton=root.querySelector('.option-new');
 let error=null,creating=false,base=null;
 const setOpen=open=>{menu.hidden=!open;toggle.setAttribute('aria-expanded',String(open));if(!open){form.hidden=true;newButton.hidden=false;}};
 toggle.onclick=()=>setOpen(menu.hidden);
 toggle.onkeydown=event=>{if(event.key==='ArrowDown'){event.preventDefault();setOpen(true);(list.querySelector('[aria-selected=true]')||list.firstElementChild)?.focus();}};
 document.addEventListener('pointerdown',event=>{if(!root.contains(event.target))setOpen(false);});
 root.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();setOpen(false);toggle.focus();}});
 const controller=new OptionComparison({...adapter,onChange:render});
 const run=async action=>{error=null;try{await action();setOpen(false);toggle.focus({preventScroll:true});}catch(problem){if(problem.code!=='SUPERSEDED'){error=problem.message;setOpen(true);}}render(controller.state());};
 function render(state){
  const entries=[{id:'live',label:`${state.editing.label||'Current design'} · Live`,active:state.displayed.mode==='live'},...state.options.map(option=>({id:option.id,label:option.label,active:option.displayed,editing:option.editing_target}))];
  const shown=entries.find(entry=>entry.active),current=state.displayed.mode==='live'?state.editing.label:shown?.label||state.options.find(option=>option.id===state.displayed.option_id)?.label;
  root.querySelector('.option-current').textContent=current||'Saved checkpoint';
  toggle.title=`${current||'Saved checkpoint'}${state.displayed.mode==='live'?' · Live':''} — Change option`;
  toggle.setAttribute('aria-label',toggle.title);
  toggle.classList.toggle('is-pending',Boolean(state.pending)||creating);
  for(const node of [...list.children])if(!entries.some(entry=>entry.id===node.dataset.option))node.remove();
  for(const entry of entries){
   let button=[...list.children].find(node=>node.dataset.option===entry.id);
   if(!button){button=document.createElement('button');button.type='button';button.dataset.option=entry.id;button.setAttribute('role','option');list.append(button);
    button.onclick=()=>run(()=>entry.id==='live'?controller.returnLive():controller.switchOption(entry.id));
    button.onpointerenter=()=>{const option=controller.options.find(option=>option.id===entry.id);if(option)void controller.prepared(option).catch(()=>{});};
   }
   button.textContent=entry.label;button.setAttribute('aria-selected',String(entry.active));button.title=entry.editing?'Active editing option':entry.label;button.disabled=creating;
  }
  newButton.disabled=creating||Boolean(state.pending);
  message.textContent=error||(state.pending?'Opening option…':creating?'Creating option…':`${current||'Saved checkpoint'}. Editing: ${state.editing.label||'—'}`);
  message.classList.toggle('has-error',Boolean(error));
  if(!state.pending)adapter.onSettled?.();
 }
 list.addEventListener('keydown',event=>{
  const items=[...list.children],index=items.indexOf(document.activeElement);
  const next=event.key==='Home'?0:event.key==='End'?items.length-1:event.key==='ArrowDown'?(index+1)%items.length:event.key==='ArrowUp'?(index+items.length-1)%items.length:null;
  if(next!==null){event.preventDefault();items[next]?.focus();}
 });
 newButton.onclick=()=>{
  const state=controller.state(),source=state.displayed.mode==='live'?state.options.find(option=>option.id===state.editing.option_id):state.options.find(option=>option.id===state.displayed.option_id);
  base=state.displayed.mode==='live'?source?.head:state.displayed.checkpoint;
  if(!base){error='Save a checkpoint before creating an option.';render(state);return;}
  root.querySelector('.option-base').textContent=`Starts from ${source?.label||'this version'}${state.displayed.mode==='live'?"’s latest saved checkpoint":' at the displayed checkpoint'}.`;
  form.hidden=false;newButton.hidden=true;name.value='';name.focus();
 };
 root.querySelector('.option-cancel').onclick=()=>{form.hidden=true;newButton.hidden=false;newButton.focus();};
 form.onsubmit=async event=>{
  event.preventDefault();if(creating||!name.value.trim())return;
  creating=true;error=null;const submittedName=name.value.trim(),submittedBase=base;
  for(const control of form.elements)control.disabled=true;
  render(controller.state());
  try{
   const option=await controller.run('create_option',{name:submittedName,base_checkpoint:submittedBase});
   form.hidden=true;newButton.hidden=false;
   await controller.refresh();await controller.switchOption(option.id);setOpen(false);toggle.focus({preventScroll:true});
  }catch(problem){error=problem.message;setOpen(true);}finally{creating=false;for(const control of form.elements)control.disabled=false;render(controller.state());}
 };
 const refresh=()=>void controller.refresh().catch(problem=>{error=problem.message;render(controller.state());});
 window.addEventListener('studprojectchange',event=>{if(!['history_displayed','live_displayed','comparison_complete','plans_complete'].includes(event.detail?.type))refresh();});
 const tools=createComparisonTools(controller);
 Promise.resolve().then(()=>adapter.registerTools?adapter.registerTools(tools):Promise.all(tools.map(tool=>document.modelContext?.registerTool?.(tool)))).catch(problem=>console.warn('stud comparison tools could not register:',problem));
 refresh();
 return {controller,tools,refresh};
}
