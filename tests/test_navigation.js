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
  const pages = ['overview', 'keywordWorkspace', 'research', 'marketWatch', 'insightWorkspace', 'reportWorkspace', 'guide'];
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
  const definitions = [
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
    [['research','关键词洞察'],['products','电商盯盘'],['report','报告与选品']]);
  for (const page of ['research','keywords','posts','insights']) assert.equal(h.run(`primaryPage('${page}')`),'research');
  assert.equal(h.run("routePage('unknown')"), 'research');
  for (const [page,view,active] of [
    ['research','research','research'], ['keywords','keywordWorkspace','research'],
    ['insights','insightWorkspace','research'], ['products','marketWatch','products'],
    ['report','reportWorkspace','report'], ['guide','guide',null], ['overview','overview',null]
  ]) {
    h.run(`goto('${page}')`);
    assert.equal(h.elements.get('#content').innerHTML, 'view:'+view, `${page} must dispatch to its real mapped view`);
    const nav = h.elements.get('#nav').innerHTML;
    assert.equal((nav.match(/data-action="navigate"/g)||[]).length, 3);
    assert.doesNotMatch(nav, /data-page="(?:guide|overview|keywords|insights|posts)"/);
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

  console.log('Navigation: three primary entries, nested highlights, market-watch dispatch and old posts links passed.');
})().catch(error=>{console.error(error);process.exitCode=1});
