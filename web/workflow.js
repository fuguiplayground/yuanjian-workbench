/* Continuous research flow, Codex reports and source-preserving translation. */
const workflow={analysisSettingsOpen:{},aiJob:null,poll:null,moduleChoices:{},reportChoices:{}};
const INSIGHT_MODULES=[
 {key:'clean',label:'关键词库',description:'去重、排除无效词，按主题与 5W1H 整理逐词依据。',source:'keywords'},
 {key:'audience',label:'人群画像',description:'具体处境、八层画像、三层需求、购买触发与决策障碍。',source:'all'},
 {key:'intent',label:'搜索意图',description:'看用户处于哪一步、在找什么，以及还缺哪些决策信息。',source:'keywords'},
 {key:'comments',label:'评论需求',description:'从评论原话中找问题、顾虑、未满足需求与可用表达。',source:'reviews'},
 {key:'notes',label:'内容规律',description:'比较内容主题、切入角度与表达规律，找尚未回答的问题。',source:'posts'},
 {key:'topics',label:'营销选题',description:'给出面向具体人群的选题、切入角度与支撑证据。',source:'all'},
 {key:'summary',label:'综合判断',description:'把优先人群、核心机会、行动与待验证事项写成简报。',source:'all'}
];
const INSIGHT_STATUS={pending:'等待生成',running:'正在生成',success:'已完成',partial:'部分完成',failed:'生成失败',skipped:'资料不足，已跳过',cancelled:'已取消',interrupted:'已中断'};
function isModularInsight(r){return r?.kind==='insights'&&r.schema_version===2&&r.report?.modules}
function insightModuleKeys(r){return INSIGHT_MODULES.filter(x=>r?.report?.modules?.[x.key]).map(x=>x.key)}
function insightModuleContext(r,key){const m=r.report.modules[key];return {...r,...m,id:r.id,module_key:key,kind:'insight-module',report:m.report||{}}}
function moduleSourceCount(source){const p=state.project;return source==='all'?p.keywords.length+(p.posts||[]).length+p.reviews.length:(p[source]||[]).length}
function selectedInsightModules(){const id=state.project.id,previous=latestAI('insights');workflow.moduleChoices[id]??=(isModularInsight(previous)?previous.requested_modules:['audience','intent','summary']).filter(key=>INSIGHT_MODULES.some(x=>x.key===key)&&moduleSourceCount(INSIGHT_MODULES.find(x=>x.key===key).source));return INSIGHT_MODULES.filter(x=>workflow.moduleChoices[id].includes(x.key)&&moduleSourceCount(x.source)).map(x=>x.key)}
function selectedInsightReport(){return (state.project.ai_reports||[]).find(x=>x.id===workflow.reportChoices[state.project.id]&&x.kind==='insights')||latestAI('insights')}
function flowNav(active){if(active==='posts')active='research';return `<nav class="flow-nav" aria-label="需求调研步骤">${[['research','采集资料'],['keywords','关键词分析'],['insights','需求与营销']].map(([id,label],i)=>`<button class="${id===active?'active':''}" data-action="navigate" data-page="${id}"><span>${i+1}</span>${label}</button>`).join('')}</nav>`}
function latestAI(kind){return [...(state.project?.ai_reports||[])].reverse().find(x=>x.kind===kind&&(x.status==='success'||isModularInsight(x)))}
function latestKeywordClassification(moduleOnly=false){
 for(const r of [...(state.project?.ai_reports||[])].reverse()){
  if(isModularInsight(r)&&r.report.modules.clean?.status==='success')return insightModuleContext(r,'clean');
  if(!moduleOnly&&r.kind==='keywords'&&r.status==='success')return r;
 }
 return null;
}
function keywordClassifications(r){
 if(!r||r.data_version!==state.project.data_version)return new Map();
 const current=new Map(state.project.keywords.map(k=>[k.id,k]));
 const evidence=new Map((r.evidence_snapshot||[]).map(e=>[e.id,e]));
 return new Map((r.report?.items||[]).flatMap(item=>{
  const id=item.id.replace(/^keywords:/,''),k=current.get(id),e=evidence.get('keywords:'+id);
  const same=k&&e&&!e.text_truncated&&e.text===k.text&&['platform','source','market_scope','provenance'].every(key=>(e[key]||'')===(k[key]||''));
  return same?[[id,item]]:[];
 }));
}
function activeAI(){return workflow.aiJob?.project_id===state.project?.id&&workflow.aiJob.status==='running'}
function aiProgress(){const j=workflow.aiJob;if(!j||j.project_id!==state.project?.id)return '';const labels={keywords:'关键词分析',insights:'需求与营销建议',translate:'中文翻译'};return `<div class="collection-progress" role="status"><div><strong>${labels[j.kind]||'AI'} · ${{running:'Codex 正在处理',success:'已完成',partial:'部分完成',failed:'未完成',cancelled:'已取消',interrupted:'已中断'}[j.status]||j.status}</strong><p>${esc(j.message||'结果会自动保存，可以先查看其他页面。')}</p>${j.schema_version===2?`<p class="caption">已处理 ${j.completed_modules||0} / ${j.total_modules||0} 项${j.current_module?' · 当前：'+esc(INSIGHT_MODULES.find(x=>x.key===j.current_module)?.label||j.current_module):''}；已完成章节可立即查看。</p>`:''}${j.scope?`<p class="caption">本次处理 ${j.scope.processed} / ${j.scope.total} 条${j.scope.truncated?' · '+j.scope.truncated+' 条未覆盖':''}${j.kind==='translate'?'；每批最多 20 条，已有译文会跳过。':''}</p>`:''}</div><div class="actions">${j.status==='running'?button('停止','cancel-ai','','small'):j.schema_version!==2&&['failed','interrupted','cancelled'].includes(j.status)?button('重试','retry-ai','','small'):''}</div></div>`}
function reportMeta(r){if(!r)return '';const scope=r.scope||{},counts=scope.counts||{};const bits=Object.entries(counts).filter(([,v])=>v.total).map(([k,v])=>`${{keywords:'关键词',posts:'内容',reviews:'评论'}[k]||k} ${v.processed}/${v.total}`);return `<p class="report-meta">本地 Codex · ${r.module_key?(r.finished_at?date(r.finished_at):'本项尚未完成'):date(r.finished_at||r.created_at)} · ${esc(bits.join(' · ')||`${scope.processed||0}/${scope.total||0} 条`)}${scope.truncated?' · 部分样本，未覆盖全部资料':''}${scope.text_truncated?' · '+scope.text_truncated+' 条原文已截断，分析仅使用保存的摘录':''}</p>${scope.selection?`<p class="caption">${esc(scope.selection)}</p>`:''}${r.data_version!==state.project.data_version?`<div class="source-note">已补充或更新资料。这份报告基于旧数据，请按需要重新选择分析项，使用新资料生成。</div>`:''}`}
function reportControls(kind,r){
 const p=state.project,hasData=kind==='keywords'?p.keywords.length:p.keywords.length+(p.posts||[]).length+p.reviews.length;
 return `<div class="actions">${button(r?'重新分析':kind==='keywords'?'生成关键词报告':'生成需求与营销建议',kind==='keywords'?'ai-keywords':'ai-insights','',r?'':'primary',activeAI()||!hasData?'disabled':'')}${r?button('导出 Markdown','export-ai-md','download','small',`data-kind="${kind}"`)+button('导出 HTML','export-ai-html','download','small',`data-kind="${kind}"`):''}</div>`
}
function keywordTable(rows){const selected=state.project.keywords.filter(r=>state.selected.has(r.id)).length;const report=latestKeywordClassification();const items=keywordClassifications(report);return `<div class="selection-bar"><span>已选 ${selected} 个词</span><div class="actions">${button('用所选词搜索内容','selected-search','arrow','small',selected?'':'disabled')}${button('翻译所选词','translate-keywords','','small',selected?'':'disabled')}</div></div>${report&&report.data_version!==state.project.data_version?'<p class="caption">资料已更新，旧分析的分类未套用到当前关键词。</p>':''}<div class="table-wrap"><table><thead><tr><th><input type="checkbox" id="select-all" aria-label="选择当前关键词" ${rows.length&&rows.every(k=>state.selected.has(k.id))?'checked':''}></th><th>关键词 / 中文</th><th>平台</th><th>主题 / 意图</th><th>搜索量</th><th>下一步</th></tr></thead><tbody>${rows.map(k=>{const a=items.get(k.id);return `<tr><td><input type="checkbox" data-select="${esc(k.id)}" aria-label="选择 ${esc(k.text)}" ${state.selected.has(k.id)?'checked':''}></td><td><strong>${esc(k.text)}</strong><div class="secondary">${esc(k.translation||(k.platform==='xhs'?'原词为中文':'待翻译'))}</div></td><td>${esc(PLATFORM_NAMES[k.platform]||k.platform||'导入')}<div class="secondary">${source(k)}</div></td><td>${esc(a?.theme||k.scene||'待分析')}<div class="secondary">${esc(a?.intent||k.intent||'待分析')}${a?.valid===false?' · 待排除词':''}</div></td><td>${k.search_volume??'未提供'}<div class="secondary">${esc(k.search_period||'')}</div></td><td>${button('搜内容','keyword-search','arrow','small',`data-id="${esc(k.id)}"`)}</td></tr>`}).join('')}</tbody></table></div>`}
function keywordWorkspace(){
 const r=latestAI('keywords'),clean=latestKeywordClassification(true);
 return head('关键词分析','把采到的词整理成主题与搜索意图，再挑选值得继续验证的方向。',button('返回关键词资料','keyword-data','arrow',''))
  +flowNav('keywords')+demoNote()+jobView()+aiProgress()
  +(clean?`<section class="report-sheet"><div class="section-head"><h2>关键词库已完成</h2>${button('查看本次关键词库','view-keyword-library','arrow','primary',`data-report="${esc(clean.id)}"`)}</div>${reportMeta(clean)}<p>${esc(clean.report.summary||'查看有效词、主题、搜索意图与逐词判断依据。')}</p></section>`:'')
  +(r||!clean?`<section class="report-sheet">${clean?'<span class="eyebrow">旧版关键词报告</span>':''}<div class="section-head"><h2>${esc(r?.report?.title||'从已有关键词中找需求线索')}</h2>${reportControls('keywords',r)}</div>
  ${r?reportMeta(r)+keywordReportBody(r):empty('关键词采完以后，在这里看结论','点击上方「生成关键词报告」，整理有效词、5W1H、搜索意图、主题与下一步研究方向。')}</section>`:'')
  +`<div class="next-step"><div><h3>继续看：谁在搜索，为什么需要？</h3><p>选择人群画像、搜索意图或营销选题，按这次要解决的问题深入分析。</p></div>${button('选择深入洞察','view-insights','arrow','primary')}</div>`
}
function evidenceButton(ids,label='查看依据',reportId='',moduleKey=''){return ids?.length?`<span class="evidence-refs">证据：${ids.map(esc).join('、')}</span>`+button(`${label} ${ids.length}`,'ai-evidence','','small',`data-evidence="${esc(JSON.stringify(ids))}" data-report="${esc(reportId)}" data-module="${esc(moduleKey)}"`):'<span class="caption">待补充证据</span>'}
function statementList(rows,reportId='',moduleKey=''){return (rows||[]).map(x=>`<article class="finding"><p>${esc(x.text)}</p>${evidenceButton(x.evidence_ids,'查看依据',reportId,moduleKey)}</article>`).join('')}
function reportEvidence(r,ref){
 const snapshot=r?.evidence_snapshot?.find(x=>x.id===ref),pos=ref.indexOf(':'),kind=ref.slice(0,pos),id=ref.slice(pos+1);
 const row=(state.project[kind]||[]).find(x=>x.id===id);
 const text=row?(kind==='keywords'?row.text:kind==='posts'?[row.title||'',row.body||''].join('\n').trim():row.body):'';
 if(snapshot){const same=row&&snapshot.text===(snapshot.text_truncated?text.slice(0,1200):text)&&['platform','source','market_scope','provenance'].every(k=>(snapshot[k]||'')===(row[k]||''));return {...snapshot,snapshot:true,source_url:same?row.source_url:'',translation:same&&!snapshot.text_truncated?row.translation:''}}
 return row?{id:ref,kind,row_id:id,text,platform:row.platform,source:row.source,source_url:row.source_url,translation:row.translation,snapshot:false}:null;
}
function reportKeyword(r,id){return reportEvidence(r,id.startsWith('keywords:')?id:'keywords:'+id)?.text||id}
function reportEvidenceHtml(r,refs=r?.scope?.evidence_ids||[]){return refs.map(ref=>{const e=reportEvidence(r,ref);return `<article class="finding"><h3>${esc(ref)}</h3>${e?`<p style="white-space:pre-wrap">${esc(e.text)}</p>${e.metrics&&Object.keys(e.metrics).length?`<p class="caption">采样时指标：${Object.entries(e.metrics).map(([key,value])=>esc(({likes:e.platform==='reddit'?'社区分数':'点赞',comment_count:'评论数',rating:'评分'})[key]||key)+' '+esc(value??'未提供')).join(' · ')}</p>`:''}${e.translation?`<p class="translation-preview">${esc(e.translation)}</p>`:''}<p class="caption">${esc(PLATFORM_NAMES[e.platform]||e.platform||e.source||'来源未注明')} · ${e.snapshot?'分析时保存的原文':'旧报告缺少输入快照；这里是当前记录，仅供参考'}${e.text_truncated?' · 原文已截断，仅分析此摘录':''} · ${external(e.source_url)}</p>`:'<p>这份报告未保存该条证据快照，当前项目也没有对应原文。</p>'}</article>`}).join('')}
function keywordReportBody(r){const report=r.report||{},items=report.items||[];const valid=items.filter(x=>x.valid),themes=[...new Set(valid.map(x=>x.theme).filter(Boolean))],how=valid.filter(x=>String(x.w5h1).toUpperCase()==='HOW');return `<p class="report-summary">${esc(report.summary)}</p><div class="report-numbers">${[['已分析',items.length],['有效词',valid.length],['归一主题',themes.length],['HOW 方法词',how.length]].map(([l,n])=>`<div><strong>${n}</strong><span>${l}</span></div>`).join('')}</div><h3>关键发现</h3>${statementList(report.findings,r.id)}<h3>5W1H · 用户怎样搜索</h3><div class="intent-distribution">${(report.stats?.w5h1||[]).map(x=>`<div><span>${esc(x.name)}</span><i style="width:${Math.min(100,Math.max(0,Number(x.count)/(items.length||1)*100))}%"></i><b>${Number(x.count)||0}</b></div>`).join('')}</div><h3>主题地图 · 从这组词继续搜索</h3><div class="table-wrap"><table><tr><th>主题</th><th>证据关键词</th><th>继续调研</th></tr>${themes.map(theme=>{const matches=valid.filter(x=>x.theme===theme),ids=matches.map(x=>x.id.replace(/^keywords:/,'')),words=matches.map(x=>reportKeyword(r,x.id));return `<tr><td><strong>${esc(theme)}</strong><div class="secondary">${[...new Set(matches.map(x=>x.intent))].map(esc).join('、')}</div></td><td>${words.map(esc).join('、')}</td><td>${button('搜这组词','search-topic','arrow','small',`data-ids="${esc(JSON.stringify(ids))}"`)}</td></tr>`}).join('')}</table></div><h3>下一步研究建议</h3>${statementList(report.next_steps,r.id)}<details class="report-details"><summary>查看逐词分析、5W1H 与待排除词（${items.length}）</summary><div class="table-wrap"><table><tr><th>词</th><th>5W1H</th><th>意图 / 阶段</th><th>判断依据</th></tr>${items.map(x=>{return `<tr><td>${esc(reportKeyword(r,x.id))}</td><td>${esc(x.w5h1)}</td><td>${esc(x.intent)}<div class="secondary">${esc(x.stage)}</div></td><td>${x.valid?'有效线索':'待排除'} · ${esc(x.reason)}</td></tr>`}).join('')}</table></div></details><p class="caption">关键词是搜索线索，人群和购买动机属于待验证推断；无效词只做标记，原数据保留。</p>`}
function insightChoices(){const selected=selectedInsightModules();return `<section class="insight-choices"><div class="section-head"><div><h2>这次重点看什么</h2><p class="muted">勾选需要回答的问题。按顺序逐块生成，完成一块就保存一块。</p></div></div><div class="insight-choice-list">${INSIGHT_MODULES.map(m=>{const count=moduleSourceCount(m.source),disabled=!count||activeAI();return `<label class="insight-choice ${count?'':'unavailable'}"><input type="checkbox" name="insight-module" value="${m.key}" ${selected.includes(m.key)?'checked':''} ${disabled?'disabled':''}><span><strong>${m.label}</strong><span>${m.description}</span></span><small>${count} 条${{keywords:'关键词',posts:'内容',reviews:'评论',all:'资料'}[m.source]}${!count?' · 先补采':''}</small></label>`}).join('')}</div><div class="insight-generate"><div>${button('生成需求与营销建议','generate-insight-modules','','primary',selected.length&&!activeAI()?'':'disabled')}<span class="caption">已选 ${selected.length} 项</span></div><p class="caption">使用本机 Codex，样本会发送至 Codex 模型服务。每块独立取样；首次启动可能需要约 2 分钟，多块分析需更长时间。实际覆盖范围随结果保存。</p></div></section>`}
function insightExportControls(r){return r?`<div class="actions">${button('导出 Markdown','export-ai-md','download','small',`data-kind="insights" data-report="${esc(r.id)}"`)}${button('导出 HTML','export-ai-html','download','small',`data-kind="insights" data-report="${esc(r.id)}"`)}</div>`:''}
function insightWorkspace(){
 const p=state.project,r=selectedInsightReport(),reports=[...(p.ai_reports||[])].reverse().filter(x=>x.kind==='insights'&&(x.status==='success'||isModularInsight(x)));
 return head('需求与营销','先选这次要回答的问题，再逐章查看人群、需求与行动建议。',button('补充调研资料','navigate','arrow','','data-page="research"'))
  +flowNav('insights')+demoNote()+aiProgress()
  +`<div class="evidence-overview"><span>关键词 ${p.keywords.length}</span><span>内容 ${(p.posts||[]).length}</span><span>评论 ${p.reviews.length}</span><div class="spacer"></div>${button('补采评论','navigate','arrow','small','data-page="posts"')}${button('翻译评论','translate-reviews','','small',p.reviews.length?'':'disabled')}${button('查看全部评论','all-reviews','','small',p.reviews.length?'':'disabled')}</div>
  ${r?`<section class="insight-report"><div class="section-head"><div><h2>本项目的洞察报告</h2>${reports.length>1?`<label class="report-history">查看版本 <select id="insight-report-select">${reports.map(x=>`<option value="${esc(x.id)}" ${x.id===r.id?'selected':''}>${esc(date(x.finished_at||x.created_at))} · ${esc(INSIGHT_STATUS[x.status]||x.status)}${isModularInsight(x)?' · '+insightModuleKeys(x).length+' 项':' · 历史报告'}</option>`).join('')}</select></label>`:''}</div>${insightExportControls(r)}</div>${reportMeta(r)}${insightReportBody(r)}</section>`:empty('先选择这次重点，再生成报告','只有关键词也能开始；涉及具体购买行为或隐性动机的判断，会明确标注证据不足。')}`
  +`<details class="analysis-settings" id="analysis-settings" ${(workflow.analysisSettingsOpen[p.id]??!r)?'open':''}><summary>${r?'调整分析内容 / 生成新版':'选择本次分析内容'}</summary>${insightChoices()}</details>`
}
function insightReportBody(r,interactive=true){if(isModularInsight(r))return modularInsightBody(r,interactive);const a=r.report||{};return `<h2>${esc(a.title&&!a.title.includes('千机塔')?a.title:'需求与营销建议')}</h2><p class="report-summary">${esc(a.summary)}</p><section class="core-opportunity"><span class="eyebrow">核心机会</span><p>${esc(a.core_opportunity?.text)}</p>${evidenceButton(a.core_opportunity?.evidence_ids,'查看依据',r.id)}</section><h3>人群与购买动机</h3>${(a.audiences||[]).map((x,i)=>`<article class="audience-block"><div class="section-head"><h3>${i+1}. ${esc(x.name)}</h3>${evidenceButton(x.evidence_ids,'查看依据',r.id)}</div><p>${esc(x.why)}</p><dl class="audience-grid">${[['自然属性',x.natural],['社会属性',x.social],['消费特征',x.consumption],['触发场景',x.scene],['生活方式',x.lifestyle],['即时情绪',x.emotion],['深层情感',x.deep_emotion],['价值观',x.values],['显性需求',x.explicit_need],['隐性需求 · 待验证',x.implicit_need]].map(([l,v])=>`<div><dt>${l}</dt><dd>${esc(v||'证据不足')}</dd></div>`).join('')}</dl></article>`).join('')}<h3>营销选题与切入角度</h3>${(a.topics||[]).map(x=>`<article class="finding"><span class="badge">${esc(x.layer)}</span><h3>${esc(x.title)}</h3><p>${esc(x.angle)}</p><p class="caption">${esc(x.why)}</p>${evidenceButton(x.evidence_ids,'查看依据',r.id)}</article>`).join('')}<h3>待验证与谨慎判断</h3>${statementList(a.cautions,r.id)}${a.self_check?`<details class="report-details"><summary>千机塔四标准自检</summary><p>${esc(a.self_check.note)}</p><p>不制造焦虑：${a.self_check.no_anxiety?'通过':'需复核'} · 最窄切入：${a.self_check.narrowest?'通过':'需复核'} · 有对比：${a.self_check.has_contrast?'通过':'需复核'} · 真实需求：${a.self_check.real_demand?'通过':'需复核'}</p></details>`:''}<p class="caption">模型分析使用本次有限样本。隐性动机与营销选题是建议，不能当作真实消费者比例或确定市场结论。</p>`}
// A single document tree feeds the screen, standalone HTML and Markdown.
function insightModuleNodes(key,a,r){
 const text=value=>({type:'text',text:value||''}),point=value=>({type:'point',value}),refs=ids=>({type:'refs',ids:ids||[]});
 const group=(title,children)=>({type:'group',title,children:children.filter(Boolean)}),list=values=>({type:'list',values:values||[]});
 const points=values=>(values||[]).map(point),quotes=values=>(values||[]).map(x=>({type:'quote',text:x.quote,id:x.evidence_id}));
 const table=(headers,rows)=>({type:'table',headers,rows}),terms=values=>(values||[]).map(x=>group(x.text,[refs([x.evidence_id]),x.why?point(x.why):null]));
 let nodes=[];
 if(key==='clean'){
  const s=a.stats||{};
  nodes=[group('关键词概况',[table(['已分析','有效词','待排除','归一主题','高价值词','HOW 方法词占有效词'],[[s.total??a.items?.length??0,s.valid??'—',s.invalid??'—',s.topic_count??'—',s.longtail_count??a.high_value_terms?.length??0,s.how_pct===undefined?'—':s.how_pct+'%']])]),
   group('关键发现',points(a.findings)),group('主题地图',(a.topic_map||a.theme_recommendations||[]).map(x=>group(x.theme,[text(`${x.layer||''}${x.count===undefined?'':' · '+x.count+' 条样本词'}`),point(x.direction),refs(x.evidence_ids)]))),
   group('高价值关键词',terms(a.high_value_terms)),group('品牌机会',points(a.brand_opportunities)),
   ...[['5W1H 分布','w5h1'],['决策阶段分布','journey'],['情绪分布','emotion']].map(([title,field])=>group(title,[table(['分类','样本词数'],(s[field]||[]).map(x=>[x.name,x.count]))])),
   group('逐词分类与内容建议',[table(['原词 / 编号','有效性与原因','5W1H / 意图 / 阶段 / 情绪','主题','内容建议'],(a.items||[]).map(x=>[reportKeyword(r,x.id)+'\n'+x.id,(x.valid?'有效线索':'待排除')+' · '+x.reason,[x.w5h1,x.intent,x.stage,x.emotion].join(' / '),x.theme,x.content_suggestion]))]),group('下一步',points(a.next_steps))];
 }else if(key==='audience'){
  nodes=[group('人群之间的关系',[point(a.audience_map)]),...(a.audiences||[]).map((x,index)=>group(`${index+1}. ${x.name}`,[
   text(x.one_line),group('优先级 · '+x.priority,[point(x.priority_reason)]),refs(x.evidence_ids),
   group('八层画像',[['自然属性','natural'],['社会属性','social'],['消费特征','consumption'],['行为场景','scene'],['生活方式','lifestyle'],['此刻情绪','emotion'],['深层情感','deep_emotion'],['价值观','values']].map(([title,field])=>group(title,[point(x.layers?.[field])]))),
   group('日常场景',(x.day_in_life||[]).map(y=>group(y.moment,[text('场景：'+y.scene),text('要做的事：'+y.task),point({...y,text:'卡住的地方：'+y.friction})]))),
   group('三层需求',[['显性需求','explicit'],['隐性需求','implicit'],['深层需求','deep']].map(([title,field])=>group(title,[point(x.needs?.[field])]))),
   ...[['购买触发','purchase_triggers'],['决策因素','decision_factors'],['购买障碍','barriers'],['现有替代方案','alternatives']].map(([title,field])=>group(title,points(x[field]))),
   group('面向这个人群的定位',[['为谁解决问题','target'],['具体承诺','promise'],['需要拿出的证明','proof'],['应避免的承诺','avoid']].map(([title,field])=>group(title,[point(x.positioning?.[field])]))),
   group('优先级的四项依据',[text('以下为模型判断；空分表示无法判断。不是市场规模、转化率或已付费人数。'),...[['痛感强度','pain'],['付费证据','payment'],['产品承接','fit'],['内容供给','content']].map(([title,field])=>group(title+' · '+(x.scores?.[field]?.score==null?'待验证':x.scores[field].score+' / 5'),[point(x.scores?.[field]?.reason)]))]),
   group('对应搜索原词',terms(x.search_terms)),group('需要实际验证的问题',[list(x.validation_questions)])
  ])),group('下一步',points(a.next_steps))];
 }else if(key==='intent'){
  nodes=[group('用户卡在哪里',[point(a.bottleneck)]),group('A1–A5 样本分布',[text('以下是关键词记录数；不是人数、人群占比或购买率。'),table(['阶段','样本词数','证据'],(a.journey||[]).map(x=>[x.stage,x.count,(x.evidence_ids||[]).join('、')]))]),
   group('各阶段需要的内容',(a.stage_insights||[]).map(x=>group(x.stage,[point(x.interpretation),group('下一步内容',[point(x.next_content)])]))),
   group('需求与迫切程度',(a.demands||[]).map(x=>group(x.need+' · '+x.urgency,[point(x.diagnosis),group('建议动作',[point(x.action)])]))),
   group('情绪线索',(a.emotions||[]).map(x=>group(x.emotion,[point(x.interpretation)]))),
   group('逐词阶段与情绪',[table(['原词 / 编号','阶段','情绪'],(a.items||[]).map(x=>[reportKeyword(r,x.id)+'\n'+x.id,x.stage,x.emotion]))]),group('下一步',points(a.next_steps))];
 }else if(key==='comments'){
  nodes=[...[['痛点与不满','pains'],['用户在问什么','questions'],['被认可的部分','loves']].map(([title,field])=>group(title,(a[field]||[]).map(x=>group('',[point(x.point),...quotes(x.quotes)])))),
   group('可保留的用户原话',quotes(a.golden_quotes)),group('需求优先级',points(a.demand_priorities)),group('从评论延伸的选题',points(a.topics)),group('下一步',points(a.next_steps))];
 }else if(key==='notes'){
  nodes=[group('本次样本的表现口径',[text(a.performance_note)]),group('内容主题',(a.themes||[]).map(x=>group(x.theme,[point(x.explanation)]))),
   group('切入角度',(a.angles||[]).map(x=>group(x.angle,[point(x.why)]))),
   group('开头、正文与收尾',(a.patterns||[]).map(x=>group(({opening:'开头',body:'正文',closing:'收尾'})[x.part]||x.part,[point(x.finding)]))),
   group('可继续创作的选题',(a.topics||[]).map(x=>group(x.title,[text(x.angle),point(x.why)]))),group('本次样本未覆盖的角度',points(a.gaps)),group('下一步',points(a.next_steps))];
 }else if(key==='topics'){
  nodes=[group('先做哪些选题',[point(a.priority_reason)]),...(a.topics||[]).map((x,index)=>group(`${index+1}. ${x.title}`,[text(`面向：${x.target} · 阶段：${x.stage} · 形式：${x.format}`),text('切入角度：'+x.angle),point(x.why),group('开头',[text(x.opening)]),group('内容提纲',[list(x.outline)]),group('行动引导',[text(x.call_to_action)]),group('对应搜索原词',[list(x.words)]),refs(x.evidence_ids)])),group('下一步',points(a.next_steps))];
 }else if(key==='summary'){
  nodes=[group('核心机会',[point(a.core_opportunity)]),group('最窄切入点',[point(a.narrowest_entry)]),group('优先服务的人群',(a.priority_audiences||[]).map(x=>group(x.name,[point(x.why)]))),group('定位建议',[point(a.positioning)]),
   group('先做什么',(a.actions||[]).map((x,index)=>group(`${index+1}. ${x.action}`,[point(x.why),text('交付物：'+x.deliverable),text('验证标准：'+x.verification)]))),group('待验证与谨慎判断',points(a.cautions)),
   a.self_check?group('方法自检',[text(a.self_check.note),list([['不制造焦虑','no_anxiety'],['最窄切入','narrowest'],['有对比','has_contrast'],['真实需求','real_demand']].map(([label,field])=>label+'：'+(a.self_check[field]?'通过':'需复核')))]):null];
 }
 return nodes.filter(Boolean);
}
function insightNodesHtml(nodes,r,level=3){return nodes.map(n=>{
 if(n.type==='group')return `<section class="insight-part">${n.title?`<h${Math.min(level,6)}>${esc(n.title)}</h${Math.min(level,6)}>`:''}${n.children.length?insightNodesHtml(n.children,r,level+1):'<p class="caption">本次未形成有依据的条目。</p>'}</section>`;
 if(n.type==='text')return `<p>${esc(n.text)}</p>`;
 if(n.type==='point'){const v=n.value;if(!v)return '<p class="caption">证据不足，待补充。</p>';return `<div class="insight-point"><span class="basis basis-${esc(v.basis||'inference')}">${({evidence:'原文直接表达',inference:'模型推断',unknown:'待验证'})[v.basis]||'模型推断'}</span><p>${esc(v.text)}</p>${v.validation?`<p class="validation"><strong>如何验证：</strong>${esc(v.validation)}</p>`:''}${v.evidence_ids?.length?evidenceButton(v.evidence_ids,'查看原文',r.id,r.module_key):''}</div>`}
 if(n.type==='refs')return n.ids.length?evidenceButton(n.ids,'查看原文',r.id,r.module_key):'';
 if(n.type==='quote')return `<blockquote><p>${esc(n.text)}</p>${evidenceButton([n.id],'查看原文',r.id,r.module_key)}</blockquote>`;
 if(n.type==='list')return n.values.length?`<ul>${n.values.map(v=>`<li>${esc(v)}</li>`).join('')}</ul>`:'<p class="caption">本次未形成有依据的条目。</p>';
 if(n.type==='table')return n.rows.length?`<div class="table-wrap"><table><thead><tr>${n.headers.map(v=>`<th>${esc(v)}</th>`).join('')}</tr></thead><tbody>${n.rows.map(row=>`<tr>${row.map(v=>`<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`:'<p class="caption">本次暂无分布数据。</p>';
 return '';
}).join('')}
function insightNodesMarkdown(nodes,level=3){return nodes.flatMap(n=>{
 if(n.type==='group')return [...(n.title?['','#'.repeat(Math.min(level,6))+' '+n.title,'']:[]),...(n.children.length?insightNodesMarkdown(n.children,level+1):['本次未形成有依据的条目。'])];
 if(n.type==='text')return [n.text,''];
 if(n.type==='point'){const v=n.value;if(!v)return ['证据不足，待补充。',''];return [`【${({evidence:'原文直接表达',inference:'模型推断',unknown:'待验证'})[v.basis]||'模型推断'}】${v.text}`,...(v.validation?['如何验证：'+v.validation]:[]),...(v.evidence_ids?.length?['证据：'+v.evidence_ids.join('、')]:[]),'']}
 if(n.type==='refs')return n.ids.length?['证据：'+n.ids.join('、'),'']:[];
 if(n.type==='quote')return [...String(n.text).split('\n').map(x=>'> '+x),'证据：'+n.id,''];
 if(n.type==='list')return n.values.length?[...n.values.map(x=>'- '+x),'']:['本次未形成有依据的条目。',''];
 if(n.type==='table'){const cell=v=>String(v??'').replace(/\|/g,'\\|').replace(/\n/g,' / ');return n.rows.length?['| '+n.headers.map(cell).join(' | ')+' |','| '+n.headers.map(()=>'---').join(' | ')+' |',...n.rows.map(row=>'| '+row.map(cell).join(' | ')+' |'),'']:['本次暂无分布数据。','']}
 return [];
})}
function modularInsightBody(r,interactive=true){const keys=insightModuleKeys(r),successful=keys.filter(key=>r.report.modules[key].status==='success');return `<header class="insight-report-head"><h2>${esc(r.report.title||'需求与营销建议')}</h2><p>${esc(r.report.summary||'每个章节单独保存；已完成章节可以立即阅读。')}</p><p class="caption">${successful.length} / ${keys.length} 项已完成 · ${esc(INSIGHT_STATUS[r.status]||r.status)}。有引用仍可能是模型推断，请按各项标注和验证方法阅读。</p></header><div class="insight-report-layout"><nav class="insight-toc" aria-label="洞察报告目录"><strong>报告目录</strong>${keys.map(key=>{const m=r.report.modules[key],label=INSIGHT_MODULES.find(x=>x.key===key).label;return interactive?`<button data-action="insight-section" data-section="insight-${esc(r.id)}-${key}"><span>${label}</span><small>${esc(INSIGHT_STATUS[m.status]||m.status)}</small></button>`:`<a href="#insight-${esc(r.id)}-${key}">${label} · ${esc(INSIGHT_STATUS[m.status]||m.status)}</a>`}).join('')}</nav><div class="insight-chapters">${keys.map(key=>{const m=r.report.modules[key],context=insightModuleContext(r,key),label=INSIGHT_MODULES.find(x=>x.key===key).label;return `<section class="insight-chapter" id="insight-${esc(r.id)}-${key}"><div class="section-head"><div><span class="eyebrow">${label} · ${esc(INSIGHT_STATUS[m.status]||m.status)}</span><h2>${esc(m.report?.title||label)}</h2></div>${interactive?button(m.status==='success'?'重跑本项':'重试本项','rerun-insight-module','','small',`data-report="${esc(r.id)}" data-module="${key}" ${activeAI()||r.data_version!==state.project.data_version||!moduleSourceCount(INSIGHT_MODULES.find(x=>x.key===key).source)?'disabled':''}`):''}</div>${m.scope?reportMeta(context):''}${m.message?`<p class="caption">${esc(m.message)}</p>`:''}${m.status==='success'?`<p class="report-summary">${esc(m.report.summary)}</p>${m.report.quality==='limited'?'<p class="source-note">资料有限，请结合本项缺口阅读。</p>':''}${m.report.limitations?.length?`<details class="insight-limitations"><summary>本项资料缺口（${m.report.limitations.length}）</summary><ul>${m.report.limitations.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></details>`:''}${insightNodesHtml(insightModuleNodes(key,m.report,context),context)}<details class="report-details"><summary>本项原始证据（${m.scope?.evidence_ids?.length||0}）</summary>${reportEvidenceHtml(context)}</details>`:`<p class="muted">${m.status==='running'?'正在分析；完成后会自动显示本章。':m.status==='pending'?'前一项完成后开始，已完成的章节可先阅读。':m.status==='skipped'?'补充对应资料后，可重新选择本项生成。':'本项尚未完成，其他成功章节已保留。'}</p>`}</section>`}).join('')}</div></div>`}
function selectionSummary(interactive=true){
 const p=state.project,a=latest(),candidates=p.products.filter(x=>x.candidate),decisions=(a?.decisions||[]).filter(d=>candidates.some(x=>x.id===d.product_id)),pending=candidates.filter(x=>!decisions.some(d=>d.product_id===x.id));
 return `<section class="flat-section"><div class="section-head"><h2>选品依据与待验证事项</h2>${interactive?button(a?'更新选品依据':'整理选品依据','analyze','refresh','',candidates.length?'':'disabled'):''}</div>${a?staleNote():''}
 ${decisions.map(d=>{const x=candidates.find(x=>x.id===d.product_id);return `<article class="finding"><div class="section-head"><h3>${esc(x.title)}</h3><span class="badge">${esc(d.status)}</span></div><p>${esc(d.reason)}</p><p><strong>待验证：</strong>${d.missing.map(esc).join('、')||'未记录'}</p><p class="caption">商品评论证据：${d.evidence_ids.map(id=>'reviews:'+esc(id)).join('、')||'暂无'}；项目级关键词 ${d.keyword_ids.length} 条，尚未验证与该商品匹配。</p>${interactive?button('查看商品评论依据 '+d.evidence_ids.length,'decision-evidence','','small',`data-id="${esc(x.id)}"`):''}</article>`}).join('')}
 ${pending.length?`<p class="muted">${pending.length} 个候选尚未整理选品依据。${interactive?'点击上方整理，将现有商品评价和缺失资料放在一起。':''}</p>`:!candidates.length?'<p class="muted">还没有候选商品。在竞品研究加入候选后，可整理选品依据。</p>':''}
 <p class="caption">${a?'整理时间：'+date(a.created_at)+' · ':''}规则整理，无综合评分。「继续观察」表示证据不足；采购、物流、退货与使用测试需补齐后再判断。</p></section>`;
}
function actionCards(interactive=true){
 const r=latestAI('insights'),m=isModularInsight(r)?r.report.modules.summary:null;
 const context=m?.status==='success'?insightModuleContext(r,'summary'):null;
 const actions=context?.report?.actions||[];
 if(!actions.length)return `<section class="action-board"><div class="section-head"><div><span class="eyebrow">从判断到行动</span><h2>下一步行动</h2></div></div><p class="muted">尚未形成行动建议。先补充资料，再在需求与营销中选择「综合判断」。</p>${interactive?button('查看分析内容','view-insights','arrow','small'):''}</section>`;
 return `<section class="action-board"><div class="section-head"><div><span class="eyebrow">从判断到行动</span><h2>下一步行动</h2></div><span class="badge">模型建议 · 待验证</span></div>${reportMeta(context)}<div class="action-cards">${actions.map((a,i)=>`<article class="action-card"><span class="action-number">${String(i+1).padStart(2,'0')}</span><h3>${esc(a.action||'行动内容待补充')}</h3><p class="action-reason">${esc(a.why?.text||'行动依据待补充')}</p><dl><div><dt>交付物</dt><dd>${esc(a.deliverable||'待补充')}</dd></div><div><dt>怎样验收</dt><dd>${esc(a.verification||'待补充')}</dd></div></dl>${evidenceButton(a.why?.evidence_ids,'查看行动依据',r.id,'summary')}</article>`).join('')}</div></section>`;
}
function reportWorkspace(){const p=state.project,kw=latestKeywordClassification(),insight=latestAI('insights'),summary=isModularInsight(insight)?insight.report.modules.summary:null,claim=summary?.status==='success'?summary.report.core_opportunity:!isModularInsight(insight)?insight?.report?.core_opportunity:null;return head('结论与行动','先看当前判断，再查依据与缺口，确定下一步验证动作。',button('导出完整报告','export-report','download','primary')+button('导出项目包','export-project','download'))+demoNote()+actionCards()+`${insight?`<section class="report-sheet"><span class="eyebrow">当前需求结论 · 待验证</span><h2>${esc(insight.report.title)}</h2><p class="report-summary">${esc(claim?.text||'逐项分析已保存；进入报告查看本次选中的章节与完成状态。')}</p>${evidenceButton(claim?.evidence_ids,'查看依据',insight.id,summary?'summary':'')}<p class="caption">本次分析 ${insight.scope?.processed||0} / ${insight.scope?.total||0} 条资料，具体样本与限制见完整建议。</p></section>`:''}<section class="report-sheet"><div class="report-link-row"><div><h2>关键词分析</h2><p>${kw?date(kw.finished_at||kw.created_at)+' · '+esc(kw.report.title):'尚未生成；先采关键词，再分析。'}</p>${kw?reportMeta(kw):''}</div>${button(kw?'查看报告':'生成报告',kw?.module_key==='clean'?'view-keyword-library':kw?'view-keyword-report':'ai-keywords','arrow','',kw?`data-report="${esc(kw.id)}"`:p.keywords.length?'':'disabled')}</div><div class="report-link-row"><div><h2>需求与营销建议</h2><p>${insight?date(insight.finished_at||insight.created_at)+' · '+esc(insight.report.title):'从人群、场景、需求与情感推导营销方向。'}</p></div>${button(insight?'查看建议':'生成建议',insight?'view-insights':'ai-insights','arrow','',p.keywords.length||(p.posts||[]).length||p.reviews.length?'':'disabled')}</div></section>${selectionSummary()}<section class="flat-section"><div class="section-head"><h2>候选商品</h2>${button('查看并比较商品','navigate','arrow','','data-page="products"')}</div>${p.products.filter(x=>x.candidate).map(x=>`<div class="report-link-row"><div><strong>${esc(x.title)}</strong><p>${money(x)} · ${esc(x.sales_raw||'销量未提供')}</p></div>${button('查看商品','product-detail','','small',`data-id="${esc(x.id)}"`)}</div>`).join('')||'<p class="muted">还没有候选商品，在商品列表加入后可并排比较。</p>'}</section><p class="caption">报告保留来源、采集时间和覆盖范围。成本、物流、退货与利润需另行核算，不从社交讨论直接推算销量。</p>`}
async function startAI(kind,target='',ids=[],options={}){if(!state.project)throw Error('请先开始一次调研');if(activeAI())throw Error('当前 Codex 任务仍在运行');const p=state.project,projectId=p.id;closeModal();if(kind==='keywords')goto('keywords');if(kind==='insights')goto('insights');const job=await api('/api/projects/'+projectId+'/ai',{revision:p.revision,kind,target,...(ids.length?{ids}:{}),...options});if(state.project?.id!==projectId)return;workflow.aiJob=job;if(kind==='insights')delete workflow.reportChoices[projectId];clearTimeout(workflow.poll);render();await pollAI()}
async function pollAI(){const job=workflow.aiJob;if(!job)return;try{const next=await api('/api/ai/jobs/'+job.id);if(workflow.aiJob?.id!==job.id)return;workflow.aiJob=next;if(state.project?.id===next.project_id){const project=await api('/api/projects/'+next.project_id);if(state.project?.id!==next.project_id||workflow.aiJob?.id!==job.id)return;state.project=project;if(!state.modal&&!state.composing&&!['quick-query','search-input'].includes(document.activeElement?.id))render()}if(next.status==='running')workflow.poll=setTimeout(pollAI,1600);else if(state.project?.id===next.project_id)toast(next.message||'Codex 任务已结束')}catch(e){toast(e.message)}}
async function resumeAI(){if(!state.project)return;const projectId=state.project.id;const jobs=await api('/api/ai/jobs?project='+projectId);if(state.project?.id!==projectId)return;const job=jobs.find(x=>x.status==='running')||jobs[0];if(job){clearTimeout(workflow.poll);workflow.aiJob=job;if(job.status==='running')await pollAI()}}
function reportDocument(title,body){return `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>${esc(title)}</title><style>body{font:15px/1.85 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;color:#26313c;max-width:980px;margin:44px auto;padding:0 24px}h1{font-size:30px}h2{margin-top:34px}h3{margin-top:28px}p{white-space:pre-wrap}table{width:100%;border-collapse:collapse;font-size:13px}td,th{border-bottom:1px solid #ddd;text-align:left;padding:12px}a{color:#1765d1}.report-numbers,.audience-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:20px}.report-numbers strong{display:block;font-size:26px}.secondary,.caption,.report-meta,dt{font-size:12px;color:#687480}.finding,.audience-block,.core-opportunity{padding:20px 0;border-bottom:1px solid #ddd}dd{margin:0}button,svg[aria-hidden="true"]{display:none}.watch-chart svg{display:block;width:100%;height:auto}.evidence-refs{display:block;font-size:12px;color:#687480}blockquote{margin:18px 0;padding:8px 20px;border-left:2px solid #bbc9da}.insight-toc{padding:16px 0;border-top:1px solid #ddd;border-bottom:1px solid #ddd}.insight-toc a{display:block}.insight-chapter{margin:42px 0;border-top:1px solid #ddd;padding-top:20px}.insight-part{margin:24px 0}.insight-part h4,.insight-part h5,.insight-part h6{font-size:15px;margin:18px 0 8px}.basis{font-size:12px;color:#59697a}.validation{color:#59697a;font-size:13px}td{white-space:pre-wrap;overflow-wrap:anywhere}.insight-limitations{background:#f6f8fb;padding:16px}.insight-point{margin:14px 0}@media print{article,tr{break-inside:avoid}details{display:block}}</style><body>${body.replace(/<button\b[\s\S]*?<\/button>/g,'').replace(/<details[^>]*>/g,'<section>').replace(/<\/details>/g,'</section>')}</body></html>`}
function fullReportHtml(){
 const p=state.project,k=latestKeywordClassification(),i=latestAI('insights');
 return reportDocument(p.name+' · 完整调研报告',`<h1>${esc(p.name)}</h1><p>产品词：${esc(p.keyword)} · 导出 ${esc(new Date().toLocaleString('zh-CN'))}</p>${demoNote()}
 ${k?'<h2>关键词报告</h2>'+reportMeta(k)+(k.module_key==='clean'?insightNodesHtml(insightModuleNodes('clean',k.report,k),k):keywordReportBody(k))+'<h3>关键词报告 · 原始证据快照</h3>'+reportEvidenceHtml(k):'<p>关键词报告尚未生成。</p>'}
 ${i?'<h2>需求与营销建议</h2>'+reportMeta(i)+insightReportBody(i,false)+(isModularInsight(i)?'':'<h3>需求与营销 · 原始证据快照</h3>'+reportEvidenceHtml(i)):'<p>需求与营销建议尚未生成。</p>'}
 ${actionCards(false)}${selectionSummary(false)}${watchReportHtml()}
 <h2>当前项目资料</h2><p>下列资料含后续补采与中文译文；旧报告实际使用的原文以上方证据快照为准。</p>
 <h3>关键词与中文</h3><table><tr><th>编号</th><th>关键词</th><th>中文</th><th>平台 / 时间</th></tr>${p.keywords.map(x=>`<tr><td>keywords:${esc(x.id)}</td><td>${esc(x.text)}</td><td>${esc(x.translation)}</td><td>${esc(PLATFORM_NAMES[x.platform]||x.source)} / ${date(x.collected_at)}</td></tr>`).join('')}</table>
 <h3>商品资料</h3>${p.products.map(x=>`<p>${esc(x.title)} · ${money(x)}<br>${esc(x.sales_raw||'销量未提供')} · ${external(x.source_url)}</p>`).join('')}
 <h3>内容原文与中文</h3>${(p.posts||[]).map(x=>`<article><h3>${esc(x.title)}</h3><p>${esc(x.body)}</p><p>${esc(x.translation)}</p><p>posts:${esc(x.id)} · ${esc(PLATFORM_NAMES[x.platform])} · ${external(x.source_url)}</p></article>`).join('')}
 <h3>评论原文与中文</h3>${p.reviews.map(reviewBlock).join('')}`);
}
function moduleEvidenceMarkdown(r){const lines=[];for(const ref of r.scope?.evidence_ids||[]){const e=reportEvidence(r,ref);lines.push('','#### '+ref);if(!e){lines.push('报告快照与当前记录均缺失，无法提供原文。');continue}lines.push(e.snapshot?'分析时保存的原文：':'旧报告缺少输入快照；下方当前记录仅供参考：',...String(e.text).split('\n').map(x=>'> '+x),'','来源：'+(PLATFORM_NAMES[e.platform]||e.platform||e.source||'未注明')+(e.source_url?' · '+e.source_url:''));if(e.text_truncated)lines.push('原文已截断；以上为模型实际收到的摘录。');if(e.translation)lines.push('中文译文：'+e.translation);if(e.metrics&&Object.keys(e.metrics).length)lines.push('采样时指标：'+Object.entries(e.metrics).map(([key,value])=>key+' = '+(value??'未提供')).join('；'))}return lines}
function modularInsightMarkdown(r){const keys=insightModuleKeys(r),lines=['# '+state.project.name+' · 需求与营销建议','',r.report.title||'',r.report.summary||'','报告建立时间：'+(r.created_at||'未记录'),'状态：'+(INSIGHT_STATUS[r.status]||r.status),'','## 报告目录',...keys.map(key=>'- '+INSIGHT_MODULES.find(x=>x.key===key).label+' · '+(INSIGHT_STATUS[r.report.modules[key].status]||r.report.modules[key].status)),''];if(r.data_version!==state.project.data_version)lines.push('资料已更新；本报告按每项生成时保存的证据快照阅读。','');for(const key of keys){const m=r.report.modules[key],context=insightModuleContext(r,key),scope=m.scope||{};lines.push('## '+INSIGHT_MODULES.find(x=>x.key===key).label,'',m.report?.title||'','状态：'+(INSIGHT_STATUS[m.status]||m.status),m.message||'',...(m.finished_at?['本项完成时间：'+m.finished_at]:[]),scope.selection||'',`覆盖：${scope.processed||0}/${scope.total||0} 条；未覆盖 ${scope.truncated||0} 条；文本截断 ${scope.text_truncated||0} 条。`,...Object.entries(scope.counts||{}).map(([kind,count])=>`${{keywords:'关键词',posts:'内容',reviews:'评论'}[kind]||kind}：${count.processed}/${count.total}`),'');if(m.status!=='success')continue;lines.push(m.report.summary||'','',m.report.quality==='limited'?'本项资料有限。':'',...(m.report.limitations?.length?['### 本项资料缺口',...m.report.limitations.map(x=>'- '+x),'']:[]),...insightNodesMarkdown(insightModuleNodes(key,m.report,context)),'','### 本项原始证据',...moduleEvidenceMarkdown(context),'')}return lines.join('\n')}
function reportMarkdown(r){
 if(isModularInsight(r))return modularInsightMarkdown(r);
 const p=state.project,scope=r.scope||{};
 let lines=['# '+p.name+' · '+(r.kind==='keywords'?'关键词报告':'需求与营销建议'),'',r.report.summary||'','',
  `分析时间：${r.finished_at||r.created_at}`,`覆盖：${scope.processed}/${scope.total} 条；${scope.truncated?'部分样本':'范围内记录均已处理'}`,
  scope.text_truncated?`文本截断：${scope.text_truncated} 条，仅分析保存的摘录。`:'文本未截断。',''];
 if(r.data_version!==p.data_version)lines.push('资料已更新；本报告按生成时保存的证据快照阅读。','');
 const claims=rows=>(rows||[]).map(x=>'- '+x.text+'（证据：'+x.evidence_ids.join('、')+'）');
 if(r.kind==='keywords'){
  lines.push('## 关键发现',...claims(r.report.findings),'','## 逐词分析',
   ...(r.report.items||[]).map(x=>`- ${reportKeyword(r,x.id)}：${x.valid?'有效线索':'待排除'} / ${x.theme} / ${x.w5h1} / ${x.intent} / ${x.stage} / ${x.emotion}；${x.reason}`),
   '','## 下一步',...claims(r.report.next_steps));
 }else{
  lines.push('## 核心机会',...claims(r.report.core_opportunity?[r.report.core_opportunity]:[]),'## 人群',
   ...(r.report.audiences||[]).flatMap(x=>['### '+x.name,x.why,
    ...[['自然属性','natural'],['社会属性','social'],['消费特征','consumption'],['场景','scene'],['生活方式','lifestyle'],['即时情绪','emotion'],['深层情感','deep_emotion'],['价值观','values'],['显性需求','explicit_need'],['隐性需求（推断）','implicit_need']].map(([l,k])=>'- '+l+'：'+x[k]),
    '证据：'+x.evidence_ids.join('、'),'']),
   '## 选题',...(r.report.topics||[]).flatMap(x=>['### '+x.layer+' · '+x.title,x.angle,x.why,'证据：'+x.evidence_ids.join('、'),'']),
   '## 待验证',...claims(r.report.cautions));
 }
 lines.push('','## 原始证据');
 for(const ref of scope.evidence_ids||[]){
  const e=reportEvidence(r,ref);lines.push('','### '+ref);
  if(!e){lines.push('报告快照与当前记录均缺失，无法提供原文。');continue}
  lines.push(e.snapshot?'分析时保存的原文：':'旧报告缺少输入快照；下方当前记录仅供参考：',
   ...String(e.text).split('\n').map(line=>'> '+line),'',
   `来源：${PLATFORM_NAMES[e.platform]||e.platform||e.source||'未注明'}${e.source_url?' · '+e.source_url:''}`);
  if(e.text_truncated)lines.push('原文已截断；以上为模型实际收到的摘录。');
  if(e.translation)lines.push('中文译文：'+e.translation);
 }
 return lines.join('\n');
}
async function workflowAction(action,el){switch(action){
case'ai-keywords':await startAI('keywords');return true;
case'ai-insights':closeModal();goto('insights');return true;
case'generate-insight-modules':{const modules=selectedInsightModules();if(!modules.length)throw Error('请至少选择一项有资料的分析');await startAI('insights','',[],{modules});return true}
case'rerun-insight-module':{const r=(state.project.ai_reports||[]).find(x=>x.id===el.dataset.report),key=el.dataset.module;if(!isModularInsight(r)||!insightModuleKeys(r).includes(key))throw Error('报告或分析项不存在');if(r.data_version!==state.project.data_version)throw Error('资料已更新，请重新勾选需要的分析项生成，旧报告仍会保留');if(!moduleSourceCount(INSIGHT_MODULES.find(x=>x.key===key).source))throw Error('请先补充本项需要的资料');await startAI('insights','',[],{modules:[key],base_report_id:r.id});return true}
case'insight-section':document.getElementById(el.dataset.section)?.scrollIntoView({behavior:'smooth',block:'start'});return true;
case'view-keyword-report':goto('keywords');return true;
case'view-keyword-library':{const r=(state.project.ai_reports||[]).find(x=>x.id===el.dataset.report);if(!isModularInsight(r)||r.report.modules.clean?.status!=='success')throw Error('本次关键词库尚未完成');workflow.reportChoices[state.project.id]=r.id;goto('insights');document.getElementById('insight-'+r.id+'-clean')?.scrollIntoView({behavior:'smooth',block:'start'});return true}
case'keyword-data':quick.tab='keywords';quick.filter='all';goto('research');return true;
case'view-insights':goto('insights');return true;
case'translate-keywords':case'translate-posts':case'translate-reviews':case'translate-current':{
 const target=action==='translate-current'?quick.tab:action.slice('translate-'.length);
 if(!['keywords','posts','reviews'].includes(target))throw Error('请选择关键词、内容或评论翻译');
 const postId=el.dataset?.postId;
 const ids=postId!==undefined?(state.project.reviews||[]).filter(x=>x.post_id===postId).map(x=>x.id):[...state.selected].filter(id=>(state.project[target]||[]).some(x=>x.id===id));
 if(postId!==undefined&&(target!=='reviews'||!ids.length))throw Error('这条内容还没有可翻译的评论，请先采集');
 await startAI('translate',target,ids);return true
}
case'cancel-ai':workflow.aiJob=await api('/api/ai/jobs/'+workflow.aiJob.id+'/cancel',{});render();return true;
case'retry-ai':{
 const j=workflow.aiJob;let ids=[];
 if(j.schema_version===2){goto('insights');return true}
 if(j.kind==='translate'){const prefix=j.target+':';ids=(j.scope?.evidence_ids||[]).filter(x=>x.startsWith(prefix)).map(x=>x.slice(prefix.length));if(!ids.length)throw Error('原翻译任务缺少范围，请重新选择需要翻译的记录')}
 await startAI(j.kind,j.target||'',ids);return true
}
case'search-topic':{const ids=JSON.parse(el.dataset.ids);const words=state.project.keywords.filter(x=>ids.includes(x.id));collectModal('posts',words.map(x=>x.text).join('\n'),[...new Set(words.map(x=>x.platform).filter(x=>PLATFORM_NAMES[x]))]);return true}
case'ai-evidence':{
 const refs=JSON.parse(el.dataset.evidence),parent=(state.project.ai_reports||[]).find(x=>x.id===el.dataset.report),key=el.dataset.module;
 if(key&&(!isModularInsight(parent)||!parent.report.modules[key]))throw Error('本项报告不存在');
 const r=key?insightModuleContext(parent,key):parent;
 if(isModularInsight(parent)&&!key)throw Error('请从具体报告章节查看依据');
 if(key&&refs.some(ref=>!r.scope?.evidence_ids?.includes(ref)))throw Error('引用不属于本项报告的资料范围');
 modal('报告依据 · 分析时的原文',reportEvidenceHtml(r,refs),button('关闭','close'),true);return true
}
case'export-ai-md':case'export-ai-html':{
 const r=el.dataset.report?(state.project.ai_reports||[]).find(x=>x.id===el.dataset.report&&x.kind===el.dataset.kind):latestAI(el.dataset.kind);if(!r)throw Error('请先生成报告');
 if(action==='export-ai-md')download(r.kind+'-report.md',reportMarkdown(r),'text/markdown');
 else download(r.kind+'-report.html',reportDocument(state.project.name,`<h1>${esc(state.project.name)}</h1>${reportMeta(r)}${r.kind==='keywords'?keywordReportBody(r):insightReportBody(r,false)}${isModularInsight(r)?'':'<h2>原始证据快照</h2>'+reportEvidenceHtml(r)}`),'text/html');
 toast('报告已导出');return true
}
default:return false;
}}
document.addEventListener('change',event=>{const el=event.target;if(el.name==='insight-module'){const key=el.value,m=INSIGHT_MODULES.find(x=>x.key===key);if(!m||!state.project||activeAI()||!moduleSourceCount(m.source))return;const selected=new Set(selectedInsightModules());if(el.checked)selected.add(key);else selected.delete(key);workflow.moduleChoices[state.project.id]=INSIGHT_MODULES.filter(x=>selected.has(x.key)).map(x=>x.key);render()}else if(el.id==='insight-report-select'&&state.project){workflow.reportChoices[state.project.id]=el.value;render()}});

document.addEventListener('toggle',e=>{if(e.target.id==='analysis-settings'&&e.target.isConnected!==false&&state.project)workflow.analysisSettingsOpen[state.project.id]=e.target.open},true);
