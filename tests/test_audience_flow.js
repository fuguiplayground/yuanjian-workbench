const assert=require('node:assert/strict');
const {harness,fixture}=require('./test_workflow');
const {reportFixture}=require('./test_insight_modules');
(async()=>{
 const p=fixture();p.ai_reports=[reportFixture()];const h=harness(p);
 for(const page of ['audience','tower','strategy','content']){
  h.state.page=page;
  const html=h.run('audienceWorkspace()');
  assert.match(html,/同一份报告/);assert.match(html,/下一步|返回人群策略/);
  assert.doesNotMatch(html,/undefined|\[object Object\]/);
 }
 h.state.page='tower';const tower=h.run('audienceWorkspace()');
 for(const title of ['基本属性','社会身份','消费模式','行为场景','生活方式','情绪状态','决策障碍','隐秘欲望'])assert.ok(tower.includes(title));
 assert.match(tower,/旧报告未单独记录/);assert.match(tower,/模型推断/);
 assert.match(tower,/data-module="audience"/);
 const second=JSON.parse(JSON.stringify(h.state.project.ai_reports[0].report.modules.audience.report.audiences[0]));
 second.name='第二类人群';second.one_line='SECOND_AUDIENCE';
 h.state.project.ai_reports[0].report.modules.audience.report.audiences.push(second);
 await h.run("workflowAction('choose-audience',{dataset:{index:'1'}})");
 assert.equal(h.state.page,'tower');assert.equal(h.run('audiencePerson(selectedInsightReport()).index'),1);
 h.state.page='strategy';assert.match(h.run('audienceWorkspace()'),/value="1" selected/);
 h.state.project.ai_reports[0].report.modules.audience.report.audiences[1].name='<img src=x onerror=alert(1)>';
 assert.doesNotMatch(h.run('audienceWorkspace()'),/<img src=x/);
 h.state.project.data_version++;assert.match(h.run('audienceWorkspace()'),/旧数据/);
 const empty=harness(fixture());empty.state.page='strategy';assert.match(empty.run('audienceWorkspace()'),/尚未生成/);
 await empty.run("workflowAction('prepare-audience-flow',{})");assert.equal(empty.calls.length,0);
 assert.equal(empty.state.page,'insights');
 assert.equal(h.calls.length,0);
 console.log('人群主线：四个页面、八层口径、原始证据、过期提示、空态和零模型调用通过');
})().catch(e=>{console.error(e);process.exitCode=1});
