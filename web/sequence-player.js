// A local timeline: tools prepare/control it, but no tool call stays open during playback.
export function createSequencePlayer({revision,compile,capture,restore,blend,activity,onChange=()=>{},now=()=>performance.now(),raf=requestAnimationFrame,caf=cancelAnimationFrame}){
 let plan=null,status='empty',index=0,elapsed=0,frame=null,last=0,release=null,generation=0,error=null,from=null,duration=0,hold=0,pausedSnapshot=null;
 const state=()=>({status,title:plan?.title||'',step:index+1,steps:plan?.steps.length||0,label:plan?.steps[index]?.label||'',caption:plan?.steps[index]?.caption||'',duration:plan?.duration||0,error});
 const publish=()=>onChange(state());
 function halt(){generation++;if(frame!==null)caf(frame);frame=null;release?.();release=null;}
 function guard(){if(!plan)throw Error('Prepare a sequence first.');if(plan.revision!==revision())throw Error('The design changed. Prepare the sequence again.');}
 function beginStep(){from=capture();duration=plan.steps[index].duration;hold=plan.steps[index].hold;elapsed=0;}
 function tick(time){
  try{
   guard();const step=plan.steps[index];elapsed+=Math.max(0,time-last);last=time;
   const t=duration?Math.min(1,elapsed/(duration*1000)):1;
   blend(from,step.end,t*t*(3-2*t));
   if(elapsed>=(duration+hold)*1000){
    restore(step.end);
    if(index===plan.steps.length-1){halt();status='completed';publish();return;}
    index++;beginStep();publish();
   }
   frame=raf(tick);
  }catch(e){halt();status='error';error=e.message;publish();}
 }
 function play(){
  guard();if(status==='playing')return state();
  if(status==='completed'||status==='stopped'){index=0;restore(plan.start);beginStep();}
  // Resume from the current view, including any manual camera adjustment.
  else if(status==='paused'){hold=Math.max(0,hold-Math.max(0,elapsed/1000-duration));const current=capture(),adjusted=JSON.stringify(current)!==JSON.stringify(pausedSnapshot);const remaining=Math.max(adjusted&&!plan.reducedMotion ? .3 : 0,duration-elapsed/1000);from=current;duration=remaining;elapsed=0;}
  else beginStep();
  status='playing';error=null;const token=++generation;publish();
  activity(async signal=>{
   if(token!==generation)return;
   await new Promise(resolve=>{
    const abort=()=>{if(token===generation){halt();status='stopped';publish();}resolve();};
    release=()=>{signal?.removeEventListener('abort',abort);resolve();};
    if(signal?.aborted){abort();return;}
    signal?.addEventListener('abort',abort,{once:true});last=now();frame=raf(tick);
   });
  }).catch(e=>{if(token===generation){halt();status='error';error=e.message;publish();}});
  return state();
 }
 const player={state,
  prepare(input){if(status==='playing')player.pause();const candidate=compile(input);halt();plan=candidate;index=0;elapsed=0;status='ready';error=null;publish();return state();},
  play,
  dismiss(){halt();plan=null;status='empty';error=null;publish();return state();},
  pause(){if(status==='playing'){halt();pausedSnapshot=capture();status='paused';publish();}return state();},
  stop(){halt();if(plan)status='stopped';publish();return state();},
  replay(){guard();halt();index=0;restore(plan.start);status='ready';return play();},
  seek(delta){guard();halt();index=Math.max(0,Math.min(plan.steps.length-1,index+delta));restore(plan.steps[index].end);beginStep();duration=0;pausedSnapshot=capture();status='paused';publish();return state();},
 };
 return player;
}
