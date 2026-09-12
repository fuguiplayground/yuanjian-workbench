const assert=require('node:assert/strict');
const {harness,fixture}=require('./test_workflow');
const {reportFixture}=require('./test_insight_modules');
(async()=>{
 const p=fixture();p.ai_reports=[reportFixture()];const h=harness(p);
 for(const page of ['audience','strategy']){
  h.state.page=page;
  const html=h.run('audienceWorkspace()');
  assert.match(html,/人群策略三步/);assert.match(html,/返回词库补证据/);
  assert.doesNotMatch(html,/undefined|\[object Object\]/);
 }
 h.state.page='strategy';const strategy=h.run('audienceWorkspace()');
 for(const title of ['产品策略','渠道','内容','达人','促销'])assert.ok(strategy.includes(title));
 assert.match(strategy,/旧报告没有这一项/);assert.match(strategy,/strategy-workbench/);assert.match(strategy,/person-rail/);assert.match(strategy,/场景与决策过程/);assert.match(strategy,/模型推断/);
 assert.match(strategy,/data-module="audience"/);
 const second=JSON.parse(JSON.stringify(h.state.project.ai_reports[0].report.modules.audience.report.audiences[0]));
 second.name='第二类人群';second.one_line='SECOND_AUDIENCE';
 h.state.project.ai_reports[0].report.modules.audience.report.audiences.push(second);
 await h.run("workflowAction('choose-audience',{dataset:{index:'1'}})");
 assert.equal(h.state.page,'strategy');assert.equal(h.run('audiencePerson(selectedInsightReport()).index'),1);
 h.state.page='strategy';assert.match(h.run('audienceWorkspace()'),/value="1" selected/);
 h.state.project.ai_reports[0].report.modules.audience.report.audiences[1].name='<img src=x onerror=alert(1)>';
 assert.doesNotMatch(h.run('audienceWorkspace()'),/<img src=x/);
 h.state.project.data_version++;assert.match(h.run('audienceWorkspace()'),/旧数据/);
 h.state.page='audience';assert.match(h.run('audienceWorkspace()'),/audience-matrix/);assert.match(h.run('audienceWorkspace()'),/展开需求、购买决策与替代方案/);h.state.page='strategy';
 const record=h.state.project.ai_reports[0];
 record.report.modules.segments=JSON.parse(JSON.stringify(record.report.modules.audience));
 record.report.modules.segments.report.audiences.forEach((x,i)=>{x.marketing={product:{text:'PRODUCT_'+i,basis:'unknown',evidence_ids:[],validation:'待实测'}}});
 h.run("workflow.audienceSelection={}");
 assert.match(h.run('audienceWorkspace()'),/PRODUCT_0/);assert.doesNotMatch(h.run('audienceWorkspace()'),/PRODUCT_1/);
 await h.run("workflowAction('choose-audience',{dataset:{index:'1'}})");
 assert.match(h.run('audienceWorkspace()'),/PRODUCT_1/);assert.doesNotMatch(h.run('audienceWorkspace()'),/PRODUCT_0/);
 for(const page of ['nine','tower','content']){h.state.page=page;const html=h.run('audienceLensWorkspace()');assert.doesNotMatch(html,/undefined|\[object Object\]/);assert.match(html,/strategy-audience/);}
 assert.match(h.run('skillWorkspace()'),/原始私有检索数据库未接入/);
 assert.match(h.run('skillWorkspace()'),/消费动机洞察/);
 for(const page of ['audience','strategy']){h.state.page=page;assert.doesNotMatch(h.run('audienceWorkspace()'),/九维/i);}
 h.state.page='nine';assert.match(h.run('audienceLensWorkspace()'),/消费动机洞察/);
 assert.doesNotMatch(h.run('skillWorkspace()'),/九维/i);
 const empty=harness(fixture());empty.state.page='strategy';assert.match(empty.run('audienceWorkspace()'),/把词背后的人/);
 assert.match(empty.run('audienceWorkspace()'),/material-ledger/);assert.match(empty.run('audienceWorkspace()'),/当前资料预览/);
 await empty.run("workflowAction('prepare-audience-flow',{})");assert.equal(empty.calls.length,0);
 assert.equal(empty.state.page,'insights');
 assert.equal(h.calls.length,0);
 console.log('人群主线：四个页面、八层口径、原始证据、过期提示、空态和零模型调用通过');
})().catch(e=>{console.error(e);process.exitCode=1});
