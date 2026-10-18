/* Pass-through observations only: the buffer already contains original DSP. */
class ReviewClock extends AudioWorkletProcessor{
 constructor(){super();this.events=[];this.maximum=0;this.port.onmessage=({data})=>{if(data.kind==='arm'){this.events=data.events;this.maximum=0}if(data.kind==='clear')this.events=[]}}
 process(inputs,outputs){const input=inputs[0],output=outputs[0],n=output[0].length;for(let c=0;c<output.length;c++){for(let j=0;j<n;j++){const v=input[c]?.[j]??0;output[c][j]=v;this.maximum=Math.max(this.maximum,Math.abs(v))}}for(let i=this.events.length-1;i>=0;i--){const e=this.events[i];if(e.frame<currentFrame+n){this.port.postMessage({...e,observedFrame:currentFrame+n,late:Math.max(0,currentFrame-e.frame),peak:this.maximum});this.events.splice(i,1)}}return true}
}
registerProcessor('review-clock',ReviewClock)
