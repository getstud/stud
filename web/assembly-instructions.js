// Fabrication dimensions come from stock metadata, never projected envelopes.
export function workshopInches(value){
 const sign=value<0?'−':'',absolute=Math.abs(value),whole=Math.floor(absolute),eighth=Math.round((absolute-whole)*8);
 if(Math.abs(absolute*8-Math.round(absolute*8))>1e-5)return `${Number(value.toFixed(3))}″`;
 if(eighth===8)return `${sign}${whole+1}″`;
 return `${sign}${whole||!eighth?whole:''}${['','⅛','¼','⅜','½','⅝','¾','⅞'][eighth]}″`;
}
export function cutSpecification(part,stock={}){
 const format=value=>part.cad?.units==='mm'?`${Number((value*25.4).toFixed(3))} mm`:workshopInches(value);
 const blank=part.blank_size||part.size;
 const shaped=part.cad?part.cad.operations.some(operation=>!['square_cut','panel_cut'].includes(operation.kind)):!!(part.profile||part.outline||part.seats||part.blank_size);
 if(Number.isFinite(part.cut_length)&&part.cut_length>0){
  const axis=blank.findIndex((length,i)=>Math.abs(length-part.cut_length)<1e-5&&(!stock.section||blank.filter((_,j)=>j!==i).sort((a,b)=>a-b).every((v,j)=>Math.abs(v-[...stock.section].sort((a,b)=>a-b)[j])<1e-5)));
  return {kind:'lumber',axis,length:part.cut_length,shaped,text:`${format(part.cut_length)} ${shaped?'blank':'cut'}`};
 }
 if(stock.sheet){
  const thicknessAxis=Number.isFinite(stock.sheet_thickness)?blank.findIndex(v=>Math.abs(v-stock.sheet_thickness)<1e-5):-1;
  const size=thicknessAxis<0?blank:blank.filter((_,i)=>i!==thicknessAxis);
  return {kind:'sheet',axis:-1,shaped,text:`${size.map(format).join(' × ')} ${shaped?'blank':'cut'}`};
 }
 return {kind:'part',axis:-1,shaped,text:stock.product?'Purchased part':'See part details'};
}
export function mountingLevel(value){return Number(value.toFixed(4));}
export function groupAssemblyCuts(records,stocks){
 const groups=new Map();
 for(const record of records){
  const p=record.part,spec=cutSpecification(p,stocks[p.stock]);
  // Equal blank lengths do not make different profiles interchangeable.
  const key=JSON.stringify([p.stock,spec.kind,spec.text,p.profile,p.outline,p.seats,p.blank_size,p.cad?.operations,p.cad?.shape_key]);
  if(!groups.has(key))groups.set(key,{spec,stock:p.stock,records:[]});
  groups.get(key).records.push(record);
 }
 return [...groups.values()].map((group,i)=>({...group,mark:group.records[0].part.cad?group.records.map(record=>record.part.mark).join(', '):i<26?String.fromCharCode(65+i):String(i+1)}));
}
