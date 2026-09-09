export function placeAnnotation(x,y,width,height,occupied,size=32){
 const edge=size/2+4,clamp=(v,max)=>Math.max(edge,Math.min(max-edge,v));
 for(let ring=0;ring<12;ring++){
  const count=ring?ring*8:1;
  for(let i=0;i<count;i++){
   const angle=i/count*Math.PI*2;
   const p={x:clamp(x+Math.cos(angle)*ring*size,width),y:clamp(y+Math.sin(angle)*ring*size,height)};
   if(occupied.every(q=>Math.hypot(q.x-p.x,q.y-p.y)>=size)){occupied.push(p);return p;}
  }
 }
 return null;
}
export function editorPosition(anchor,width,height,windowWidth,windowHeight){
 return {left:Math.max(16,Math.min(anchor.left,windowWidth-width-16)),top:Math.max(16,Math.min(anchor.bottom+8,windowHeight-height-16))};
}
