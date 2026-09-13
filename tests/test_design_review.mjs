import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';

test('design evidence status follows the displayed revision and clears for older projections',()=>{
 const source=readFileSync(new URL('../web/app.js',import.meta.url),'utf8');
 const elements=new Map();
 const $=id=>{
  if(!elements.has(id))elements.set(id,{hidden:false,textContent:'',classList:{toggle(){}},replaceChildren(){},setAttribute(){}});
  return elements.get(id);
 };
 const render=runInNewContext(source.slice(source.indexOf('function renderValidation('),source.indexOf('function stopViewerMotion('))+'\nrenderValidation',{
  $,validationReport:null,workspaceFindings:()=>[],renderWarningAnnotations(){},clearValidationHighlights(){},
 });
 render({revision:'a',design_review:{summary:'Geometry verified. Design details remain unresolved.'}});
 assert.equal($('design-review-status').textContent,'Geometry verified. Design details remain unresolved.');
 assert.equal($('design-review-status').hidden,false);
 render({revision:'b',design_review:{summary:'Geometry not fully verified.'}});
 assert.equal($('design-review-status').textContent,'Geometry not fully verified.');
 render({revision:'older'});
 assert.equal($('design-review-status').textContent,'');
 assert.equal($('design-review-status').hidden,true);
});
