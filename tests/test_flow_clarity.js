// 运行实际渲染函数，验证指引、报告状态与只读打开行为。
const assert=require('node:assert/strict');
const {harness,fixture}=require('./test_workflow');
const {reportFixture}=require('./test_insight_modules');
function cleanReport(p,id='clean-only') {
 return {id,kind:'insights',schema_version:2,status:'partial',data_version:p.data_version,
  requested_modules:['clean'],report:{title:'关键词库报告',modules:{clean:{status:'success',data_version:p.data_version,
   scope:{processed:2,total:2,evidence_ids:[]},evidence_snapshot:[],
   report:{title:'已完成的关键词库',summary:'有据摘要',items:[],findings:[],next_steps:[]}}}}};
}
async function main(){
 const p=fixture();p.ai_reports=[cleanReport(p)];const h=harness(p);
 const report=h.run('reportWorkspace()');
 assert.match(report,/data-action="view-keyword-library"[^>]*data-report="clean-only"/);
 assert.doesNotMatch(report,/尚未生成；先采关键词/);
 assert.doesNotMatch(report,/data-action="ai-keywords"/);
 assert.doesNotMatch(h.run('fullReportHtml()'),/关键词报告尚未生成/);
 assert.match(h.run('fullReportHtml()'),/有据摘要/);
 const separate=fixture(),clean=reportFixture('clean-first'),later=reportFixture('audience-later');
 clean.requested_modules=['clean'];clean.report.modules={clean:clean.report.modules.clean};
 const cleanBody=clean.report.modules.clean.report;
 cleanBody.summary='独立清洗摘要 <需复核>';cleanBody.quality='limited';cleanBody.limitations=['独立清洗缺口 <未覆盖>'];
 later.requested_modules=['audience','intent','topics','summary'];
 later.report.modules=Object.fromEntries(later.requested_modules.map(key=>[key,later.report.modules[key]]));
 separate.ai_reports=[clean,later];const separateView=harness(separate),full=separateView.run('fullReportHtml()');
 const cleanSection=full.split('<h2>需求与营销建议</h2>')[0];
 for(const text of [cleanBody.title,'SAVED_KEYWORD'])assert.ok(cleanSection.includes(text),text);
 assert.match(cleanSection,/独立清洗摘要 &lt;需复核&gt;/);
 assert.match(cleanSection,/资料有限，请结合本项缺口阅读/);
 assert.match(cleanSection,/独立清洗缺口 &lt;未覆盖&gt;/);
 assert.ok(full.includes(later.report.modules.audience.report.audiences[0].one_line));
 assert.equal(separateView.calls.length,0);
 const combined=fixture(),combinedReport=reportFixture('combined');combined.ai_reports=[combinedReport];
 const combinedHtml=harness(combined).run('fullReportHtml()');
 assert.equal((combinedHtml.match(/id="insight-combined-clean"/g)||[]).length,1,'同一报告中的关键词章节只导出一次');
 h.fields['#insight-clean-only-clean']={scrollIntoView(){}};
 await h.run("workflowAction('view-keyword-library',{dataset:{report:'clean-only'}})");
 assert.equal(h.run('selectedInsightReport().id'),'clean-only');assert.equal(h.calls.length,0);
 const workspace=h.run('insightWorkspace()');
 assert.ok(workspace.indexOf('本项目的洞察报告')<workspace.indexOf('这次重点看什么'));
 assert.match(workspace,/<details[^>]*class="analysis-settings"[^>]*><summary>调整分析内容/);
 h.state.project.data_version++;
 assert.match(h.run('reportWorkspace()'),/旧数据|资料已更新/);
 const empty=fixture();empty.keywords=[];empty.posts=[];empty.reviews=[];
 assert.match(harness(empty).run('nextStep()'),/采集关键词/);
 const words=fixture();words.posts=[];words.reviews=[];
 assert.match(harness(words).run('nextStep()'),/data-page="keywords"/);
 const posts=fixture();posts.keywords=[];posts.reviews=[];
 assert.match(harness(posts).run('nextStep()'),/data-action="quick-tab"[^>]*data-tab="posts"/);
 assert.match(harness(fixture()).run('nextStep()'),/关键词清洗/);
 const settings=harness(null);settings.fire('toggle',{id:'quick-settings',open:true});
 assert.match(settings.run('research()'),/<details[^>]*id="quick-settings"[^>]*open/);
 const first=harness(null).run('research()');
 assert.match(first,/从搜索词，找到具体的人/);
 assert.match(first,/<details[^>]*class="research-settings"/);
 assert.match(first,/目标市场：美国 Amazon/);
 assert.match(first,/跨市场参考/);
 assert.match(first,/id="quick-keyword-budget"/);
 const legacy=fixture();legacy.ai_reports=[{id:'v1',kind:'keywords',status:'success',data_version:2,report:{title:'旧版报告'}}];
 assert.match(harness(legacy).run('reportWorkspace()'),/data-action="view-keyword-report"/);
 console.log('流程清晰化：新版和旧版汇总入口、过期提示、结果优先、四种资料指引、首屏边界与零模型调用通过。');
}
main().catch(e=>{console.error(e);process.exitCode=1});
