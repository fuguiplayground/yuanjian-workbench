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
  const pages = ['inputManifestWorkspace','evidenceLedgerWorkspace','audienceLensWorkspace','skillWorkspace','businessWorkspace','audienceWorkspace', 'overview', 'keywordWorkspace', 'research', 'marketWatch', 'insightWorkspace', 'reportWorkspace', 'guide'];
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

  assert.equal(h.run('NAV.length'),13);
  assert.equal(h.run('new Set(NAV.map(x=>x[3])).size'),4);
  assert.equal(h.run("routePage('unknown')"),'keywords');
  for(const [page,view,active] of [
    ['inputs','inputManifestWorkspace','inputs'],['ledger','evidenceLedgerWorkspace','ledger'],['research','research','research'],['keywords','keywordWorkspace','keywords'],['evidence','research','evidence'],
    ['nine','audienceLensWorkspace','nine'],['audience','audienceWorkspace','audience'],['tower','audienceLensWorkspace','tower'],
    ['strategy','audienceWorkspace','strategy'],['content','audienceLensWorkspace','content'],['skills','skillWorkspace','skills'],
    ['products','marketWatch','products'],['report','reportWorkspace','report'],['insights','insightWorkspace','report'],
    ['brief','keywordWorkspace','keywords'],['feedback','audienceWorkspace','strategy'],['guide','guide',null]
  ]){
    h.run(`goto('${page}')`);
    assert.equal(h.elements.get('#content').innerHTML,'view:'+view);
    const nav=h.elements.get('#nav').innerHTML;
    assert.equal((nav.match(/nav-group-title/g)||[]).length,4);
    assert.equal((nav.match(/data-action="navigate"/g)||[]).length,13);
    const highlighted=[...nav.matchAll(/<button class="active"[^>]*data-page="([^"]+)"/g)].map(x=>x[1]);
    assert.deepEqual(highlighted,active?[active]:[]);
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
