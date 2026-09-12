// Actual collection controls: requests, caps, round selection and IME-safe updates.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const handlers={},nodes=new Map(),calls=[];let renders=0;
const el=(id,value)=>{const node={id,value,disabled:false,textContent:''};nodes.set('#'+id,node);return node};
const mode=el('mode','intent'),rounds=el('quick-keyword-rounds','3'),limit=el('quick-keyword-limit','31');
el('quick-keyword-budget','');el('quick-keyword-description','');
const context=vm.createContext({
 document:{addEventListener(k,fn){(handlers[k]??=[]).push(fn)},querySelector(s){return s.includes(':checked')?mode:nodes.get(s)},querySelectorAll(){return [{value:'xhs'},{value:'amazon'}]}},
 state:{project:{id:'project',keyword:'宠物饮水机',revision:1},selected:new Set(),composing:false},
 render(){renders++},collectionJob:null,collectionPoll:null,clearTimeout(){},location:{hash:''},
 api:async(path,body)=>{calls.push({path,body});return {run:{status:'success'}}},pollCollection:async()=>{},
 esc:s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'),toast(){},
});
for(const file of ['web/keyword-controls.js','web/research.js'])vm.runInContext(fs.readFileSync(file,'utf8'),context);
const run=s=>vm.runInContext(s,context),plain=x=>JSON.parse(JSON.stringify(x));
const fire=(type,target)=>(handlers[type]||[]).forEach(fn=>fn({target}));
(async()=>{
 assert.deepEqual(plain(run("keywordBudget({keyword_mode:'quick'},['宠物饮水机'],['xhs','tiktok','reddit','amazon'])")),{total:5,tikhub:4,mcp:1,translation:1});
 assert.deepEqual(plain(run("keywordBudget({keyword_mode:'az',request_limit:9},['宠物饮水机'],['xhs','tiktok','reddit','amazon'])")),{total:9,tikhub:7,mcp:2,translation:1});
 assert.match(run("keywordBudgetText({keyword_mode:'az',rounds:6,request_limit:200},['fountain'],['xhs'])"),/不保证完成全部扩词/);
 run("quick.query='宠物饮水机';quick.platforms=['xhs','amazon']");
 await run("quickStart('keywords')");
 assert.equal(calls.length,1);assert.deepEqual(plain(calls[0].body),{revision:1,kind:'keywords',platforms:['xhs','amazon'],queries:['宠物饮水机'],pages:1,keyword_mode:'intent',rounds:3,request_limit:31});
 for(const invalid of ['0','501','2.5','']){limit.value=invalid;const before=calls.length;await assert.rejects(run("quickStart('keywords')"),/1 至 500/);assert.equal(calls.length,before)}
 limit.value='31';rounds.value='7';await assert.rejects(run("quickStart('keywords')"),/1 至 6/);
 mode.value='quick';run("refreshKeywordControls('quick')");assert.equal(rounds.value,'1');assert.equal(rounds.disabled,true);assert.equal(limit.disabled,true);
 await run("quickStart('keywords')");assert.equal(calls.at(-1).body.rounds,1);assert.equal('request_limit' in calls.at(-1).body,false);
 mode.value='az';run("refreshKeywordControls('quick')");assert.equal(rounds.value,'2');assert.equal(rounds.disabled,false);
 const before=renders;fire('input',{id:'quick-query',value:'饮水机清洗'});assert.equal(renders,before);assert.equal(run('quick.query'),'饮水机清洗');
 const html=run("keywordRoundsHtml({keyword_mode:'az',rounds:2,capped:true,round_results:[{platform:'<script>',round:2,queries:3,new_keywords:2,duplicates:1,status:'capped'}]})");
 assert.match(html,/预算停止/);assert.match(html,/&lt;script&gt;/);assert.equal(html.includes('<script>'),false);
 console.log('Keyword controls: actual start payloads, quick and advanced caps, defaults, IME-safe input and escaped per-round details passed.');
})().catch(error=>{console.error(error);process.exitCode=1});
