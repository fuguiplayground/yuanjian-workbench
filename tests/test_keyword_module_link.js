// Exercise the real keyword table, saved-report entry and workflow handlers.
const assert=require('node:assert/strict');
const {harness,fixture}=require('./test_workflow');
const clone=value=>JSON.parse(JSON.stringify(value));

function keywordReport(project,id='legacy',theme='旧版主题'){
 const evidence=project.keywords.map(k=>({...k,id:'keywords:'+k.id,row_id:k.id,kind:'keywords',text_truncated:false}));
 return {id,kind:'keywords',schema_version:1,status:'success',data_version:project.data_version,
  scope:{processed:evidence.length,total:evidence.length,evidence_ids:evidence.map(e=>e.id)},evidence_snapshot:evidence,
  report:{title:'旧版关键词结果',summary:'旧版摘要',findings:[],next_steps:[],items:project.keywords.map(k=>({id:'keywords:'+k.id,theme:theme+k.id,
   intent:'旧版意图',valid:true,reason:'原词依据',w5h1:'HOW',stage:'A4',emotion:'中性'}))}};
}
function modular(project,id='modular'){
 const old=keywordReport(project,id,'新版主题');
 return {id,kind:'insights',schema_version:2,status:'partial',data_version:project.data_version,
  report:{title:'按模块分析',modules:{clean:{status:'success',data_version:project.data_version,scope:old.scope,evidence_snapshot:old.evidence_snapshot,
   report:{...old.report,title:'本次关键词库',summary:'本次清洗结果',items:old.report.items.map(x=>({...x,intent:'新版意图',valid:false}))}}}}};
}

async function main(){
 const p=fixture(),old=keywordReport(p),clean=modular(p),failed=modular(p,'failed');failed.report.modules.clean.status='failed';
 p.ai_reports=[old,clean,failed];
 const app=harness(p),before=JSON.stringify(app.state.project),table=app.run('keywordTable(state.project.keywords)');
 assert.match(table,/新版主题k1/);assert.match(table,/新版意图/);assert.match(table,/待排除词/);
 assert.doesNotMatch(table,/旧版主题/);
 assert.equal(app.run('latestKeywordClassification().id'),'modular','failed clean does not hide the latest successful clean');
 assert.equal(app.run("latestAI('keywords').id"),'legacy','the existing v1 report and exporter lookup is unchanged');
 assert.equal(JSON.stringify(app.state.project),before,'classification is display-only and preserves every source row');

 const later=keywordReport(app.state.project,'later-v1','最后报告主题');later.finished_at='2000-01-01';
 app.state.project.ai_reports.push(later);
 assert.match(app.run('keywordTable(state.project.keywords)'),/最后报告主题k1/,'report array order determines the latest completed classification');
 assert.equal(app.run('latestKeywordClassification(true).id'),'modular','the module entry still finds the latest successful clean');

 for(const mismatch of ['data_version','text','platform','snapshot','truncated','module_version']){
  const current=fixture(),r=modular(current);current.ai_reports=[keywordReport(current),r];
  if(mismatch==='data_version')current.data_version++;
  if(mismatch==='text')current.keywords[0].text='同ID替换的新词';
  if(mismatch==='platform')current.keywords[0].platform='tiktok';
  if(mismatch==='snapshot')r.report.modules.clean.evidence_snapshot=[];
  if(mismatch==='truncated')r.report.modules.clean.evidence_snapshot[0].text_truncated=true;
  if(mismatch==='module_version')r.report.modules.clean.data_version--;
  const view=harness(current),html=view.run('keywordTable([state.project.keywords[0]])');
  assert.doesNotMatch(html,/新版主题|新版意图|旧版主题|待排除词/,mismatch+' must not attach an old judgment to a changed or unverifiable row');
  if(mismatch==='data_version'||mismatch==='module_version')assert.match(html,/旧分析的分类未套用/);
 }
 const partial=fixture(),subset=modular(partial);subset.report.modules.clean.report.items=subset.report.modules.clean.report.items.slice(0,1);
 partial.ai_reports=[keywordReport(partial),subset];
 const subsetView=harness(partial);
 assert.doesNotMatch(subsetView.run('keywordTable([state.project.keywords[1]])'),/主题k2|旧版意图|新版意图/,'uncovered IDs are not filled from another report');

 const only=fixture(),target=modular(only,'chosen-report'),newer=modular(only,'newer-failed');newer.report.modules.clean.status='failed';
 only.ai_reports=[target,newer];const linked=harness(only),workspace=linked.run('keywordWorkspace()');
 assert.match(workspace,/查看本次关键词库/);
 assert.doesNotMatch(workspace,/生成关键词报告|data-action="ai-keywords"/,'a completed v2 clean does not ask for a duplicate v1 report');
 const button=workspace.match(/<button[^>]*data-action="view-keyword-library"[^>]*>/)[0];
 const action=button.match(/data-action="([^"]+)"/)[1],report=button.match(/data-report="([^"]+)"/)[1];
 let scrolled=0;linked.fields['#insight-chosen-report-clean']={scrollIntoView(options){assert.equal(options.block,'start');scrolled++}};
 linked.fire('change',{id:'insight-report-select',value:'newer-failed'});
 await linked.run(`workflowAction(${JSON.stringify(action)}, {dataset:{report:${JSON.stringify(report)}}})`);
 assert.equal(linked.state.page,'insights');
 assert.equal(linked.run('selectedInsightReport().id'),'chosen-report','entry selects its exact report instead of whichever report was last viewed');
 assert.equal(scrolled,1);assert.equal(linked.context.location.hash,'insights?project=project-a');
 assert.equal(linked.calls.length,0,'viewing a saved keyword library never invokes a model or HTTP');
 await assert.rejects(linked.run("workflowAction('view-keyword-library',{dataset:{report:'newer-failed'}})"),/尚未完成/);

 const legacy=fixture();legacy.ai_reports=[keywordReport(legacy)];const v1=harness(legacy);
 assert.match(v1.run('keywordTable(state.project.keywords)'),/旧版主题k1/);
 assert.match(v1.run('keywordWorkspace()'),/旧版摘要/);
 assert.doesNotMatch(v1.run('keywordWorkspace()'),/view-keyword-library/);
 await v1.run("workflowAction('export-ai-md',{dataset:{kind:'keywords'}})");
 assert.equal(v1.downloads[0].name,'keywords-report.md');assert.match(v1.downloads[0].body,/旧版主题k1/);
 assert.equal(v1.calls.length,0);
 console.log('Keyword module link: latest v1/v2 ordering, snapshot/version safety, partial coverage, exact clean navigation and legacy export passed.');
}
if(require.main===module)main().catch(error=>{console.error(error);process.exitCode=1});
