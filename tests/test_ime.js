// Exercise the actual input handlers with composition events and controlled timers.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('web/index.html','utf8');
const handlers={},timers=new Map();let timerId=0,renders=0,searches=0;
const input={id:'search-input',value:'',selectionStart:0,isConnected:true,focus(){},setSelectionRange(a){this.selectionStart=a}};
const context=vm.createContext({state:{composing:false,query:'',selected:new Set()},
 document:{addEventListener(k,fn){(handlers[k]??=[]).push(fn)},querySelector(){return input}},
 render(){renders++},setTimeout(fn){timers.set(++timerId,fn);return timerId},clearTimeout(id){timers.delete(id)},toast(){}});
vm.runInContext(html.slice(html.indexOf('let searchUpdateTimer;'),html.indexOf("document.addEventListener('change',event=>")),context);
vm.runInContext(fs.readFileSync('web/keyword-controls.js','utf8'),context);
vm.runInContext(fs.readFileSync('web/research.js','utf8'),context);
// Override in the same lexical context used by the registered keyboard listener.
context.__search=()=>searches++;
vm.runInContext('quickStart=async()=>{__search()}',context);
const fire=(type,extra={})=>(handlers[type]||[]).forEach(fn=>fn({target:input,...extra}));
const flush=()=>{const pending=[...timers.values()];timers.clear();pending.forEach(fn=>fn())};
fire('compositionstart');input.value='bian';fire('input',{isComposing:true});flush();
assert.equal(renders,0);assert.equal(context.state.query,'');
input.value='便携榨汁杯';input.selectionStart=5;fire('compositionend');fire('input',{isComposing:false});flush();
assert.equal(renders,1);assert.equal(context.state.query,'便携榨汁杯');assert.equal(input.selectionStart,5);
input.id='quick-query';fire('compositionstart');fire('input',{isComposing:true});
fire('keydown',{key:'Enter',isComposing:true,preventDefault(){}});assert.equal(searches,0);
fire('compositionend');fire('keydown',{key:'Enter',isComposing:false,preventDefault(){}});assert.equal(searches,1);
console.log('IME: composition preserves input; committed Chinese filters once; composing Enter does not search.');
