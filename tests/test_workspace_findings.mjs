import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../web/app.js',import.meta.url),'utf8');
const workspaceFindings=vm.runInNewContext(source.slice(source.indexOf('function workspaceFindings('),source.indexOf('function renderValidation('))+';workspaceFindings');
test('general coverage and author notes do not become workspace warnings',()=>{
 const findings=[
  {status:'UNVERIFIED',rule:'coverage',parts:[],message:'No geometry rules declared.'},
  {status:'UNVERIFIED',rule:'preview.connections',message:'Connections are not specified.'},
  {status:'PASS',rule:'stock_fit',parts:['rail']},
 ];
 assert.equal(workspaceFindings({findings}).length,0);
 assert.equal(workspaceFindings({}).length,0);
});
test('actual failures and part-specific gaps remain visible',()=>{
 const findings=[
  {status:'FAIL',rule:'configuration',parts:[],message:'Invalid check configuration.'},
  {status:'FAIL',rule:'solid_collision',parts:['rail','leg']},
  {status:'WARNING',rule:'contact',parts:['rail']},
  {status:'UNVERIFIED',rule:'connection',parts:['rail','leg'],message:'Select a connector for this joint.'},
 ];
 assert.deepEqual(workspaceFindings({findings}),findings);
});
