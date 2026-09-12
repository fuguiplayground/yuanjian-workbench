const assert=require('node:assert/strict');
const {harness,fixture}=require('./test_workflow');
const {reportFixture}=require('./test_insight_modules');
(async()=>{
 const p=fixture();const r=reportFixture();r.report.modules.clean.report.items=[{id:'keywords:k1',valid:true,w5h1:'HOW',intent:'购买意图',stage:'A5',emotion:'中性',theme:'清洗',reason:'售后使用需求',content_suggestion:'测试建议'},{id:'keywords:k2',valid:false,w5h1:'WHAT',reason:'非本品类',theme:'不相关'}];p.ai_reports=[r];const h=harness(p);
 const page=h.run('keywordWorkspace()');
 for(const s of ['去重','无效词','5W1H','搜索意图','A1–A5','情绪','主题聚合','清洗后关键词库','排除词与原因','主题与人群入口'])assert.ok(page.includes(s),s);
 assert.match(page,/SAVED_KEYWORD/);assert.match(page,/非本品类/);assert.match(page,/data-action="generate-clean-library"/);
 assert.match(page,/售后故障、清洗、漏水和维修词保留为需求证据/);
 assert.doesNotMatch(page,/售后使用问题移出营销词库/);
 assert.equal(h.calls.length,0);
 h.state.project.data_version++;assert.match(h.run('keywordWorkspace()'),/旧数据|资料已更新/);
 const fresh=harness(fixture());assert.match(fresh.run('keywordWorkspace()'),/尚未生成清洗结果/);
 await fresh.run("workflowAction('generate-clean-library',{})");assert.equal(fresh.state.page,'keywords');assert.deepEqual(fresh.calls.find(x=>x.url.endsWith('/ai')).body.modules,['clean']);
 console.log('清洗入口：七步方法、四区结果、原词证据、排除原因、过期提示及独立清洗请求通过');
})().catch(e=>{console.error(e);process.exitCode=1});
