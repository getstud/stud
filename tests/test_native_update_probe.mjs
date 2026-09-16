import {test} from 'node:test';
import assert from 'node:assert/strict';
import {waitForUpdatedCli} from '../scripts/native-update-probe.mjs';

test('update readiness never launches a CLI while its installer is active',async()=>{
  let installing=true,launches=0;
  const result=await waitForUpdatedCli(()=>{
    assert.equal(installing,false,'The CLI must not compete for the runtime lock');
    launches++;
    return {status:0,stdout:'stud 1.0.0-preview.11\n'};
  },'stud 1.0.0-preview.11',{
    installers:()=>installing?[{ProcessId:123,Name:'setup.exe'}]:[],
    pause:async()=>{installing=false;},
  });
  assert.equal(launches,1);
  assert.equal(result.installerProcessObservations,1);
});

test('an old CLI version cannot satisfy readiness and appears in timeout evidence',async()=>{
  await assert.rejects(waitForUpdatedCli(()=>({status:0,stdout:'stud 1.0.0-preview.8\n',stderr:''}),
    'stud 1.0.0-preview.11',{timeout:0}),/preview\.8/);
});

test('installer lock remains a retry condition after the installer process exits',async()=>{
  let calls=0;
  const result=await waitForUpdatedCli(()=>++calls===1
    ?{status:1,stdout:'',stderr:'stud is being updated.'}
    :{status:0,stdout:'stud 1.0.0-preview.11'},'stud 1.0.0-preview.11',{pause:async()=>{}});
  assert.equal(result.installerLockObservations,1);
  assert.equal(calls,2);
});
