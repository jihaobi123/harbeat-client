/* Audio-thread observation + 5ms lookahead protection. Not FFmpeg alimiter. */
class V3Clock extends AudioWorkletProcessor{
 constructor(){super();this.events=[];this.delay=Math.ceil(sampleRate*.005);this.size=this.delay+2;this.ring=[new Float32Array(this.size),new Float32Array(this.size)];this.peaks=new Float32Array(this.size*2);this.indices=new Float64Array(this.size*2);this.head=0;this.tail=0;this.count=0;this.gain=1;this.maximum=0;this.port.onmessage=({data})=>{if(data.kind==='arm')this.events.push(...data.events);if(data.kind==='cancel')this.events=this.events.filter(x=>x.planId!==data.planId);if(data.kind==='clear')this.events=[]}}
 process(inputs,outputs){
  const output=outputs[0],input=inputs[0],n=output[0].length;const capacity=this.peaks.length
  for(let j=0;j<n;j++){
   const l=input[0]?.[j]||0,r=input[1]?.[j]??l,p=Math.max(Math.abs(l),Math.abs(r));const count=this.count++,slot=count%this.size
   this.ring[0][slot]=l;this.ring[1][slot]=r
   while(this.tail>this.head&&this.peaks[(this.tail-1)%capacity]<=p)this.tail--
   this.peaks[this.tail%capacity]=p;this.indices[this.tail%capacity]=count;this.tail++
   while(this.head<this.tail&&this.indices[this.head%capacity]<count-this.delay)this.head++
   const target=Math.min(1,.96/Math.max(.0001,this.peaks[this.head%capacity]));this.gain=target<this.gain?target:Math.min(target,this.gain+1/(sampleRate*.05))
   const at=(count-this.delay+this.size)%this.size
   for(let c=0;c<output.length;c++)output[c][j]=count>=this.delay?this.ring[Math.min(c,1)][at]*this.gain:0
   this.maximum=Math.max(this.maximum,Math.abs(output[0][j]))
  }
  for(let i=this.events.length-1;i>=0;i--){const e=this.events[i];if(e.frame<currentFrame+n){this.port.postMessage({...e,observedFrame:currentFrame+n,quantumStart:currentFrame,quantumFrames:n,late:Math.max(0,currentFrame-e.frame),limiterDelayFrames:this.delay,peak:this.maximum});this.events.splice(i,1)}}
  return true
 }
}
registerProcessor('v3-clock',V3Clock)
