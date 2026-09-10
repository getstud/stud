import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
test('spreadsheet rows use the estimate returned by the preceding queued save',async()=>{
 const source=fs.readFileSync('web/app.js','utf8');const calls=[];
 const context=vm.createContext({model:{cad:{build_id:'b1'}},estimate:{estimate_id:'e1'},crypto:{randomUUID:()=>String(calls.length)},priceQueue:Promise.resolve(),priceEdits:new Map(),rowStatus(){},renderPrices(data){context.estimate=data;},priceRequest:async payload=>{calls.push(payload);assert.equal(payload.expected_estimate,'e'+calls.length);return {estimate_id:'e'+(calls.length+1)};}});
 vm.runInContext(source.slice(source.indexOf('function enqueuePrice('),source.indexOf('async function priceRequest(')),context);
 vm.runInContext("enqueuePrice('a',{key:'a',unit_price:8});enqueuePrice('b',{key:'b',unit_price:9});",context);
 await context.priceQueue;assert.equal(calls.length,2);assert(calls.every(p=>p.expected_build==='b1'));
});
