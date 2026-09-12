/* Continuous research flow, Codex reports and source-preserving translation. */
const workflow={aiJob:null,poll:null};
function flowNav(active){if(active==='posts')active='research';return `<nav class="flow-nav" aria-label="关键词洞察步骤">${[['research','采集资料'],['keywords','关键词分析'],['insights','需求与营销']].map(([id,label],i)=>`<button class="${id===active?'active':''}" data-action="navigate" data-page="${id}"><span>${i+1}</span>${label}</button>`).join('')}</nav>`}
function latestAI(kind){return [...(state.project?.ai_reports||[])].reverse().find(x=>x.kind===kind&&x.status==='success')}
function activeAI(){return workflow.aiJob?.project_id===state.project?.id&&workflow.aiJob.status==='running'}
function aiProgress(){const j=workflow.aiJob;if(!j||j.project_id!==state.project?.id)return '';const labels={keywords:'关键词分析',insights:'需求与营销建议',translate:'中文翻译'};return `<div class="collection-progress" role="status"><div><strong>${labels[j.kind]||'AI'} · ${{running:'Codex 正在处理',success:'已完成',failed:'未完成',cancelled:'已取消',interrupted:'已中断'}[j.status]||j.status}</strong><p>${esc(j.message||'结果会自动保存，可以先查看其他页面。')}</p>${j.scope?`<p class="caption">本次处理 ${j.scope.processed} / ${j.scope.total} 条${j.scope.truncated?' · '+j.scope.truncated+' 条未覆盖':''}${j.kind==='translate'?'；每批最多 20 条，已有译文会跳过。':''}</p>`:''}</div><div class="actions">${j.status==='running'?button('停止','cancel-ai','','small'):['failed','interrupted','cancelled'].includes(j.status)?button('重试','retry-ai','','small'):''}</div></div>`}
function reportMeta(r){if(!r)return '';const scope=r.scope||{},counts=scope.counts||{};const bits=Object.entries(counts).filter(([,v])=>v.total).map(([k,v])=>`${{keywords:'关键词',posts:'内容',reviews:'评论'}[k]||k} ${v.processed}/${v.total}`);return `<p class="report-meta">本地 Codex · ${date(r.finished_at||r.created_at)} · ${esc(bits.join(' · ')||`${scope.processed||0}/${scope.total||0} 条`)}${scope.truncated?' · 部分样本，未覆盖全部资料':''}${scope.text_truncated?' · '+scope.text_truncated+' 条原文已截断，分析仅使用保存的摘录':''}</p>${r.data_version!==state.project.data_version?`<div class="source-note">已补充或更新资料。这份报告基于旧数据，可点击「重新分析」更新。</div>`:''}`}
function reportControls(kind,r){
 const p=state.project,hasData=kind==='keywords'?p.keywords.length:p.keywords.length+(p.posts||[]).length+p.reviews.length;
 return `<div class="actions">${button(r?'重新分析':kind==='keywords'?'生成关键词报告':'生成需求与营销建议',kind==='keywords'?'ai-keywords':'ai-insights','',r?'':'primary',activeAI()||!hasData?'disabled':'')}${r?button('导出 Markdown','export-ai-md','download','small',`data-kind="${kind}"`)+button('导出 HTML','export-ai-html','download','small',`data-kind="${kind}"`):''}</div>`
}
function keywordTable(rows){const selected=state.project.keywords.filter(r=>state.selected.has(r.id)).length;const report=latestAI('keywords');const items=new Map((report?.report?.items||[]).map(x=>[x.id.replace(/^keywords:/,''),x]));return `<div class="selection-bar"><span>已选 ${selected} 个词</span><div class="actions">${button('用所选词搜索内容','selected-search','arrow','small',selected?'':'disabled')}${button('翻译所选词','translate-keywords','','small',selected?'':'disabled')}</div></div><div class="table-wrap"><table><thead><tr><th><input type="checkbox" id="select-all" aria-label="选择当前关键词" ${rows.length&&rows.every(k=>state.selected.has(k.id))?'checked':''}></th><th>关键词 / 中文</th><th>平台</th><th>主题 / 意图</th><th>搜索量</th><th>下一步</th></tr></thead><tbody>${rows.map(k=>{const a=items.get(k.id);return `<tr><td><input type="checkbox" data-select="${esc(k.id)}" aria-label="选择 ${esc(k.text)}" ${state.selected.has(k.id)?'checked':''}></td><td><strong>${esc(k.text)}</strong><div class="secondary">${esc(k.translation||(k.platform==='xhs'?'原词为中文':'待翻译'))}</div></td><td>${esc(PLATFORM_NAMES[k.platform]||k.platform||'导入')}<div class="secondary">${source(k)}</div></td><td>${esc(a?.theme||k.scene||'待分析')}<div class="secondary">${esc(a?.intent||k.intent||'待分析')}${a?.valid===false?' · 待排除词':''}</div></td><td>${k.search_volume??'未提供'}<div class="secondary">${esc(k.search_period||'')}</div></td><td>${button('搜内容','keyword-search','arrow','small',`data-id="${esc(k.id)}"`)}</td></tr>`}).join('')}</tbody></table></div>`}
function keywordWorkspace(){
 const r=latestAI('keywords');
 return head('关键词分析','把采到的词整理成主题与搜索意图，再挑选值得继续验证的方向。',button('返回关键词资料','keyword-data','arrow',''))
  +flowNav('keywords')+demoNote()+jobView()+aiProgress()
  +`<section class="report-sheet"><div class="section-head"><h2>${esc(r?.report?.title||'从已有关键词中找需求线索')}</h2>${reportControls('keywords',r)}</div>
  ${r?reportMeta(r)+keywordReportBody(r):empty('关键词采完以后，在这里看结论','点击上方「生成关键词报告」，整理有效词、5W1H、搜索意图、主题与下一步研究方向。')}</section>`
}
function evidenceButton(ids,label='查看依据',reportId=''){return ids?.length?`<span class="evidence-refs">证据：${ids.map(esc).join('、')}</span>`+button(`${label} ${ids.length}`,'ai-evidence','','small',`data-evidence="${esc(JSON.stringify(ids))}" data-report="${esc(reportId)}"`):'<span class="caption">待补充证据</span>'}
function statementList(rows,reportId=''){return (rows||[]).map(x=>`<article class="finding"><p>${esc(x.text)}</p>${evidenceButton(x.evidence_ids,'查看依据',reportId)}</article>`).join('')}
function reportEvidence(r,ref){
 const snapshot=r?.evidence_snapshot?.find(x=>x.id===ref),pos=ref.indexOf(':'),kind=ref.slice(0,pos),id=ref.slice(pos+1);
 const row=(state.project[kind]||[]).find(x=>x.id===id);
 const text=row?(kind==='keywords'?row.text:kind==='posts'?[row.title||'',row.body||''].join('\n').trim():row.body):'';
 if(snapshot){const same=row&&snapshot.text===(snapshot.text_truncated?text.slice(0,1200):text)&&['platform','source','market_scope','provenance'].every(k=>(snapshot[k]||'')===(row[k]||''));return {...snapshot,snapshot:true,source_url:same?row.source_url:'',translation:same&&!snapshot.text_truncated?row.translation:''}}
 return row?{id:ref,kind,row_id:id,text,platform:row.platform,source:row.source,source_url:row.source_url,translation:row.translation,snapshot:false}:null;
}
function reportKeyword(r,id){return reportEvidence(r,id.startsWith('keywords:')?id:'keywords:'+id)?.text||id}
function reportEvidenceHtml(r,refs=r?.scope?.evidence_ids||[]){return refs.map(ref=>{const e=reportEvidence(r,ref);return `<article class="finding"><h3>${esc(ref)}</h3>${e?`<p style="white-space:pre-wrap">${esc(e.text)}</p>${e.translation?`<p class="translation-preview">${esc(e.translation)}</p>`:''}<p class="caption">${esc(PLATFORM_NAMES[e.platform]||e.platform||e.source||'来源未注明')} · ${e.snapshot?'分析时保存的原文':'旧报告缺少输入快照；这里是当前记录，仅供参考'}${e.text_truncated?' · 原文已截断，仅分析此摘录':''} · ${external(e.source_url)}</p>`:'<p>这份报告未保存该条证据快照，当前项目也没有对应原文。</p>'}</article>`}).join('')}
function keywordReportBody(r){const report=r.report||{},items=report.items||[];const valid=items.filter(x=>x.valid),themes=[...new Set(valid.map(x=>x.theme).filter(Boolean))],how=valid.filter(x=>String(x.w5h1).toUpperCase()==='HOW');return `<p class="report-summary">${esc(report.summary)}</p><div class="report-numbers">${[['已分析',items.length],['有效词',valid.length],['归一主题',themes.length],['HOW 方法词',how.length]].map(([l,n])=>`<div><strong>${n}</strong><span>${l}</span></div>`).join('')}</div><h3>关键发现</h3>${statementList(report.findings,r.id)}<h3>5W1H · 用户怎样搜索</h3><div class="intent-distribution">${(report.stats?.w5h1||[]).map(x=>`<div><span>${esc(x.name)}</span><i style="width:${Math.min(100,Math.max(0,Number(x.count)/(items.length||1)*100))}%"></i><b>${Number(x.count)||0}</b></div>`).join('')}</div><h3>主题地图 · 从这组词继续搜索</h3><div class="table-wrap"><table><tr><th>主题</th><th>证据关键词</th><th>继续调研</th></tr>${themes.map(theme=>{const matches=valid.filter(x=>x.theme===theme),ids=matches.map(x=>x.id.replace(/^keywords:/,'')),words=matches.map(x=>reportKeyword(r,x.id));return `<tr><td><strong>${esc(theme)}</strong><div class="secondary">${[...new Set(matches.map(x=>x.intent))].map(esc).join('、')}</div></td><td>${words.map(esc).join('、')}</td><td>${button('搜这组词','search-topic','arrow','small',`data-ids="${esc(JSON.stringify(ids))}"`)}</td></tr>`}).join('')}</table></div><h3>下一步研究建议</h3>${statementList(report.next_steps,r.id)}<details class="report-details"><summary>查看逐词分析、5W1H 与待排除词（${items.length}）</summary><div class="table-wrap"><table><tr><th>词</th><th>5W1H</th><th>意图 / 阶段</th><th>判断依据</th></tr>${items.map(x=>{return `<tr><td>${esc(reportKeyword(r,x.id))}</td><td>${esc(x.w5h1)}</td><td>${esc(x.intent)}<div class="secondary">${esc(x.stage)}</div></td><td>${x.valid?'有效线索':'待排除'} · ${esc(x.reason)}</td></tr>`}).join('')}</table></div></details><p class="caption">关键词是搜索线索，人群和购买动机属于待验证推断；无效词只做标记，原数据保留。</p>`}
function insightWorkspace(){
 const p=state.project,r=latestAI('insights');
 return head('需求与营销','结合关键词、内容与评论，找出用户顾虑、使用场景和可验证的营销方向。',reportControls('insights',r))
  +flowNav('insights')+demoNote()+aiProgress()
  +`<div class="evidence-overview"><span>关键词 ${p.keywords.length}</span><span>内容 ${(p.posts||[]).length}</span><span>评论 ${p.reviews.length}</span><div class="spacer"></div>
  ${button('补采评论','navigate','arrow','small','data-page="posts"')}${button('翻译评论','translate-reviews','','small',p.reviews.length?'':'disabled')}${button('查看全部评论','all-reviews','','small',p.reviews.length?'':'disabled')}</div>
  ${r?`<section class="report-sheet">${reportMeta(r)}${insightReportBody(r)}</section>`:empty('用现有资料分析需求与营销方向','点击上方「生成需求与营销建议」。先找人群、触发场景和购买顾虑；只有关键词时，会明确提示证据不足。')}`
}
function insightReportBody(r){const a=r.report||{};return `<h2>${esc(a.title&&!a.title.includes('千机塔')?a.title:'需求与营销建议')}</h2><p class="report-summary">${esc(a.summary)}</p><section class="core-opportunity"><span class="eyebrow">核心机会</span><p>${esc(a.core_opportunity?.text)}</p>${evidenceButton(a.core_opportunity?.evidence_ids,'查看依据',r.id)}</section><h3>人群与购买动机</h3>${(a.audiences||[]).map((x,i)=>`<article class="audience-block"><div class="section-head"><h3>${i+1}. ${esc(x.name)}</h3>${evidenceButton(x.evidence_ids,'查看依据',r.id)}</div><p>${esc(x.why)}</p><dl class="audience-grid">${[['自然属性',x.natural],['社会属性',x.social],['消费特征',x.consumption],['触发场景',x.scene],['生活方式',x.lifestyle],['即时情绪',x.emotion],['深层情感',x.deep_emotion],['价值观',x.values],['显性需求',x.explicit_need],['隐性需求 · 待验证',x.implicit_need]].map(([l,v])=>`<div><dt>${l}</dt><dd>${esc(v||'证据不足')}</dd></div>`).join('')}</dl></article>`).join('')}<h3>营销选题与切入角度</h3>${(a.topics||[]).map(x=>`<article class="finding"><span class="badge">${esc(x.layer)}</span><h3>${esc(x.title)}</h3><p>${esc(x.angle)}</p><p class="caption">${esc(x.why)}</p>${evidenceButton(x.evidence_ids,'查看依据',r.id)}</article>`).join('')}<h3>待验证与谨慎判断</h3>${statementList(a.cautions,r.id)}${a.self_check?`<details class="report-details"><summary>千机塔四标准自检</summary><p>${esc(a.self_check.note)}</p><p>不制造焦虑：${a.self_check.no_anxiety?'通过':'需复核'} · 最窄切入：${a.self_check.narrowest?'通过':'需复核'} · 有对比：${a.self_check.has_contrast?'通过':'需复核'} · 真实需求：${a.self_check.real_demand?'通过':'需复核'}</p></details>`:''}<p class="caption">模型分析使用本次有限样本。隐性动机与营销选题是建议，不能当作真实消费者比例或确定市场结论。</p>`}
function selectionSummary(interactive=true){
 const p=state.project,a=latest(),candidates=p.products.filter(x=>x.candidate),decisions=(a?.decisions||[]).filter(d=>candidates.some(x=>x.id===d.product_id)),pending=candidates.filter(x=>!decisions.some(d=>d.product_id===x.id));
 return `<section class="flat-section"><div class="section-head"><h2>选品依据与待验证事项</h2>${interactive?button(a?'更新选品依据':'整理选品依据','analyze','refresh','',candidates.length?'':'disabled'):''}</div>${a?staleNote():''}
 ${decisions.map(d=>{const x=candidates.find(x=>x.id===d.product_id);return `<article class="finding"><div class="section-head"><h3>${esc(x.title)}</h3><span class="badge">${esc(d.status)}</span></div><p>${esc(d.reason)}</p><p><strong>待验证：</strong>${d.missing.map(esc).join('、')||'未记录'}</p><p class="caption">商品评论证据：${d.evidence_ids.map(id=>'reviews:'+esc(id)).join('、')||'暂无'}；项目级关键词 ${d.keyword_ids.length} 条，尚未验证与该商品匹配。</p>${interactive?button('查看商品评论依据 '+d.evidence_ids.length,'decision-evidence','','small',`data-id="${esc(x.id)}"`):''}</article>`}).join('')}
 ${pending.length?`<p class="muted">${pending.length} 个候选尚未整理选品依据。${interactive?'点击上方整理，将现有商品评价和缺失资料放在一起。':''}</p>`:!candidates.length?'<p class="muted">还没有候选商品。在电商盯盘加入候选后，可整理选品依据。</p>':''}
 <p class="caption">${a?'整理时间：'+date(a.created_at)+' · ':''}规则整理，无综合评分。「继续观察」表示证据不足；采购、物流、退货与使用测试需补齐后再判断。</p></section>`;
}
function reportWorkspace(){const p=state.project,kw=latestAI('keywords'),insight=latestAI('insights');return head('报告与选品','关键词分析、需求与营销建议和原始证据，保存在同一个项目。',button('导出完整报告','export-report','download','primary')+button('导出项目包','export-project','download'))+`${insight?`<section class="report-sheet"><span class="eyebrow">当前需求结论 · 待验证</span><h2>${esc(insight.report.title)}</h2><p class="report-summary">${esc(insight.report.core_opportunity?.text)}</p>${evidenceButton(insight.report.core_opportunity?.evidence_ids,'查看依据',insight.id)}<p class="caption">本次分析 ${insight.scope.processed} / ${insight.scope.total} 条资料，具体样本与限制见完整建议。</p></section>`:''}<section class="report-sheet"><div class="report-link-row"><div><h2>关键词分析</h2><p>${kw?date(kw.finished_at||kw.created_at)+' · '+esc(kw.report.title):'尚未生成；先采关键词，再分析。'}</p></div>${button(kw?'查看报告':'生成报告',kw?'view-keyword-report':'ai-keywords','arrow','',p.keywords.length?'':'disabled')}</div><div class="report-link-row"><div><h2>需求与营销建议</h2><p>${insight?date(insight.finished_at||insight.created_at)+' · '+esc(insight.report.title):'从人群、场景、需求与情感推导营销方向。'}</p></div>${button(insight?'查看建议':'生成建议',insight?'view-insights':'ai-insights','arrow','',p.keywords.length||(p.posts||[]).length||p.reviews.length?'':'disabled')}</div></section>${selectionSummary()}<section class="flat-section"><div class="section-head"><h2>候选商品</h2>${button('查看并比较商品','navigate','arrow','','data-page="products"')}</div>${p.products.filter(x=>x.candidate).map(x=>`<div class="report-link-row"><div><strong>${esc(x.title)}</strong><p>${money(x)} · ${esc(x.sales_raw||'销量未提供')}</p></div>${button('查看商品','product-detail','','small',`data-id="${esc(x.id)}"`)}</div>`).join('')||'<p class="muted">还没有候选商品，在商品列表加入后可并排比较。</p>'}</section><p class="caption">报告保留来源、采集时间和覆盖范围。成本、物流、退货与利润需另行核算，不从社交讨论直接推算销量。</p>`}
async function startAI(kind,target='',ids=[]){if(!state.project)throw Error('请先开始一次调研');if(activeAI())throw Error('当前 Codex 任务仍在运行');closeModal();if(kind==='keywords')goto('keywords');if(kind==='insights')goto('insights');workflow.aiJob=await api('/api/projects/'+state.project.id+'/ai',{revision:state.project.revision,kind,target,...(ids.length?{ids}:{})});clearTimeout(workflow.poll);render();await pollAI()}
async function pollAI(){const job=workflow.aiJob;if(!job)return;try{const next=await api('/api/ai/jobs/'+job.id);if(workflow.aiJob?.id!==job.id)return;workflow.aiJob=next;if(state.project?.id===next.project_id){state.project=await api('/api/projects/'+state.project.id);if(!state.modal&&!state.composing&&!['quick-query','search-input'].includes(document.activeElement?.id))render()}if(next.status==='running')workflow.poll=setTimeout(pollAI,1600);else toast(next.message||'Codex 任务已结束')}catch(e){toast(e.message)}}
async function resumeAI(){if(!state.project)return;const projectId=state.project.id;const jobs=await api('/api/ai/jobs?project='+projectId);if(state.project?.id!==projectId)return;const job=jobs.find(x=>x.status==='running')||jobs[0];if(job){clearTimeout(workflow.poll);workflow.aiJob=job;if(job.status==='running')await pollAI()}}
function reportDocument(title,body){return `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>${esc(title)}</title><style>body{font:15px/1.85 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;color:#26313c;max-width:980px;margin:44px auto;padding:0 24px}h1{font-size:30px}h2{margin-top:34px}h3{margin-top:28px}p{white-space:pre-wrap}table{width:100%;border-collapse:collapse;font-size:13px}td,th{border-bottom:1px solid #ddd;text-align:left;padding:12px}a{color:#1765d1}.report-numbers,.audience-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:20px}.report-numbers strong{display:block;font-size:26px}.secondary,.caption,.report-meta,dt{font-size:12px;color:#687480}.finding,.audience-block,.core-opportunity{padding:20px 0;border-bottom:1px solid #ddd}dd{margin:0}button,svg[aria-hidden="true"]{display:none}.watch-chart svg{display:block;width:100%;height:auto}.evidence-refs{display:block;font-size:12px;color:#687480}@media print{article,tr{break-inside:avoid}details{display:block}}</style><body>${body.replace(/<button\b[\s\S]*?<\/button>/g,'').replace(/<details[^>]*>/g,'<section>').replace(/<\/details>/g,'</section>')}</body></html>`}
function fullReportHtml(){
 const p=state.project,k=latestAI('keywords'),i=latestAI('insights');
 return reportDocument(p.name+' · 完整调研报告',`<h1>${esc(p.name)}</h1><p>产品词：${esc(p.keyword)} · 导出 ${esc(new Date().toLocaleString('zh-CN'))}</p>${demoNote()}
 ${k?'<h2>关键词报告</h2>'+reportMeta(k)+keywordReportBody(k)+'<h3>关键词报告 · 原始证据快照</h3>'+reportEvidenceHtml(k):'<p>关键词报告尚未生成。</p>'}
 ${i?'<h2>需求与营销建议</h2>'+reportMeta(i)+insightReportBody(i)+'<h3>需求与营销 · 原始证据快照</h3>'+reportEvidenceHtml(i):'<p>需求与营销建议尚未生成。</p>'}
 ${selectionSummary(false)}${watchReportHtml()}
 <h2>当前项目资料</h2><p>下列资料含后续补采与中文译文；旧报告实际使用的原文以上方证据快照为准。</p>
 <h3>关键词与中文</h3><table><tr><th>编号</th><th>关键词</th><th>中文</th><th>平台 / 时间</th></tr>${p.keywords.map(x=>`<tr><td>keywords:${esc(x.id)}</td><td>${esc(x.text)}</td><td>${esc(x.translation)}</td><td>${esc(PLATFORM_NAMES[x.platform]||x.source)} / ${date(x.collected_at)}</td></tr>`).join('')}</table>
 <h3>商品资料</h3>${p.products.map(x=>`<p>${esc(x.title)} · ${money(x)}<br>${esc(x.sales_raw||'销量未提供')} · ${external(x.source_url)}</p>`).join('')}
 <h3>内容原文与中文</h3>${(p.posts||[]).map(x=>`<article><h3>${esc(x.title)}</h3><p>${esc(x.body)}</p><p>${esc(x.translation)}</p><p>posts:${esc(x.id)} · ${esc(PLATFORM_NAMES[x.platform])} · ${external(x.source_url)}</p></article>`).join('')}
 <h3>评论原文与中文</h3>${p.reviews.map(reviewBlock).join('')}`);
}
function reportMarkdown(r){
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
case'ai-insights':await startAI('insights');return true;
case'view-keyword-report':goto('keywords');return true;
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
 if(j.kind==='translate'){const prefix=j.target+':';ids=(j.scope?.evidence_ids||[]).filter(x=>x.startsWith(prefix)).map(x=>x.slice(prefix.length));if(!ids.length)throw Error('原翻译任务缺少范围，请重新选择需要翻译的记录')}
 await startAI(j.kind,j.target||'',ids);return true
}
case'search-topic':{const ids=JSON.parse(el.dataset.ids);const words=state.project.keywords.filter(x=>ids.includes(x.id));collectModal('posts',words.map(x=>x.text).join('\n'),[...new Set(words.map(x=>x.platform).filter(x=>PLATFORM_NAMES[x]))]);return true}
case'ai-evidence':{
 const refs=JSON.parse(el.dataset.evidence),r=(state.project.ai_reports||[]).find(x=>x.id===el.dataset.report);
 modal('报告依据 · 分析时的原文',reportEvidenceHtml(r,refs),button('关闭','close'),true);return true
}
case'export-ai-md':case'export-ai-html':{
 const r=latestAI(el.dataset.kind);if(!r)throw Error('请先生成报告');
 if(action==='export-ai-md')download(r.kind+'-report.md',reportMarkdown(r),'text/markdown');
 else download(r.kind+'-report.html',reportDocument(state.project.name,`<h1>${esc(state.project.name)}</h1>${reportMeta(r)}${r.kind==='keywords'?keywordReportBody(r):insightReportBody(r)}<h2>原始证据快照</h2>${reportEvidenceHtml(r)}`),'text/html');
 toast('报告已导出');return true
}
default:return false;
}}
