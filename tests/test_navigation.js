// Execute the real index routing and rendering; page bodies are dispatch markers.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const index = fs.readFileSync(path.join(root, 'web/index.html'), 'utf8');
const research = fs.readFileSync(path.join(root, 'web/research.js'), 'utf8');
function line(source, prefix) {
  const matches = source.split('\n').filter(value => value.startsWith(prefix));
  assert.equal(matches.length, 1, `Expected one real source definition: ${prefix}`);
  return matches[0];
}

function harness(hash = '') {
  const elements = new Map(), listeners = {}, calls = [];
  const pages = ['audienceWorkspace', 'overview', 'keywordWorkspace', 'research', 'marketWatch', 'insightWorkspace', 'reportWorkspace', 'guide'];
  const project = id => ({id, name:'饮水机', keyword:'宠物饮水机', data_version:1, updated_at:'2026-09-12',
    runs:[{mode:'collection',kind:'keywords',platforms:['xhs','reddit']}], demo:false});
  const context = vm.createContext({console, URLSearchParams, location:{hash},
    document:{title:'', querySelector(selector) {
      if (!elements.has(selector)) elements.set(selector, {innerHTML:'',textContent:'',href:''});
      return elements.get(selector);
    }},
    window:{scrollTo(){},addEventListener(type, handler){listeners[type] = handler}},
    icon:()=>'', esc:value=>String(value ?? ''), date:value=>value,
    head:title=>`<h1>${title}</h1>`, empty:title=>`<p>${title}</p>`, button:label=>label,
    setTimeout(){}, checkDeviceSetup(){}, toast:message=>{throw Error(message)},
    async api(url){calls.push(url);return url==='/api/projects'?[]:project(url.split('/').at(-1))},
    async resumeCollection(){}, async resumeAI(){},
    ...Object.fromEntries(pages.map(name=>[name,()=>`view:${name}`]))
  });
  const definitions = [line(fs.readFileSync(path.join(root,'web/workflow.js'),'utf8'),'const AUDIENCE_STEPS='),
    ...['const quick=', 'const PLATFORM_NAMES=', 'function syncQuickProject('].map(prefix=>line(research,prefix)),
    ...['const NAV=', 'const ROUTE_LABELS=', 'const primaryPage=', 'function routePage(', 'const state=',
      'async function openProject(', 'function goto(', 'function render(', 'async function init(',
      "window.addEventListener('hashchange'"].map(prefix=>line(index,prefix))
  ].join('\n');
  vm.runInContext(definitions, context, {filename:'real-navigation.js'});
  return {run:code=>vm.runInContext(code, context), elements, listeners, calls, context};
}

(async()=>{
  const h = harness('#posts?project=project-a');
  await h.run('init()');
  assert.equal(h.run('state.page'), 'research', 'old posts bookmark belongs to keyword research');
  assert.equal(h.run('quick.tab'), 'posts', 'opening saved project must not replace the requested posts tab with its last collection kind');
  assert.equal(h.elements.get('#content').innerHTML, 'view:research');
  assert.equal(h.run('state.project.id'), 'project-a');
  assert.equal(h.run('quick.platforms.join(",")'), 'xhs,reddit');

  assert.deepEqual(JSON.parse(h.run('JSON.stringify(NAV.map(([id,,label])=>[id,label]))')),
    [['research','1. 下拉词采集'],['keywords','2. 关键词清洗'],['audience','3. 人群与场景'],['tower','4. 千机塔洞察'],['strategy','5. 人群策略'],['content','6. 内容与验证']]);
  for (const page of ['research','keywords','posts','insights']) assert.equal(h.run(`primaryPage('${page}')`),page);
  assert.equal(h.run("routePage('unknown')"), 'research');
  for (const [page,view,active] of [
    ['research','research','research'], ['keywords','keywordWorkspace','keywords'],
    ...['audience','tower','strategy','content'].map(page=>[page,'audienceWorkspace',page]),
    ['insights','insightWorkspace',null], ['products','marketWatch',null],
    ['report','reportWorkspace',null], ['guide','guide',null], ['overview','overview',null]
  ]) {
    h.run(`goto('${page}')`);
    assert.equal(h.elements.get('#content').innerHTML, 'view:'+view, `${page} must dispatch to its real mapped view`);
    const nav = h.elements.get('#nav').innerHTML;
    assert.equal((nav.match(/data-action="navigate"/g)||[]).length, 6);
    assert.doesNotMatch(nav, /data-page="(?:guide|overview|insights|posts|products|report)"/);
    const highlighted = [...nav.matchAll(/<button class="active"[^>]*data-page="([^"]+)"/g)].map(match=>match[1]);
    assert.deepEqual(highlighted, active?[active]:[], `${page} must highlight its primary section only`);
  }

  h.run("quick.tab='keywords'; goto('posts')");
  assert.equal(h.run('state.page'), 'research');
  assert.equal(h.run('quick.tab'), 'posts');
  assert.equal(h.context.location.hash, 'research?project=project-a');

  h.context.location.hash = '#posts?project=project-b';
  await h.listeners.hashchange();
  assert.equal(h.run('state.project.id'), 'project-b');
  assert.equal(h.run('state.page'), 'research');
  assert.equal(h.run('quick.tab'), 'posts', 'old posts link must survive switching to another project');
  assert.equal(h.elements.get('#content').innerHTML, 'view:research');

  console.log('Navigation: six collection-to-strategy steps, exact highlights, market-watch dispatch and old posts links passed.');
})().catch(error=>{console.error(error);process.exitCode=1});
