// Real module UI and both exporters share a document tree; no generated report mocks.
const assert=require('node:assert/strict');
const {harness,fixture}=require('./test_workflow');
const clone=x=>JSON.parse(JSON.stringify(x));
const keys=['clean','audience','intent','comments','notes','topics','summary'];
let serial=0;
const marker=name=>'FIELD_'+name+'_'+(++serial);
const p=name=>({text:marker(name),basis:'inference',evidence_ids:['keywords:k1'],validation:marker('validation')});
const base=()=>({title:marker('title'),summary:marker('summary'),quality:'limited',limitations:[marker('limitation')]});
const reports={
 clean:{...base(),items:[{id:'keywords:k1',valid:true,reason:marker('clean_reason'),w5h1:'HOW',intent:marker('intent'),stage:'A4',emotion:'中性',theme:'清洗',content_suggestion:marker('suggestion')}],
  theme_recommendations:[{theme:'清洗',direction:p('direction'),layer:'A4'}],high_value_terms:[{text:'SAVED_KEYWORD',evidence_id:'keywords:k1',why:p('valuable')}],brand_opportunities:[p('brand')],findings:[p('finding')],next_steps:[p('next')],
  stats:{total:1,valid:1,invalid:0,topic_count:1,longtail_count:1,how_pct:100,w5h1:[{name:'HOW',count:1}],journey:[{name:'A4',count:1}],emotion:[{name:'中性',count:1}]}},
 audience:{...base(),audience_map:p('map'),next_steps:[p('next')],audiences:[{
  name:marker('person'),one_line:marker('one_line'),layers:Object.fromEntries(['natural','social','consumption','scene','lifestyle','emotion','deep_emotion','values'].map(k=>[k,p(k)])),
  day_in_life:[{moment:marker('moment'),scene:marker('scene'),task:marker('task'),friction:marker('friction'),basis:'inference',evidence_ids:['keywords:k1'],validation:marker('day_validation')}],
  needs:Object.fromEntries(['explicit','implicit','deep'].map(k=>[k,p(k)])),purchase_triggers:[p('trigger')],decision_factors:[p('decision')],barriers:[p('barrier')],alternatives:[p('alternative')],
  positioning:Object.fromEntries(['target','promise','proof','avoid'].map(k=>[k,p(k)])),search_terms:[{text:'SAVED_KEYWORD',evidence_id:'keywords:k1'}],
  scores:Object.fromEntries(['pain','payment','fit','content'].map(k=>[k,{score:k==='payment'?null:3,reason:p(k)}])),priority:'高',priority_reason:p('priority'),validation_questions:[marker('question')],evidence_ids:['keywords:k1']}]},
 intent:{...base(),items:[{id:'keywords:k1',stage:'A4',emotion:marker('item_emotion')}],stage_insights:[{stage:'A4',interpretation:p('stage'),next_content:p('next_content')}],
  bottleneck:p('bottleneck'),demands:[{need:marker('need'),urgency:'待验证',diagnosis:p('diagnosis'),action:p('action')}],emotions:[{emotion:marker('emotion'),interpretation:p('interpretation')}],next_steps:[p('next')],journey:[{stage:'A4',count:1,evidence_ids:['keywords:k1']}]},
 comments:{...base(),pains:[{point:p('pain'),quotes:[{quote:'SAVED_REVIEW',evidence_id:'reviews:r1'}]}],questions:[{point:p('question'),quotes:[]}],loves:[{point:p('love'),quotes:[]}],golden_quotes:[{quote:'SAVED_REVIEW',evidence_id:'reviews:r1'}],topics:[p('comment_topic')],demand_priorities:[p('demand_priority')],next_steps:[p('next')]},
 notes:{...base(),themes:[{theme:marker('theme'),explanation:p('explanation')}],angles:[{angle:marker('angle'),why:p('why')}],performance_note:marker('performance'),
  patterns:['opening','body','closing'].map(part=>({part,finding:p(part)})),topics:[{title:marker('note_title'),angle:marker('note_angle'),why:p('note_why')}],gaps:[p('gap')],next_steps:[p('next')]},
 topics:{...base(),topics:[{title:marker('topic_title'),target:marker('topic_target'),stage:'A4',angle:marker('topic_angle'),format:marker('format'),opening:marker('opening'),outline:[marker('outline1'),marker('outline2')],call_to_action:marker('cta'),why:p('topic_why'),words:['SAVED_KEYWORD'],evidence_ids:['keywords:k1']}],priority_reason:p('topics_priority'),next_steps:[p('next')]},
 summary:{...base(),core_opportunity:p('core'),narrowest_entry:p('narrowest'),priority_audiences:[{name:marker('priority_person'),why:p('priority_why')}],positioning:p('summary_position'),actions:[{action:marker('action'),why:p('why'),deliverable:marker('deliverable'),verification:marker('verification')}],cautions:[p('caution')],self_check:{no_anxiety:true,narrowest:true,has_contrast:false,real_demand:false,note:marker('self_check')}}
};
function reportFixture(id='v2-report'){
 const snapshot=[{id:'keywords:k1',kind:'keywords',row_id:'k1',text:'SAVED_KEYWORD',platform:'xhs'},
  {id:'posts:p1',kind:'posts',row_id:'p1',text:'SAVED_POST_TITLE\nSAVED_POST_BODY',platform:'reddit',metrics:{likes:8,comment_count:2}},
  {id:'reviews:r1',kind:'reviews',row_id:'r1',text:'SAVED_REVIEW',platform:'reddit'}];
 const scope={processed:3,total:5,truncated:2,text_truncated:1,evidence_ids:snapshot.map(x=>x.id),counts:{keywords:{processed:1,total:1},posts:{processed:1,total:2},reviews:{processed:1,total:2}}};
 return {id,kind:'insights',schema_version:2,status:'success',data_version:2,requested_modules:['notes'],created_at:'2026-09-12',scope,
  report:{title:'模块报告',summary:'逐项查看',modules:Object.fromEntries(keys.map(key=>[key,{key,status:'success',data_version:2,finished_at:'2026-09-11',scope:clone(scope),evidence_snapshot:clone(snapshot),report:clone(reports[key])}]))}};
}
function allMarkers(value){if(typeof value==='string')return value.startsWith('FIELD_')?[value]:[];if(Array.isArray(value))return value.flatMap(allMarkers);if(value&&typeof value==='object')return Object.values(value).flatMap(allMarkers);return []}
async function main(){
 const reopened=fixture(),ongoing=reportFixture('reopened');ongoing.status='running';ongoing.requested_modules=['audience','comments','summary'];reopened.ai_reports=[ongoing];
 assert.deepEqual(clone(harness(reopened).run('selectedInsightModules()')),['audience','comments','summary'],'reload restores the actual module selection instead of changing comments to intent');
 const choice=harness(),page=choice.run('insightWorkspace()');
 assert.equal((page.match(/name="insight-module"/g)||[]).length,8);
 assert.match(page,/这次重点看什么/);assert.match(page,/每块独立取样/);
 assert.deepEqual(clone(choice.run('selectedInsightModules()')),['audience','intent','summary']);
 await choice.run("workflowAction('ai-insights',{})");
 assert.equal(choice.state.page,'insights');assert.equal(choice.calls.length,0,'entry opens module selection without starting model calls');
 for(const key of ['audience','intent','summary'])choice.fire('change',{name:'insight-module',value:key,checked:false});
 await assert.rejects(choice.run("workflowAction('generate-insight-modules',{})"),/至少选择/);
 choice.fire('change',{name:'insight-module',value:'notes',checked:true});choice.fire('change',{name:'insight-module',value:'comments',checked:true});
 await choice.run("workflowAction('generate-insight-modules',{})");
 assert.deepEqual(choice.posts('/ai')[0].body,{revision:4,kind:'insights',target:'',modules:['comments','notes']},'one explicit request sends only selected modules in execution order');
 const postsOnly=fixture();postsOnly.keywords=[];postsOnly.reviews=[];const available=harness(postsOnly),availability=available.run('insightWorkspace()');
 for(const key of ['clean','intent','comments'])assert.match(availability,new RegExp('value="'+key+'"[^>]*disabled'));
 assert.doesNotMatch(availability, /value="notes"[^>]*disabled/);
 available.fire('change',{name:'insight-module',value:'comments',checked:true});assert.ok(!available.run('selectedInsightModules()').includes('comments'));
 available.fire('change',{name:'insight-module',value:'notes',checked:true});
 available.state.project={...fixture(),id:'project-b'};assert.deepEqual(clone(available.run('selectedInsightModules()')),['audience','intent','summary'],'module choices are per project');
 available.state.project=postsOnly;assert.ok(available.run('selectedInsightModules()').includes('notes'));

 const project=fixture(),saved=reportFixture();project.ai_reports=[saved];project.keywords[0].text='CURRENT_CHANGED_WORD';project.posts[0].body='CURRENT_CHANGED_BODY';project.reviews=[];
 const view=harness(project),html=view.run("insightReportBody(latestAI('insights'))"),md=view.run("reportMarkdown(latestAI('insights'))");
 assert.deepEqual(clone(view.run("insightModuleKeys(latestAI('insights'))")),keys,'copied successful modules are shown even when requested_modules contains one rerun');
 for(const token of allMarkers(reports)){assert.ok(html.includes(token),'UI missed '+token);assert.ok(md.includes(token),'Markdown missed '+token)}
 assert.match(html,/付费证据 · 待验证/);assert.doesNotMatch(html,/付费证据 · 0/);
 assert.match(html,/模型推断/);assert.match(html,/如何验证/);assert.match(md,/本项资料有限/);
 assert.match(html,/data-module="notes"/);assert.match(md,/SAVED_POST_BODY/);assert.match(md,/文本截断 1 条/);assert.match(md,/posts:|posts =|likes = 8/);
 assert.doesNotMatch(html,/CURRENT_CHANGED_WORD|CURRENT_CHANGED_BODY/);assert.doesNotMatch(md,/CURRENT_CHANGED_WORD|CURRENT_CHANGED_BODY/);
 await view.run("workflowAction('export-ai-html',{dataset:{kind:'insights',report:'v2-report'}})");
 const exported=view.downloads.at(-1).body;
 for(const token of allMarkers(reports))assert.ok(exported.includes(token),'HTML missed '+token);
 assert.doesNotMatch(exported,/<button\b|data-action=|<script\b/);assert.match(exported,/<a href="#insight-v2-report-notes"/);
 for(const key of keys)assert.equal((exported.match(new RegExp('id="insight-v2-report-'+key+'"','g'))||[]).length,1);
 const full=view.run('fullReportHtml()').split('<h2>当前项目资料</h2>');assert.match(full[0],/SAVED_POST_BODY/);assert.doesNotMatch(full[0],/CURRENT_CHANGED_BODY/);assert.match(full[1],/CURRENT_CHANGED_BODY/);
 assert.match(view.run('reportWorkspace()'),new RegExp(reports.summary.core_opportunity.text));
 assert.match(view.run('keywordWorkspace()'),/查看人群与场景/);

 view.state.project.ai_reports[0].report.modules.notes.evidence_snapshot.find(x=>x.id==='posts:p1').text='NOTES_SPECIFIC_SNAPSHOT';
 await view.run(`workflowAction('ai-evidence',{dataset:{report:'v2-report',module:'notes',evidence:'["posts:p1"]'}})`);
 assert.match(view.modal().html,/NOTES_SPECIFIC_SNAPSHOT/);assert.doesNotMatch(view.modal().html,/SAVED_POST_BODY|CURRENT_CHANGED_BODY/);
 view.state.project.ai_reports[0].report.modules.notes.scope.evidence_ids=['posts:p1'];
 await assert.rejects(view.run(`workflowAction('ai-evidence',{dataset:{report:'v2-report',module:'notes',evidence:'["keywords:k1"]'}})`),/不属于/);
 const retries=harness(project);await retries.run("workflowAction('rerun-insight-module',{dataset:{report:'v2-report',module:'notes'}})");
 assert.deepEqual(retries.posts('/ai')[0].body,{revision:4,kind:'insights',target:'',modules:['notes'],base_report_id:'v2-report'});
 const stale=harness(project);stale.state.project.data_version=3;
 await assert.rejects(stale.run("workflowAction('rerun-insight-module',{dataset:{report:'v2-report',module:'notes'}})"),/资料已更新/);
 assert.equal(stale.calls.length,0,'stale reports cannot be used as a rerun base');

 const partial=fixture(),partialRecord=reportFixture('partial');partialRecord.status='running';partialRecord.report.modules.comments={status:'failed',message:'可重试的失败',data_version:2};partialRecord.report.modules.notes={status:'running',data_version:2};partialRecord.report.modules.topics={status:'pending',data_version:2};partial.ai_reports=[partialRecord];
 const partialView=harness(partial),partialHtml=partialView.run("insightReportBody(latestAI('insights'))");
 assert.match(partialHtml,/可重试的失败/);assert.match(partialHtml,/正在分析/);assert.match(partialHtml,/前一项完成后开始/);assert.match(partialHtml,new RegExp(reports.audience.audiences[0].one_line));
 const partialMD=partialView.run("reportMarkdown(latestAI('insights'))");assert.match(partialMD,/内容规律[\s\S]*状态：正在生成/);assert.match(partialMD,new RegExp(reports.audience.audiences[0].one_line));
 partialView.state.project.ai_reports[0].report.modules.summary={status:'pending',data_version:2};assert.doesNotThrow(()=>partialView.run('reportWorkspace()'));
 const newer=reportFixture('newer');newer.report.modules.summary.report.core_opportunity.text='NEW_REPORT_ONLY';view.state.project.ai_reports.push(newer);
 view.fire('change',{id:'insight-report-select',value:'v2-report'});assert.match(view.run('insightWorkspace()'),/data-report="v2-report"/);
 await view.run("workflowAction('export-ai-md',{dataset:{kind:'insights',report:'v2-report'}})");assert.doesNotMatch(view.downloads.at(-1).body,/NEW_REPORT_ONLY/,'viewing an old version exports that version');
 let scrolled=false;view.fields['#insight-v2-report-notes']={scrollIntoView(){scrolled=true}};const hash=view.context.location.hash;
 await view.run("workflowAction('insight-section',{dataset:{section:'insight-v2-report-notes'}})");assert.ok(scrolled);assert.equal(view.context.location.hash,hash,'report chapter navigation does not overwrite the app route');

 // A project switch during the second await must never replace the new project.
 const race=harness();let release;race.run("workflow.aiJob={id:'job-a',project_id:'project-a',status:'running'}");
 race.context.api=async url=>url.includes('/ai/jobs/')?{id:'job-a',project_id:'project-a',status:'success'}:await new Promise(resolve=>{release=resolve});
 const polling=race.run('pollAI()');await new Promise(resolve=>setImmediate(resolve));race.state.project={...fixture(),id:'project-b'};release(fixture());await polling;assert.equal(race.state.project.id,'project-b');
 console.log('Insight modules: selection, incremental chapters, complete schema exports, exact snapshots, rerun scope, history and project-switch race passed.');
}
if(require.main===module)main().catch(error=>{console.error(error);process.exitCode=1});
module.exports={reportFixture};
