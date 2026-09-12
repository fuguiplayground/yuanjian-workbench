/* Shared keyword controls for the main form and batch collector. */
const KEYWORD_MODE_LABELS={quick:'快速采集',az:'A～Z 穷尽',intent:'意图深挖'};
const KEYWORD_MODE_NOTES={quick:'只查询产品词本身，适合先看相关词。固定 1 轮。',az:'首轮查询产品词及 A～Z 扩词；后续轮次只继续搜索平台返回的新词。',intent:'首轮加入「怎么选、推荐、避坑」等意图词；海外平台使用英文模板，后续轮次继续搜索返回的新词。'};
function keywordOptions(value={}){
 const mode=Object.hasOwn(KEYWORD_MODE_LABELS,value.keyword_mode)?value.keyword_mode:'quick';
 return {keyword_mode:mode,rounds:mode==='quick'?1:Number(value.rounds||2),request_limit:Number(value.request_limit||200)};
}
function keywordControls(prefix,value={}){
 const o=keywordOptions(value),disabled=o.keyword_mode==='quick';
 return `<div class="keyword-depth"><fieldset><legend>采词方式</legend><div class="keyword-mode-picker">${Object.entries(KEYWORD_MODE_LABELS).map(([id,label])=>`<label><input type="radio" name="${prefix}-keyword-mode" value="${id}" ${o.keyword_mode===id?'checked':''}><span>${label}</span></label>`).join('')}</div></fieldset><div class="keyword-depth-options"><label for="${prefix}-keyword-rounds">采集轮数<select id="${prefix}-keyword-rounds" ${disabled?'disabled':''}>${[1,2,3,4,5,6].map(n=>`<option value="${n}" ${o.rounds===n?'selected':''}>${n} 轮</option>`).join('')}</select></label><label for="${prefix}-keyword-limit">本次请求上限<input id="${prefix}-keyword-limit" type="number" min="1" max="500" step="1" value="${o.request_limit}" ${disabled?'disabled':''}></label></div><p class="caption" id="${prefix}-keyword-description">${KEYWORD_MODE_NOTES[o.keyword_mode]}</p></div>`;
}
function readKeywordControls(prefix){
 const mode=document.querySelector(`input[name="${prefix}-keyword-mode"]:checked`)?.value||'quick';
 const o=keywordOptions({keyword_mode:mode,rounds:Number(document.querySelector(`#${prefix}-keyword-rounds`)?.value||2),request_limit:Number(document.querySelector(`#${prefix}-keyword-limit`)?.value||0)});
 if(mode!=='quick'){
  o.request_limit=Number(document.querySelector(`#${prefix}-keyword-limit`)?.value);
  if(!Number.isInteger(o.request_limit)||o.request_limit<1||o.request_limit>500)throw Error('采词请求上限须为 1 至 500 的整数');
  if(!Number.isInteger(o.rounds)||o.rounds<1||o.rounds>6)throw Error('采集轮数须为 1 至 6 的整数');
 }
 return o;
}
function refreshKeywordControls(prefix){
 const mode=document.querySelector(`input[name="${prefix}-keyword-mode"]:checked`)?.value||'quick';
 const rounds=document.querySelector(`#${prefix}-keyword-rounds`),limit=document.querySelector(`#${prefix}-keyword-limit`);
 if(rounds){const wasDisabled=rounds.disabled;rounds.disabled=mode==='quick';if(mode==='quick')rounds.value='1';else if(wasDisabled)rounds.value='2'}
 if(limit)limit.disabled=mode==='quick';
 const note=document.querySelector(`#${prefix}-keyword-description`);if(note)note.textContent=KEYWORD_MODE_NOTES[mode];
}
function keywordRequestBody(options){const o=keywordOptions(options);return {keyword_mode:o.keyword_mode,rounds:o.rounds,...(o.keyword_mode==='quick'?{}:{request_limit:o.request_limit})}}
function keywordBudget(options,queries,platforms){
 const o=keywordOptions(options),translation=platforms.some(p=>p!=='xhs')?queries.filter(q=>/[\u3400-\u9fff]/.test(q)).length:0;
 if(o.keyword_mode==='quick'){
  const tikhub=queries.length*platforms.filter(p=>p!=='amazon').length+translation,mcp=queries.length*(platforms.includes('amazon')?1:0);
  return {total:tikhub+mcp,tikhub,mcp,translation};
 }
 const total=o.request_limit,remaining=Math.max(0,total-translation),n=platforms.length;
 let tikhub=Math.min(total,translation),mcp=0;
 platforms.forEach((p,i)=>{const count=Math.floor(remaining/n)+(i<remaining%n?1:0);if(p==='amazon')mcp+=count;else tikhub+=count});
 return {total,tikhub,mcp,translation};
}
function keywordBudgetText(options,queries,platforms){
 if(!platforms.length)return '请选择至少一个平台。';
 const o=keywordOptions(options),b=keywordBudget(o,queries,platforms);
 return `${KEYWORD_MODE_LABELS[o.keyword_mode]} · ${o.rounds} 轮，最多 ${b.total} 次请求：TikHub 最多 ${b.tikhub} 次（保守约 US$${(b.tikhub*.01).toFixed(2)}）${b.mcp?'，另用卖家精灵 '+b.mcp+' 次查询':''}。${o.keyword_mode==='quick'?(b.total>20?'超过快速采集 20 次上限，请减少词数或平台。':''):'各平台分配独立预算；达到上限会停止并保留结果，不保证完成全部扩词。'}费用以供应商账单为准。`;
}
function keywordRoundsHtml(run){
 if(!run.round_results?.length)return '';
 const labels={running:'进行中',success:'完成',partial:'部分完成',failed:'未完成',cancelled:'已取消',capped:'预算停止',interrupted:'已中断'};
 return `<h3>每轮采集结果</h3><p class="caption">${esc(KEYWORD_MODE_LABELS[run.keyword_mode]||'快速采集')} · 最多 ${esc(run.rounds)} 轮${run.capped?' · 已按预算停止，保留已采集资料':''}</p><div class="table-wrap"><table><tr><th>平台</th><th>轮次</th><th>查询</th><th>新增词</th><th>重复词</th><th>状态</th></tr>${run.round_results.map(x=>`<tr><td>${esc(PLATFORM_NAMES[x.platform]||x.platform)}</td><td>${esc(x.round)}</td><td>${esc(x.queries)}</td><td>${esc(x.new_keywords)}</td><td>${esc(x.duplicates)}</td><td>${esc(labels[x.status]||x.status)}</td></tr>`).join('')}</table></div>`;
}
