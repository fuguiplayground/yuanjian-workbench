const assert=require('node:assert/strict');
const {harness,fixture}=require('./test_workflow');
(async()=>{
 const h=harness(fixture());
 h.state.project.decision_workspace={brief:{goal:'找需求'},selected_id:'o1',cases:[{id:'o1',title:'机会甲',source_version:2,scenario:'使用场景',task:'用户任务',strategy:{audience:'人群甲',promise:'承诺甲'},content:{title:'选题甲'},feedback:{}}]};
 for(const page of ['brief','materials','opportunities','strategy','content','feedback']){h.state.page=page;const html=h.run('businessWorkspace()');assert.doesNotMatch(html,/undefined|\[object Object\]/);}
 h.state.page='content';assert.match(h.run('businessWorkspace()'),/人群甲/);assert.match(h.run('businessWorkspace()'),/承诺甲/);
 h.state.page='feedback';assert.match(h.run('businessWorkspace()'),/选题甲/);
 h.state.project.decision_workspace.cases[0].feedback.context='old';assert.match(h.run('businessWorkspace()'),/不代表新版已验证/);
 h.state.project.data_version++;assert.match(h.run('businessWorkspace()'),/旧版本/);
 h.state.project.decision_workspace.selected_id='';assert.match(h.run('businessWorkspace()'),/先选择一张需求机会卡/);
 h.state.page='brief';h.state.project.decision_workspace.brief.goal='<script>bad</script>';assert.doesNotMatch(h.run('businessWorkspace()'),/<script>/);
 assert.equal(h.calls.length,0);
 h.run(`api=async (url,body)=>{if(!url.endsWith('/decision-workspace'))throw Error('unexpected'); return {...state.project,revision:state.project.revision+1,decision_workspace:body.workspace}};crypto={randomUUID:()=> 'test-uuid'};`);
 h.state.page='opportunities';
 await h.run(`businessAction('save-business',{dataset:{kind:'opportunity'},closest(){return {elements:{namedItem(key){return {value:key==='title'?'机会乙':''}}}}}})`);
 assert.equal(h.state.project.decision_workspace.cases.length,2);assert.equal(h.state.project.decision_workspace.selected_id,'opp-test-uuid');
 await h.run(`businessAction('select-opportunity',{dataset:{id:'o1'}})`);assert.equal(h.state.page,'strategy');assert.equal(h.state.project.decision_workspace.selected_id,'o1');
 console.log('业务页面：六页、机会编号关联、人群/内容承接、旧反馈失效提醒、转义、空态与保存选择通过');
})().catch(e=>{console.error(e);process.exitCode=1});
