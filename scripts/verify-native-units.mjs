// Verify actual browser geometry, labels and native-region focus in both units.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const {chromium}=await import(process.env.STUD_PLAYWRIGHT_MODULE||'playwright');
const python=process.env.STUD_PYTHON||path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
const output=path.join(root,'docs/evidence'),results=[];
await mkdir(output,{recursive:true});
const browser=await chromium.launch({headless:true,...(process.env.STUD_CHROME?{executablePath:process.env.STUD_CHROME}:{}),args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const near=(actual,expected)=>assert(Math.abs(actual-expected)<1e-4,`${actual} != ${expected}`);
try{
 for(const units of ['in','mm']){
  const server=spawn(python,['-B','scripts/native-units-fixture.py',units],{cwd:root,stdio:['ignore','pipe','pipe']});
  let stderr='',page;
  server.stderr.on('data',data=>stderr+=data);
  try{
   const info=await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(new Error('Fixture timed out: '+stderr)),90000);
    createInterface({input:server.stdout}).on('line',line=>{if(line.startsWith('READY ')){clearTimeout(timer);resolve(JSON.parse(line.slice(6)));}});
    server.once('exit',code=>{clearTimeout(timer);reject(new Error(`Fixture exited ${code}: ${stderr}`));});
   });
   page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];
   page.on('pageerror',error=>errors.push(String(error)));
   await page.goto(info.url);await page.waitForFunction(()=>window.stud?.visibleCount===1);
   await page.getByRole('button',{name:'Expand Frame',exact:true}).click();
   await page.locator('[data-id="board"]').click();
   const inspector=await page.locator('#inspector').innerText(),footer=await page.locator('#viewlabel').innerText();
   assert(footer.endsWith(units==='mm'?'MILLIMETERS':'INCHES'),footer);
   for(const value of units==='mm'?['38.1 mm','88.9 mm','609.6 mm']:['1.5″','3.5″','24″'])assert(inspector.includes(value),inspector);
   assert(!inspector.includes(units==='mm'?'″':' mm'),inspector);
   const geometry=await page.evaluate(async()=>{
    const THREE=await import('three'),{CadScene}=await import('/cad-scene.js');
    const group=new THREE.Group(),scene=new CadScene({THREE,group});
    const apply=await scene.prepare(window.stud.model);apply();group.updateMatrixWorld(true);
    const box=new THREE.Box3().setFromObject(scene.objects.get('board'));
    const result={units:window.stud.model.display_units,part_units:window.stud.model.parts[0].cad.units,min:box.min.toArray(),max:box.max.toArray(),dimensions:window.stud.model.dimensions};
    scene.dispose();return result;
   });
   assert.equal(geometry.units,units);assert.equal(geometry.part_units,units);
   geometry.min.forEach((v,i)=>near(v,[10,0,-23.5][i]));geometry.max.forEach((v,i)=>near(v,[11.5,24,-20][i]));
   const scale=units==='in'?1:25.4;
   const payload={operation:'show',key:crypto.randomUUID(),arguments:{expected_build:await page.evaluate(()=>window.stud.model.cad.build_id),
    region:{min:[10,20,0].map(v=>v*scale),max:[11.5,23.5,24].map(v=>v*scale)}}};
   const response=await fetch(info.url+'/api/v1/command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
   const show=await response.json();assert(response.ok,JSON.stringify(show));
   let acknowledged=false;
   for(let i=0;i<150;i++){
    const job=await (await fetch(info.url+'/api/v1/jobs/'+show.id)).json();
    if(job.status==='complete'){acknowledged=true;break;}await page.waitForTimeout(100);
   }
   assert(acknowledged,'Native-unit focus was acknowledged');
   const camera=await page.evaluate(()=>window.stud.camera);camera.target.forEach((v,i)=>near(v,[10.75,12,-21.75][i]));
   await page.locator('[data-id="board"]').click();
   await page.screenshot({path:path.join(output,`native-units-${units}.png`)});
   assert.deepEqual(errors,[]);results.push({units,project:info.root,geometry,inspector,footer,focus_acknowledged:true,camera,errors});
  }finally{
   await page?.close();server.kill('SIGINT');
   await new Promise(resolve=>{if(server.exitCode!==null)return resolve();const timer=setTimeout(resolve,5000);server.once('exit',()=>{clearTimeout(timer);resolve();});});
  }
 }
 await writeFile(path.join(output,'native-units-browser.json'),JSON.stringify({status:'passed',results},null,2)+'\n');
 console.log(JSON.stringify({status:'passed',units:results.map(r=>r.units),physical_bounds_equal:true,native_focus:true}));
}finally{await browser.close();}
