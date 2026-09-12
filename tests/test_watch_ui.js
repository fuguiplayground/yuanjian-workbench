// Exercise the shipped page helpers/actions and watch UI without a browser or network.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('web/index.html','utf8');
const inline=html.slice(html.indexOf("'use strict';"),html.indexOf("document.addEventListener('click'"));
const script=fs.readFileSync('web/watch.js','utf8');
function harness(){
 const nodes=new Map(),requests=[],responses=[];
 const node=selector=>{if(!nodes.has(selector))nodes.set(selector,{innerHTML:'',textContent:'',scrollIntoView(){this.scrolled=true}});return nodes.get(selector)};
 const context=vm.createContext({document:{querySelector:node},window:{scrollTo(){}},location:{hash:''},
  setTimeout(){return 1},clearTimeout(){},requestAnimationFrame(){},
  audienceLensWorkspace(){return ''},skillWorkspace(){return ''},inputManifestWorkspace(){return ''},evidenceLedgerWorkspace(){return ''},businessAction:async()=>false,businessWorkspace(){return ''},audienceWorkspace(){return ''},keywordWorkspace(){return ''},insightWorkspace(){return ''},reportWorkspace(){return ''},guide(){return ''},research(){return ''},jobView(){return ''},
  async fetch(path,options){requests.push({path,options});assert.ok(responses.length,'Only an explicit refresh may request history');return responses.shift()(path,options)}});
 vm.runInContext(fs.readFileSync('web/workflow.js','utf8').split('\n').find(x=>x.startsWith('const AUDIENCE_STEPS=')),context);vm.runInContext(script,context);vm.runInContext(inline,context);
 return {context,nodes,requests,responses,run:code=>vm.runInContext(code,context),
  set(p){context.inputProject=p;vm.runInContext("state.project=inputProject;state.page='products';state.query='';state.filter='all';state.sort='default'",context)}};
}
function product(id='B000000001',title='宠物饮水机'){
 return {id,title,asin:id,platform:'amazon',source_url:'https://www.amazon.com/dp/'+id,
  features:['可拆卸'],candidate:false,price:null,currency:'USD',rating:null,review_count:null,
  sales_raw:'',provenance:'live',collected_at:'2026-09-12T00:00:00Z'};
}
function project(id='project-a',items=[product()]){return {id,name:'调研',keyword:'宠物饮水机',revision:7,
 updated_at:'2026-09-12T00:00:00Z',data_version:1,products:items,watch_history:[],demo:false}}
