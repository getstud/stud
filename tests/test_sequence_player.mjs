import test from 'node:test';
import assert from 'node:assert/strict';
import {createSequencePlayer} from '../web/sequence-player.js';
function fixture(){
 let value=0,time=0,revision='r1',next=0,active=0;const frames=new Map();
 const plan={title:'Demo',revision:'r1',duration:4,start:0,steps:[{label:'First',duration:1,hold:1,end:10},{label:'Second',duration:1,hold:1,end:20}]};
 const player=createSequencePlayer({revision:()=>revision,compile:()=>plan,capture:()=>value,restore:v=>value=v,blend:(a,b,t)=>value=a+(b-a)*t,
  activity:async fn=>{active++;try{await fn(new AbortController().signal);}finally{active--; }},now:()=>time,raf:fn=>{frames.set(++next,fn);return next},caf:id=>frames.delete(id)});
 return {player,get value(){return value},get active(){return active},setValue:v=>value=v,changeRevision:()=>revision='r2',tick:async delta=>{time+=delta;const callbacks=[...frames.values()];frames.clear();callbacks.forEach(fn=>fn(time));await Promise.resolve();await Promise.resolve();}};
}
test('preparation does not play; full sequence owns one activity and replay returns to its start',async()=>{
 const f=fixture();f.player.prepare({});assert.equal(f.active,0);assert.equal(f.value,0);
 f.player.play();await f.tick(500);assert.equal(f.value,5);assert.equal(f.active,1);
 await f.tick(1500);await f.tick(2000);assert.equal(f.value,20);assert.equal(f.player.state().status,'completed');assert.equal(f.active,0);
 f.player.replay();assert.equal(f.value,0);await f.tick(500);assert.equal(f.value,5);f.player.stop();
});
test('pause cancels frames and resume starts from a manual adjustment',async()=>{
 const f=fixture();f.player.prepare({});f.player.play();await f.tick(500);f.player.pause();await f.tick(4000);assert.equal(f.value,5);assert.equal(f.active,0);
 f.setValue(7);f.player.play();await f.tick(250);assert.equal(f.value,8.5);f.player.stop();await f.tick(4000);assert.equal(f.value,8.5);
});
test('revision changes stop animation before touching the changed scene',async()=>{
 const f=fixture();f.player.prepare({});f.player.play();f.changeRevision();await f.tick(500);assert.equal(f.value,0);assert.equal(f.active,0);assert.equal(f.player.state().status,'error');assert.throws(()=>f.player.replay(),/design changed/);
});
test('step navigation stays paused and displays the selected scene',async()=>{
 const f=fixture();f.player.prepare({});f.player.play();await f.tick(500);f.player.seek(1);assert.equal(f.value,20);assert.equal(f.player.state().status,'paused');await f.tick(1000);assert.equal(f.value,20);f.player.seek(-1);assert.equal(f.value,10);
});
test('resume preserves the remaining hold rather than replaying the entire hold',async()=>{
 const f=fixture();f.player.prepare({});f.player.play();await f.tick(1900);f.player.pause();f.player.play();await f.tick(110);assert.equal(f.player.state().step,2);f.player.stop();
});
