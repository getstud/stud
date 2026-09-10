// Ordered delivery with explicit snapshot recovery. Geometry stays in assets.
export class ProjectEvents {
  constructor({onEvent,onReset,onError=()=>{}}){this.onEvent=onEvent;this.onReset=onReset;this.onError=onError;this.sequence=0;this.source=null;this.generation=0;}
  async connect(){
    const generation=++this.generation;this.source?.close();
    const response=await fetch('/api/v1/status',{cache:'no-store'});
    if(!response.ok)return false; // Existing projects keep their legacy adapter.
    const snapshot=await response.json();if(generation!==this.generation)return false;
    this.sequence=snapshot.sequence;this.onReset(snapshot);
    this.source=new EventSource(`/api/v1/events?after=${this.sequence}`);
    this.source.addEventListener('reset',event=>{
      if(generation!==this.generation)return;
      const snapshot=JSON.parse(event.data);this.sequence=snapshot.sequence;this.onReset(snapshot);
    });
    this.source.addEventListener('project',event=>{if(generation===this.generation)this.accept(JSON.parse(event.data));});
    this.source.onerror=()=>this.onError('Reconnecting to project events…');
    return true;
  }
  accept(event){
    if(event.sequence<=this.sequence)return false;
    if(event.sequence!==this.sequence+1){
      this.source?.close();void this.connect();return false;
    }
    this.sequence=event.sequence;this.onEvent(event);return true;
  }
  close(){this.generation++;this.source?.close();}
}