function history(status='success'){
 return {product_id:'B000000001',status,created_at:'2026-09-12T00:00:00Z',finished_at:'2026-09-12T00:01:00Z',
  requests:2,request_limit:2,source:'卖家精灵 MCP',results:[
   {tool:'keepa_info',status:'success',data:{requested_asin:'B000000001',returned_asin:'B000000001',data_asin:'B000000001',skipped_points:3,series:{
    price:[{at:'2026-09-01T00:00:00Z',value:19.99},{at:'2026-09-10T00:00:00Z',value:24.99}],
    bsr:[{at:'2026-09-10T00:00:00Z',value:null}],ratings_count:[],rating:[]}}},
   {tool:'asin_sales_trend',status:'success',data:{requested_asin:'B000000001',returned_asin:'B000000001',skipped_points:2,
    months:[{month:'2026-08',parent_units:3200,child_units:140,average_price:null}]}}]};
}
function renderHistory(h,record){h.context.inputHistory=record;return h.run('historyBody(inputHistory)')}
async function main(){
 const h=harness();h.set(project());
 assert.match(html,/<script src="\/watch.js"><\/script>/);
 assert.equal(h.run("NAV.some(x=>x[0]==='products')"),true);
 assert.equal(h.run("NAV.find(x=>x[0]==='products')[3]"),'资料与工具');
 const watched={...product('B000000002','仅关注商品'),watched:true,candidate:false};
 const candidate={...product('B000000003','仅候选商品'),candidate:true};
 h.set(project('project-a',[watched,candidate]));
 h.run("state.filter='watched'");
 assert.match(h.run('products()'),/data-action="watched"/);
 assert.doesNotMatch(h.run('products()').split('<div class="compare-dock">')[0],/data-id="B000000003"/);
 h.run("state.filter='candidate'");
 assert.doesNotMatch(h.run('products()').split('<div class="compare-dock">')[0],/data-id="B000000002"/);
 h.set(project());
 let view=h.run('marketWatch()');
 assert.match(view,/查看竞品变化/);assert.match(view,/未开启定时监控/);assert.equal(h.requests.length,0);
 await h.run("runAction('product-history',{dataset:{id:'B000000001'}})");
 assert.equal(h.run('watch.productId'),'B000000001');assert.match(h.nodes.get('#content').innerHTML,/读取历史 · 2次查询/);
 assert.match(h.nodes.get('#content').innerHTML,/近 90 天的价格、BSR 与评分记录，以及供应商全部可用月份的销量估算/);
 assert.equal(h.requests.length,0,'Viewing saved/empty history does not consume MCP calls');

 h.context.missingDaily=[{at:'2026-09-01T00:00:00Z',value:null}];
 h.context.monthly=[{month:'2026-07',average_price:25},{month:'2026-08',average_price:29}];
 const fallback=h.run('historyPriceChart(missingDaily,monthly)');
 assert.match(fallback,/月均价格 · USD/);assert.match(fallback,/统计口径不同/);assert.match(fallback,/<svg/);
 assert.equal(h.requests.length,0,'Monthly fallback uses saved values without another request');
 let resolve;h.responses.push(()=>new Promise(r=>{resolve=r}));
 const pending=h.run("watchAction('refresh-product-history',{dataset:{id:'B000000001'}})");
 assert.equal(h.requests.length,1);assert.equal(h.requests[0].path,'/api/projects/project-a/product-history');
 assert.equal(h.requests[0].options.method,'POST');
 assert.deepEqual(JSON.parse(h.requests[0].options.body),{revision:7,product_id:'B000000001'});
 await h.run("watchAction('refresh-product-history',{dataset:{id:'B000000001'}})");
 assert.equal(h.requests.length,1,'A double click does not duplicate queries');
 const saved=project();saved.revision=8;saved.watch_history=[history()];resolve({ok:true,json:async()=>saved});await pending;
 assert.equal(h.run('state.project.revision'),8);assert.equal(h.run('watch.busy'),false);
 assert.match(h.nodes.get('#content').innerHTML,/更新趋势 · 2次查询/);

 h.responses.push(()=>new Promise(r=>{resolve=r}));
 const old=h.run("watchAction('refresh-product-history',{dataset:{id:'B000000001'}})");
 const other=project('project-b',[product('B000000002','另一个项目的商品')]);h.set(other);
 h.run("watch.productId='B000000002';render()");
 assert.match(h.nodes.get('#content').innerHTML,/正在查询/);
 resolve({ok:true,json:async()=>saved});await old;
 assert.equal(h.run('state.project.id'),'project-b');assert.equal(h.run('state.project.revision'),7);
 assert.match(h.nodes.get('#content').innerHTML,/另一个项目的商品/);
 assert.doesNotMatch(h.nodes.get('#content').innerHTML,/正在查询…/,'The new project is re-rendered when the old request unlocks');

 const partial=history('partial');partial.results[1]={tool:'asin_sales_trend',status:'failed',error:'供应商限流，请稍后再试',http:429};
 view=renderHistory(h,partial);assert.match(view,/部分结果已保存/);assert.match(view,/供应商限流/);assert.match(view,/HTTP 429/);assert.match(view,/24\.99/);
 assert.match(view,/跳过异常、重复或超出范围时间点 3 个/);assert.match(view,/保留缺失值时间点 1 个/);
 const missing=history();missing.results[0].data.series.price=[{at:'2026-09-10',value:null}];
 view=renderHistory(h,missing);assert.match(view,/<strong>未提供<\/strong><span>最新记录价格/);
 assert.match(view,/<strong>未提供<\/strong><span>BSR 排名/);assert.doesNotMatch(view,/<strong>0<\/strong>/);
 assert.match(view,/<th>父体月销量<\/th><th>子体月销量<\/th>/);
 assert.match(view,/<td>3,200<\/td><td>140<\/td><td>未提供<\/td>/);
 assert.match(view,/供应商全部可用月份，不限于近 90 天/);
 assert.match(view,/跳过异常或重复月份 2 个/);assert.match(view,/当前表格缺失值 1 项/);
 assert.equal(h.run('watchValue(0)'), '0');assert.equal(h.run('watchValue(null)'),'未提供');assert.equal(h.run('watchValue(NaN)'),'未提供');

 for(const field of ['data_asin','returned_asin']){
  const mismatch=history();mismatch.results[0].data[field]='B000000099';
  view=renderHistory(h,mismatch);assert.match(view,/供应商返回关联商品 B000000099/);assert.match(view,/不能直接作为所选商品的走势/);
 }
 const mismatch=history();mismatch.results[1].data.returned_asin='B000000088';
 assert.match(renderHistory(h,mismatch),/销量返回商品 B000000088 与查询商品不同/);

 const attack='<img src=x onerror="alert(1)">';
 const injected=history('partial');injected.source=attack;injected.requests=attack;
 injected.results[0].data.data_asin=attack;injected.results[1]={tool:'asin_sales_trend',status:'failed',error:attack,http:500};
 view=renderHistory(h,injected);assert.doesNotMatch(view,/<img/);assert.match(view,/&lt;img src=x onerror=&quot;alert\(1\)&quot;&gt;/);
 const escaped=project('project-c',[product('B000000001',attack)]);escaped.watch_history=[injected];h.set(escaped);h.run("watch.productId='B000000001'");
 escaped.products[0].features=[attack];escaped.products[0].sales_raw=attack;escaped.products[0].source_url='https://example.test/"<img src=x>';
 assert.doesNotMatch(h.run('marketWatch()'),/<img/);assert.doesNotMatch(h.run('watchReportHtml()'),/<img/);
 assert.equal(h.requests.length,2,'Rendering/report export never makes extra requests');
 h.responses.push(async()=>({ok:false,json:async()=>({error:'供应商暂不可用'})}));
 await assert.rejects(h.run("watchAction('refresh-product-history',{dataset:{id:'B000000001'}})"),/供应商暂不可用/);
 assert.equal(h.run('watch.busy'),false);assert.doesNotMatch(h.nodes.get('#content').innerHTML,/正在查询…/);
 console.log('Watch UI: explicit queries, project switching, partial results, null values, ASIN provenance and escaping verified.');
}
main().catch(error=>{console.error(error);process.exitCode=1});
