// Run the real workflow handlers; only browser primitives and HTTP are replaced.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const ROOT = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(ROOT, file), 'utf8');
const clone = value => JSON.parse(JSON.stringify(value));
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const unescape = value => value.replace(/&(amp|lt|gt|quot|#39);/g, (_, name) => ({amp:'&',lt:'<',gt:'>',quot:'"','#39':"'"}[name]));

function fixture() {
  return {id:'project-a', revision:4, data_version:2, name:'饮水机调研', keyword:'宠物饮水机', demo:false,
    keywords:[{id:'k1',text:'饮水机清洗',translation:'',platform:'xhs'}, {id:'k2',text:'cat fountain cleaning',translation:'',platform:'reddit'}],
    posts:[{id:'p1',title:'Cleaning a fountain',body:'Original post',platform:'reddit'}],
    reviews:[{id:'r1',body:'Hard to clean',platform:'reddit',post_id:'p1'}], products:[], runs:[], ai_reports:[], analyses:[], watch_history:[]};
}

function harness(initial = fixture()) {
  const calls = [], downloads = [], listeners = {}, fields = {}, checked = {}, timers = new Map();
  let database = initial ? clone(initial) : null, sequence = 0, collection = null, ai = null, lastModal = null;
  const state = {project:initial ? clone(initial) : null, selected:new Set(), composing:false, modal:false, page:'research', query:'', filter:'all'};
  const context = vm.createContext({state, location:{hash:''}, console,
    document:{activeElement:null, addEventListener(type, fn){(listeners[type] ??= []).push(fn)},
      querySelector(selector){return fields[selector] || null}, getElementById(id){return fields['#'+id] || null},
      querySelectorAll(selector){const name = selector.match(/name="([^"]+)"/)?.[1]; return checked[name] || []}},
    setTimeout(fn){timers.set(++sequence,fn);return sequence}, clearTimeout(id){timers.delete(id)},
    render(){}, toast(){}, icon(){return ''}, date(value){return value || ''}, source(){return ''}, demoNote(){return ''},
    external(url){return url?`<a href="${escape(url)}">来源</a>`:''},
    reviewBlock(row){return `<p>${escape(row.body)}</p>`},
    download(name,body,type){downloads.push({name,body,type})},
    esc:escape, head(title, subtitle, actions=''){return `<h1>${escape(title)}</h1><p>${escape(subtitle)}</p>${actions}`},
    button(label, action, icon='', style='', attrs=''){return `<button data-action="${action}" ${attrs}>${escape(label)}</button>`},
    empty(title, subtitle, action=''){return `<p>${escape(title)} ${escape(subtitle)}</p>${action}`},
    goto(page){state.page=page;state.selected.clear();context.location.hash=page+'?project='+state.project.id},
    closeModal(){state.modal=false},
    modal(title, html, footer=''){
      state.modal=true;
      lastModal={title,html,footer};
      for (const name of Object.keys(checked)) if (name.startsWith('collect-')) delete checked[name];
      for (const input of html.matchAll(/<input\b[^>]*>/g)) {
        const name=input[0].match(/name="([^"]+)"/)?.[1], value=input[0].match(/value="([^"]*)"/)?.[1];
        if (name && /\bchecked\b/.test(input[0])) (checked[name] ??= []).push({value:unescape(value || '')});
      }
      for (const textarea of html.matchAll(/<textarea[^>]*id="([^"]+)"[^>]*>([\s\S]*?)<\/textarea>/g)) fields['#'+textarea[1]]={value:unescape(textarea[2])};
      for (const select of html.matchAll(/<select[^>]*id="([^"]+)"[^>]*>([\s\S]*?)<\/select>/g)) {
        const options=[...select[2].matchAll(/<option([^>]*)>([^<]*)<\/option>/g)], chosen=options.find(x=>/\bselected\b/.test(x[1])) || options[0];
        fields['#'+select[1]]={value:chosen?.[1].match(/value="([^"]*)"/)?.[1] || chosen?.[2] || ''};
      }
      fields['#collect-budget']={textContent:''};
    },
    async api(url, body){
      calls.push({url,body:body === undefined ? undefined : clone(body)});
      if (url==='/api/projects' && body) {database=fixture();database.keywords=[];database.reviews=[];database.posts=[];database.name=body.name;database.keyword=body.keyword;return clone(database)}
      if (url.endsWith('/collect') && body) {
        collection={id:'collect-1',project_id:database.id,run:{kind:body.kind,platforms:body.platforms,status:'success',imported:2,errors:[],requests:2,request_limit:2,pages:2,duplicates:0}};
        if (body.kind==='keywords' && !database.keywords.length) database.keywords=fixture().keywords;
        database.revision++;database.runs.push(clone(collection.run));return clone(collection);
      }
      if (url.startsWith('/api/jobs/')) return clone(collection);
      if (url.endsWith('/ai') && body) {
        ai={id:'ai-1',project_id:database.id,kind:body.kind,target:body.target,status:'success',message:'已完成'};
        if (body.kind==='keywords') database.ai_reports.push({id:'report-1',kind:'keywords',status:'success',data_version:database.data_version,
          scope:{processed:2,total:2,evidence_ids:['keywords:k1','keywords:k2']},report:{title:'饮水机关键词报告',summary:'用户在寻找清洗方式。',items:[],findings:[],next_steps:[]}});
        return clone(ai);
      }
      if (url.startsWith('/api/ai/jobs/')) return clone(ai);
      if (url==='/api/projects/'+database?.id) return clone(database);
      throw Error('Unexpected request: '+url);
    }
  });
  const html=read('web/index.html');
  for (const prefix of ['const money=', 'function latest(', 'function stale(', 'function staleNote(']) {
    const definition=html.split('\n').find(line=>line.startsWith(prefix));
    assert.ok(definition,`Missing real index helper: ${prefix}`);
    vm.runInContext(definition,context);
  }
  vm.runInContext(html.slice(html.indexOf('let searchUpdateTimer;'),html.indexOf("document.addEventListener('change',event=>")),context);
  for (const file of ['web/collection.js','web/keyword-controls.js','web/research.js','web/watch.js','web/workflow.js','web/business.js']) vm.runInContext(read(file),context,{filename:file});
  const run=code=>vm.runInContext(code,context);
  const fire=(type,target,extra={})=>{for (const fn of listeners[type] || []) fn({target,...extra})};
  return {state,calls,context,run,fire,checked,fields,downloads,modal(){return lastModal},
    posts(suffix){return calls.filter(x=>x.body && x.url.endsWith(suffix))},
    selectPlatforms(platforms){checked['quick-platform']=platforms.map(value=>({value}));fire('change',{name:'quick-platform'})},
    query(value){fire('input',{id:'quick-query',value})}};
}

async function main() {
  const fresh=harness(null);
  fresh.selectPlatforms(['xhs','tiktok','reddit']);fresh.query('宠物饮水机');
  await fresh.run("researchAction('quick-keywords', {})");
  assert.equal(fresh.posts('/api/projects').length,1,'one product keyword creates exactly one project');
  assert.equal(fresh.posts('/collect').length,1,'multiple platforms submit one bounded collection task');
  assert.deepEqual(fresh.posts('/collect')[0],{url:'/api/projects/project-a/collect',body:{revision:4,kind:'keywords',platforms:['xhs','tiktok','reddit'],queries:['宠物饮水机'],pages:1,keyword_mode:'quick',rounds:1}});
  await fresh.run("researchAction('quick-keywords', {})");
  assert.equal(fresh.posts('/api/projects').length,1,'collecting again continues the existing project');
  assert.equal(fresh.state.project.id,'project-a');
  assert.equal(fresh.posts('/collect')[1].body.revision,5,'polling refreshes the project revision before its next task');

  assert.match(fresh.run('nextStep()'),/data-page="keywords"/,'keyword-only material recommends keyword analysis first');
  await fresh.run("workflowAction('view-insights', {})");
  assert.equal(fresh.posts('/ai').length,0,'opening module selection does not implicitly invoke a model');
  assert.match(fresh.run("flowNav('insights')"),/data-page="keywords"/,'the existing keyword report remains available in the internal steps');
  await fresh.run("workflowAction('ai-keywords', {})");
  assert.equal(fresh.state.page,'keywords');
  const analysisPage=fresh.run('keywordWorkspace()');
  assert.match(analysisPage,/<h1>整理词库<\/h1>/);
  assert.match(analysisPage,/用户在寻找清洗方式。/,'completed analysis is directly readable without choosing another report tab');
  assert.doesNotMatch(analysisPage,/keyword-view|workspace-tabs|id="search-input"/,'keyword analysis no longer duplicates the source library');
  assert.equal((analysisPage.match(/data-action="ai-keywords"/g)||[]).length,1,'the report exposes one analysis action');
  const steps=fresh.run("flowNav('audience')");
  assert.equal((steps.match(/data-action="navigate"/g)||[]).length,3);
  assert.match(steps,/class="active" data-action="navigate" data-page="audience"/);
  assert.match(steps,/拆分人群/);assert.match(steps,/整理词库/);assert.match(steps,/人群策略/);
  assert.doesNotMatch(steps,/data-page="posts"/);
  assert.match(fresh.run('insightWorkspace()'),/<h1>需求与营销<\/h1>/);
  assert.match(fresh.run('insightWorkspace()'),/生成需求与营销建议/);
  fresh.run("quick.tab='posts'");
  await fresh.run("workflowAction('keyword-data', {})");
  assert.equal(fresh.state.page,'research');
  assert.equal(fresh.run('quick.tab'),'keywords','returning to source material opens its keyword collection');
  assert.match(fresh.run('nextStep()'),/data-page="keywords"/);
  fresh.state.page='research';
  await fresh.run("workflowAction('view-keyword-report', {})");
  assert.equal(fresh.state.page,'keywords');
  assert.equal(fresh.posts('/ai').length,1,'viewing a saved report does not start another analysis');

  const prefs=harness();
  prefs.state.project.runs=[{mode:'collection',kind:'keywords',platforms:['xhs','reddit']},{mode:'collection',kind:'posts',platforms:['amazon']}];
  prefs.run('syncQuickProject()');
  assert.deepEqual(clone(prefs.run('quick.platforms')),['xhs','reddit'],'competitor searches do not replace discovery platform choices');
  assert.equal(prefs.run('quick.tab'),'keywords');

  const theme=harness();
  await theme.run(`workflowAction('search-topic', {dataset:{ids:'["k1","k2"]'}})`);
  await theme.run("collectAction('start-collection', {disabled:false})");
  assert.equal(theme.posts('/api/projects').length,0,'searching report topics must not create a new project');
  assert.deepEqual(theme.posts('/collect')[0].body.platforms,['xhs','reddit'],'topic search keeps every source platform');
  assert.deepEqual(theme.posts('/collect')[0].body.queries,['饮水机清洗','cat fountain cleaning']);
  assert.equal(theme.posts('/collect')[0].body.kind,'posts');
  assert.equal(theme.posts('/collect')[0].url,'/api/projects/project-a/collect');

  const amazon=harness();amazon.state.page='products';
  await amazon.run("researchAction('query-products', {})");
  await amazon.run("collectAction('start-collection', {disabled:false})");
  assert.deepEqual(amazon.posts('/collect')[0].body.platforms,['amazon']);
  assert.equal(amazon.posts('/collect')[0].body.kind,'posts');
  assert.equal(amazon.state.page,'products','Amazon-only product queries remain in market watch after saving');
  assert.equal(amazon.posts('/api/projects').length,0,'competitor search continues the current project');

  for (const [action,target,selected,expected] of [
    ['translate-keywords','keywords',['k2','p1','missing'],['k2']],
    ['translate-current','posts',['p1','k1'],['p1']],
    ['translate-reviews','reviews',['r1','p1'],['r1']]
  ]) {
    const t=harness(),before=clone(t.state.project[target]);
    t.state.selected=new Set(selected);t.run("quick.tab='posts'");
    await t.run(`workflowAction('${action}', {})`);
    assert.deepEqual(t.posts('/ai')[0].body,{revision:4,kind:'translate',target,ids:expected},'translation only sends selected IDs from its target collection');
    assert.deepEqual(t.state.project[target],before,'requesting translation does not replace the original records');
  }

  const retry=harness();
  retry.run("workflow.aiJob={id:'failed-1',kind:'translate',target:'keywords',status:'failed',scope:{evidence_ids:['keywords:k2']}}");
  await retry.run("workflowAction('retry-ai', {})");
  assert.deepEqual(retry.posts('/ai')[0].body.ids,['k2'],'retry keeps its original batch rather than translating the whole project');
  const lostRange=harness();
  lostRange.run("workflow.aiJob={kind:'translate',target:'keywords',status:'failed',scope:{evidence_ids:[]}}");
  await assert.rejects(lostRange.run("workflowAction('retry-ai', {})"),/缺少范围/);
  assert.equal(lostRange.calls.length,0,'an unknown retry range must not silently become all data');

  const otherPost=fixture();
  otherPost.posts.push({id:'p2',title:'Another post',body:'Other topic',platform:'reddit'});
  otherPost.reviews.push({id:'r2',body:'Not selected',platform:'reddit',post_id:'p2'});
  const scoped=harness(otherPost);
  scoped.state.selected=new Set(['p1','k2']);
  await scoped.run("collectAction('post-comments', {dataset:{id:'p1'}})");
  const postId=scoped.modal().footer.match(/data-post-id="([^"]+)"/)?.[1];
  assert.equal(postId,'p1','the comment modal carries the displayed post into its translation button');
  await scoped.run(`workflowAction('translate-reviews', {dataset:{postId:'${postId}'}})`);
  assert.deepEqual(scoped.posts('/ai')[0].body.ids,['r1'],'a post comment modal never translates comments from another post');
  const emptyPost=harness();
  await assert.rejects(emptyPost.run("workflowAction('translate-reviews', {dataset:{postId:'missing'}})"),/没有可翻译/);
  assert.equal(emptyPost.calls.length,0);

  const commentInsight=harness();
  await commentInsight.run("collectAction('post-comments', {dataset:{id:'p1'}})");
  assert.equal(commentInsight.state.modal,true);
  const insightAction=commentInsight.modal().footer.match(/data-action="(ai-insights)"/)?.[1];
  assert.equal(insightAction,'ai-insights','the comment modal links to insight selection');
  await commentInsight.run(`workflowAction('${insightAction}', {})`);
  assert.equal(commentInsight.state.page,'insights');
  assert.equal(commentInsight.state.modal,false,'entering insight selection closes the comment modal');
  assert.equal(commentInsight.posts('/ai').length,0,'opening insight selection does not start analysis');

  const saved=fixture();
  const evidence=(kind,id,text,extra={})=>({id:kind+':'+id,kind,row_id:id,text,platform:'reddit',source:'fixture',text_truncated:false,...extra});
  const keywordSnapshot=[evidence('keywords','k1','OLD_KEYWORD'),evidence('keywords','k2','MISSING_KEYWORD')];
  const keywordReport={id:'keyword-report',kind:'keywords',status:'success',data_version:1,
    scope:{processed:2,total:2,truncated:0,text_truncated:0,evidence_ids:keywordSnapshot.map(x=>x.id)},evidence_snapshot:keywordSnapshot,
    report:{title:'关键词报告',summary:'按旧样本分析',items:keywordSnapshot.map(x=>({id:x.id,valid:true,theme:'清洗',w5h1:'HOW',intent:'需求',stage:'A4',emotion:'中性',reason:'原始线索'})),
      findings:[{text:'清洗问题',evidence_ids:['keywords:k1']}],next_steps:[]}};
  const insightSnapshot=[evidence('posts','p1','OLD_POST_TITLE\nOLD_POST_BODY',{text_truncated:true}),evidence('reviews','r1','OLD_REVIEW_BODY')];
  const insightReport={id:'insight-report',kind:'insights',status:'success',data_version:1,
    scope:{processed:2,total:2,truncated:0,text_truncated:1,evidence_ids:insightSnapshot.map(x=>x.id)},evidence_snapshot:insightSnapshot,
    report:{title:'千机塔',summary:'保存的分析',core_opportunity:{text:'清洗便利',evidence_ids:['posts:p1']},audiences:[],topics:[],cautions:[]}};
  saved.ai_reports=[keywordReport,insightReport];saved.data_version=2;
  saved.keywords=[{...saved.keywords[0],text:'CHANGED_KEYWORD',translation:'NEW_TRANSLATION'}];
  saved.posts[0].title='CHANGED_POST';saved.posts[0].body='CHANGED_BODY';saved.posts[0].translation='NEW_TRANSLATION';saved.posts[0].source_url='https://example.com/changed';
  saved.reviews=[];
  const archive=harness(saved);
  const keywordHtml=archive.run("keywordReportBody(latestAI('keywords'))");
  assert.match(keywordHtml,/OLD_KEYWORD/);assert.match(keywordHtml,/MISSING_KEYWORD/);
  assert.doesNotMatch(keywordHtml,/CHANGED_KEYWORD/,'old classifications stay paired with their original keyword');
  assert.match(keywordHtml,/HOW 方法词/);
  await archive.run("workflowAction('export-ai-md', {dataset:{kind:'keywords'}})");
  assert.match(archive.downloads.at(-1).body,/MISSING_KEYWORD/);
  assert.match(archive.downloads.at(-1).body,/A4/);
  await archive.run("workflowAction('export-ai-md', {dataset:{kind:'insights'}})");
  const markdown=archive.downloads.at(-1).body;
  assert.match(markdown,/OLD_POST_BODY/,'Markdown evidence contains the post body as well as its title');
  assert.match(markdown,/OLD_REVIEW_BODY/,'removed current records still have their analysis snapshot');
  assert.match(markdown,/文本截断：1 条/);
  assert.doesNotMatch(markdown,/CHANGED_BODY|NEW_TRANSLATION|example.com\/changed/);
  await archive.run("workflowAction('export-ai-html', {dataset:{kind:'insights'}})");
  const standalone=archive.downloads.at(-1).body;
  assert.match(standalone,/OLD_POST_BODY/);assert.match(standalone,/OLD_REVIEW_BODY/);
  assert.match(standalone,/1 条原文已截断/);
  assert.doesNotMatch(standalone,/CHANGED_BODY|NEW_TRANSLATION/);
  await archive.run(`workflowAction('ai-evidence', {dataset:{report:'insight-report',evidence:'["posts:p1","reviews:r1"]'}})`);
  assert.match(archive.modal().html,/OLD_POST_BODY/);assert.match(archive.modal().html,/OLD_REVIEW_BODY/);
  assert.doesNotMatch(archive.modal().html,/CHANGED_BODY/);
  const complete=archive.run('fullReportHtml()').split('<h2>当前项目资料</h2>');
  assert.equal(complete.length,2);
  assert.match(complete[0],/OLD_POST_BODY/);assert.doesNotMatch(complete[0],/CHANGED_BODY/);
  assert.match(complete[1],/CHANGED_BODY/,'complete export labels subsequent project data separately from report evidence');

  const candidates=fixture();
  candidates.products=[{id:'B000000001',title:'观察中的饮水机',candidate:true,price:24,currency:'USD'},
    {id:'B000000002',title:'新加入候选',candidate:true,price:null},
    {id:'B000000003',title:'已移出候选',candidate:false,price:20}];
  candidates.analyses=[{id:'rules-1',data_version:1,created_at:'2026-09-11',decisions:[
    {product_id:'B000000001',status:'继续观察',reason:'已整理 1 条商品评价样本；需补充成本与性能验证。',
      missing:['采购与物流成本','真实使用测试'],evidence_ids:['r3'],keyword_ids:['k1']},
    {product_id:'B000000003',status:'继续观察',reason:'已移出商品的旧结论',missing:[],evidence_ids:[],keyword_ids:[]}
  ]}];
  candidates.reviews.push({id:'r3',body:'商品评论原文',product_id:'B000000001',platform:'amazon'});
  candidates.watch_history=[{product_id:'B000000001',status:'success',requests:2,request_limit:2,source:'卖家精灵',created_at:'2026-09-12',results:[
    {tool:'keepa_info',status:'success',data:{requested_asin:'B000000001',data_asin:'B000000001',series:{
      price:[{at:'2026-09-01T00:00:00Z',value:20},{at:'2026-09-12T00:00:00Z',value:24}],
      bsr:[],ratings_count:[{at:'2026-09-12T00:00:00Z',value:37}],rating:[]}}},
    {tool:'asin_sales_trend',status:'success',data:{months:[{month:'2026-08',parent_units:124,child_units:31,average_price:23}]}}
  ]}];
  const finalReport=harness(candidates),page=finalReport.run('reportWorkspace()');
  assert.match(page,/选品依据与待验证事项/);assert.match(page,/已整理 1 条商品评价样本/);
  assert.match(page,/采购与物流成本、真实使用测试/);assert.match(page,/继续观察/);
  assert.match(page,/1 个候选尚未整理选品依据/);assert.match(page,/当前显示的是旧版整理结果/);
  assert.match(page,/data-action="decision-evidence" data-id="B000000001"/);
  assert.doesNotMatch(page,/已移出商品的旧结论/);
  const exported=finalReport.run('fullReportHtml()');
  assert.match(exported,/已整理 1 条商品评价样本/);assert.match(exported,/reviews:r3/);
  assert.match(exported,/竞品历史观察/);assert.match(exported,/父体月销量/);assert.match(exported,/子体月销量/);
  assert.match(exported,/2026-08/);assert.match(exported,/aria-label="历史价格 · USD，供应商返回时间点"/);
  assert.match(exported,/\.watch-chart svg\{display:block/,'exported historical price chart remains visible');
  assert.doesNotMatch(exported,/<button\b/,'standalone selection and history report has no inactive controls');
  assert.equal(finalReport.calls.length,0,'viewing saved conclusions or exporting never sends another paid query');

  const postsOnly=fixture();postsOnly.keywords=[];postsOnly.reviews=[];
  const postReport=harness(postsOnly).run('reportWorkspace()');
  const insightButton=postReport.match(/<button\b[^>]*data-action="ai-insights"[^>]*>/)?.[0];
  assert.ok(insightButton);assert.doesNotMatch(insightButton,/disabled/,'posts-only evidence can generate demand and marketing advice');
  assert.match(archive.run("insightReportBody(latestAI('insights'))"),/营销选题与切入角度/);
  assert.doesNotMatch(archive.run("insightReportBody(latestAI('insights'))"),/A1–A5 营销选题/);

  const ime=harness(null),input={id:'quick-query',value:'chong wu'};
  ime.selectPlatforms(['xhs','reddit']);
  ime.fire('compositionstart',input);ime.fire('input',input,{isComposing:true});
  let prevented=0;
  ime.fire('keydown',input,{key:'Enter',isComposing:true,preventDefault(){prevented++}});
  ime.fire('keydown',input,{key:'Enter',isComposing:false,preventDefault(){prevented++}});
  assert.equal(ime.posts('/collect').length,0,'IME state also protects engines whose key event omits isComposing');
  assert.equal(ime.posts('/api/projects').length,0);
  assert.equal(prevented,0,'IME confirmation is left to the input method');
  input.value='宠物饮水机';ime.fire('compositionend',input);ime.fire('input',input,{isComposing:false});
  ime.fire('keydown',input,{key:'Enter',isComposing:false,preventDefault(){prevented++}});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(ime.posts('/collect').length,1);
  assert.deepEqual(ime.posts('/collect')[0].body.queries,['宠物饮水机']);
  assert.equal(prevented,1);

  const invalid=harness();invalid.selectPlatforms([]);invalid.query('宠物饮水机');
  await assert.rejects(invalid.run("researchAction('quick-keywords', {})"),/至少选择一个平台/);
  assert.equal(invalid.calls.length,0,'empty platform selection must fail before any HTTP request');
  console.log('Workflow: multi-platform collection, report navigation, topic continuation, translation scope/retry, snapshot exports and Chinese IME passed.');
}

if(require.main===module)main().catch(error=>{console.error(error);process.exitCode=1});
module.exports={harness,fixture};
