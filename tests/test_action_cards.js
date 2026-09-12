// 行动卡只读取真实保存的字段，不把空报告变成市场结论。
const assert=require('node:assert/strict');
const {harness,fixture}=require('./test_workflow');
const {reportFixture}=require('./test_insight_modules');
const p=fixture(),r=reportFixture();r.data_version=p.data_version;p.ai_reports=[r];
const h=harness(p),html=h.run('actionCards()'),a=r.report.modules.summary.report.actions[0];
for(const value of [a.action,a.deliverable,a.verification])assert.ok(html.includes(value));
assert.match(html,/模型建议 · 待验证/);assert.match(html,/data-report="v2-report"/);
assert.match(h.run('reportWorkspace()'),/下一步行动/);
assert.match(h.run('fullReportHtml()'),/下一步行动/);
h.state.project.data_version++;assert.match(h.run('actionCards()'),/旧数据|资料已更新/);
const empty=harness(fixture());assert.match(empty.run('actionCards()'),/尚未形成行动建议/);assert.equal(empty.calls.length,0);
h.state.project.ai_reports[0].report.modules.summary.report.actions[0].action='<img src=x onerror=alert(1)>';
assert.doesNotMatch(h.run('actionCards()'),/<img/);assert.match(h.run('actionCards()'),/&lt;img/);
assert.match(harness(null).run('research()'),/research-layout/);
console.log('行动卡：已有建议、精确证据、过期提示、空态、转义和首屏结构通过。');
