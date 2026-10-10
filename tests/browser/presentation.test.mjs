import assert from 'node:assert/strict';
import {before, after, test} from 'node:test';
import {createServer} from 'node:http';
import {readFile, mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium, webkit} from 'playwright';

// An owned loopback server, headless sandbox and fresh temporary contexts only.
// Never connect to an existing browser or fall back to a visible window.
const root = process.env.SOLVER_SITE_DIR ? path.resolve(process.env.SOLVER_SITE_DIR) :
  fileURLToPath(new URL('../../_site/', import.meta.url));
const evidence = JSON.parse(await readFile(new URL('../../docs/visual-example-data.json', import.meta.url)));
const originalSVG = await readFile(new URL('../../docs/blackjack-composition-example.svg', import.meta.url));
const mime = {'.html':'text/html', '.css':'text/css', '.js':'text/javascript',
  '.mjs':'text/javascript', '.json':'application/json', '.svg':'image/svg+xml', '.png':'image/png'};
let browser, server, base;
before(async () => {
  const published = process.env.SOLVER_BROWSER_BASE_URL;
  if (published && published !== 'https://t92t1914.github.io/exact-blackjack-solver/') {
    throw Error('Unsupported published project URL');
  }
  if (published) base = published.slice(0,-1);
  else {
    server = createServer(async (request, response) => {
    const pathname = new URL(request.url, 'http://localhost').pathname;
    if (pathname === '/favicon.ico') { response.writeHead(204).end(); return; }
    const name = pathname === '/' ? 'index.html' : pathname.slice(1);
    if (!/^[a-z0-9.-]+$/i.test(name)) { response.writeHead(404).end(); return; }
    try {
      const bytes = await readFile(path.join(root, name));
      response.writeHead(200, {'Content-Type':mime[path.extname(name)] ?? 'text/plain'}).end(bytes);
    } catch (_) { response.writeHead(404).end(); }
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    base = `http://127.0.0.1:${server.address().port}`;
  }
  const channel = process.env.SOLVER_BROWSER_CHANNEL;
  if (channel && !['chrome','chromium'].includes(channel)) throw Error('Unsupported channel');
  const engine = process.env.SOLVER_BROWSER_ENGINE ?? 'chromium';
  if (!['chromium','webkit'].includes(engine)) throw Error('Unsupported engine');
  browser = await (engine === 'webkit' ? webkit.launch({headless:true}) :
    chromium.launch({headless:true, chromiumSandbox:true, args:['--mute-audio','--disable-gpu'],
      ...(channel ? {channel} : {})}));
  console.log(`Isolated headless ${engine} ${browser.version()}; fresh contexts` +
    (engine === 'chromium' ? '; sandbox requested' : ''));
});
after(async () => {
  if (browser) await browser.close();
  if (server) await new Promise(resolve => server.close(resolve));
});
async function fixture(t, options = {}, blockedStorage = false) {
  const context = await browser.newContext({viewport:{width:1280,height:900}, ...options});
  const failures = [], external = [];
  await context.route('**/*', route => {
    const requested = new URL(route.request().url()),allowed = new URL(base+'/');
    if (requested.origin !== allowed.origin || !requested.pathname.startsWith(allowed.pathname)) {
      external.push(route.request().url()); return route.abort();
    }
    return route.continue();
  });
  if (blockedStorage) await context.addInitScript(() => {
    Object.defineProperty(window, 'localStorage', {get() { throw new DOMException('Blocked','SecurityError'); }});
  });
  const page = await context.newPage();
  page.on('pageerror', error => failures.push(error.message));
  page.on('console', message => { if (message.type() === 'error') failures.push(message.text()); });
  page.on('response', response => { if (response.status() >= 400) failures.push(`${response.status()} ${response.url()}`); });
  t.after(async () => {
    await context.close();
    assert.deepEqual(failures, []);
    assert.deepEqual(external, [], 'No external font, analytics or other page requests');
  });
  return page;
}
const background = page => page.locator('body').evaluate(e => getComputedStyle(e).backgroundColor);
async function ready(page) {
  await page.goto(base+'/');
  await page.locator('#interactive:visible').waitFor();
}
async function capture(page, name, fullPage = true) {
  if (!process.env.SOLVER_SCREENSHOT_DIR) return;
  await mkdir(process.env.SOLVER_SCREENSHOT_DIR, {recursive:true});
  await page.screenshot({path:path.join(process.env.SOLVER_SCREENSHOT_DIR, name+'.png'), fullPage});
}

const recordFixture=await readFile(new URL('../fixtures/saved-decision-v1-7a38141.json',import.meta.url));
const suppliedRecord=(name,buffer)=>({name,mimeType:'application/json',buffer});
const alteredRecord=update=>{const saved=JSON.parse(recordFixture);update(saved);return Buffer.from(JSON.stringify(saved));};
const effectiveControls=saved=>saved.schema.version===1 ? {can_double:true,can_split:true} : saved.state.action_controls;
const controlledRecord=(double,pair)=>alteredRecord(saved=>{
  if (!double || !pair) {
    saved.schema.version=2;saved.state.action_controls={can_double:double,can_split:pair};
  }
  if (!double) delete saved.decision.evs.D;
  if (!pair) delete saved.decision.evs.P;
});
const controlCases=[['TT',true,true],['FT',false,true],['TF',true,false],['FF',false,false]];
async function actualControlRecords() {
  const paths=controlCases.map(([label])=>process.env[`SOLVER_RECORD_${label}`]);
  assert.ok(paths.every(Boolean) || paths.every(value=>!value),'Provide all four installed control records or none');
  return Promise.all(controlCases.map(async ([label,double,pair],i)=>({label,double,pair,
    buffer:paths[i] ? await readFile(paths[i]) : controlledRecord(double,pair)})));
}
async function acceptedRecord(page,label,buffer,name=`record-${label}.json`) {
  await page.locator(`#record-file-${label}`).setInputFiles(suppliedRecord(name,buffer));
  await page.locator(`#record-result-${label}:visible`).waitFor();
  assert.match(await page.locator(`#record-status-${label}`).textContent(),/not been recomputed/);
}
async function assertPermittedActions(page,label,permitted,saved) {
  const result=page.locator(`#record-result-${label}`),name=`Record ${label.toUpperCase()}`;
  const table=result.getByRole('region',{name:`${name} derived permitted actions beside supplied EV presence`,exact:true});
  assert.equal(await table.locator('tbody tr').count(),4);
  const names=saved.schema.version===4 ? {S:'STAND',H:'HIT',D:'DOUBLE',R:'SURRENDER'} :
    {H:'HIT',S:'STAND',D:'DOUBLE',P:'SPLIT'};
  for (const action of Object.keys(names)) {
    const row=table.locator('tbody tr').filter({has:page.getByRole('rowheader',{name:`${action} (${names[action]})`,exact:true})});
    assert.deepEqual(await row.locator('td').allTextContents(),[String(permitted.includes(action)),
      Object.hasOwn(saved.decision.evs,action) ? String(saved.decision.evs[action]) : 'absent (no saved value)']);
  }
  const omitted=permitted.filter(action=>!Object.hasOwn(saved.decision.evs,action));
  const unavailable=Object.keys(saved.decision.evs).filter(action=>!permitted.includes(action));
  const note=result.locator('[data-action-set-status]');
  assert.equal(await note.getAttribute('data-action-set-status'),omitted.length || unavailable.length ? 'differs' : 'matches');
  if (omitted.length) assert.match(await note.textContent(),new RegExp('Permitted actions omitted from saved EVs: '+omitted.join(', ')));
  if (unavailable.length) assert.match(await note.textContent(),new RegExp('Saved EVs include unavailable actions: '+unavailable.join(', ')));
  if (!permitted.includes(saved.decision.action)) assert.match(await note.textContent(),/Recorded recommendation .* is unavailable/);
  assert.match(await result.textContent(),/does not establish which buttons an external table offers/);
}
async function assertCompleteRecord(page,label,buffer,permitted=Object.keys(JSON.parse(buffer).decision.evs)) {
  const saved=JSON.parse(buffer),result=page.locator(`#record-result-${label}`);
  const controls=effectiveControls(saved);
  const expected=[...Object.entries(saved.state).filter(([key])=>!['shoe','action_controls'].includes(key)).map(([key,value])=>[`state.${key}`,value]),
    ['state.action_controls.can_double',controls.can_double],['state.action_controls.can_split',controls.can_split],
    ['effective_action_controls.can_surrender',saved.schema.version===4 ? controls.can_surrender : false],
    ['state.action_controls.can_surrender',saved.state.action_controls?.can_surrender],
    ['state.shoe.rank_order',saved.state.shoe.rank_order],
    ...saved.state.shoe.rank_order.map((rank,i)=>[`state.shoe.counts.${rank}`,saved.state.shoe.counts[i]]),
    ...Object.entries(saved.state.shoe).filter(([key])=>!['counts','rank_order'].includes(key)).map(([key,value])=>[`state.shoe.${key}`,value]),
    ...Object.entries(saved.rules).map(([key,value])=>[`rules.${key}`,value]),
    ...Object.entries(saved.model).map(([key,value])=>[`model.${key}`,value]),
    ...Object.entries(saved.schema).map(([key,value])=>[`schema.${key}`,value]),
    ...Object.entries(saved.package).map(([key,value])=>[`package.${key}`,value]),
    ...Object.entries(saved.decision).filter(([key])=>key!=='evs').map(([key,value])=>[`decision.${key}`,value])];
  const show=value=>value===undefined ? 'absent (not declared by this model)' :
    Array.isArray(value) ? '['+value.join(', ')+']' : String(value);
  for (const [key,value] of expected) {
    const row=result.locator('tbody tr').filter({has:page.getByRole('rowheader',{name:key,exact:true})});
    assert.equal(await row.count(),1,key);
    assert.equal(await row.locator('td').textContent(),show(value),key);
  }
  assert.equal(await result.locator('tbody tr').count(),expected.length+Object.keys(saved.decision.evs).length+4);
  const values=result.getByRole('region',{name:`Record ${label.toUpperCase()} supplied action values in original wager units`,exact:true});
  for (const [action,value] of Object.entries(saved.decision.evs)) {
    const row=values.locator('tbody tr').filter({has:page.getByRole('rowheader',{name:new RegExp('^'+action+' \\(')})});
    assert.equal(await row.locator('td').textContent(),String(value));
  }
  await assertPermittedActions(page,label,permitted,saved);
  assert.match(await result.textContent(),saved.schema.version===1 ? /implicit current action defaults/ :
    saved.schema.version===2 ? /stores the declared current action controls/ :
    saved.schema.version===3 ? /bounded common-shoe model/ : /bounded post-peek late surrender/);
}

test('local file consumer shows complete records and compares inputs before answers',async t=>{
  const page=await fixture(t,{viewport:{width:390,height:844}});
  await ready(page);
  assert.equal(Boolean(process.env.SOLVER_RECORD_A),Boolean(process.env.SOLVER_RECORD_B),'Provide both installed record files or neither');
  const first=process.env.SOLVER_RECORD_A ? await readFile(process.env.SOLVER_RECORD_A) : recordFixture;
  const second=process.env.SOLVER_RECORD_B ? await readFile(process.env.SOLVER_RECORD_B) : alteredRecord(r=>{r.state.cards.reverse();r.rules.s17=false;r.decision.evs.H=-0.5;});
  console.log('Local file consumer inputs:',JSON.stringify({source:process.env.SOLVER_RECORD_A ? 'provided installed outputs' : 'retained and constructed test records',
    sha256:[first,second].map(buffer=>createHash('sha256').update(buffer).digest('hex'))}));
  await acceptedRecord(page,'a',first);
  await assertCompleteRecord(page,'a',first);
  assert.equal(await page.locator('#record-comparison').isVisible(),false);
  await acceptedRecord(page,'b',second);
  await assertCompleteRecord(page,'b',second);
  const comparison=page.locator('#record-comparison');
  assert.equal(await comparison.isVisible(),true);
  assert.deepEqual(await comparison.locator('h3').allTextContents(),[
    '1. Changed modeled inputs','2. Changed record labels','3. Permitted actions from modeled inputs','4. Recorded answer comparison']);
  const eligibility=comparison.getByRole('region',{name:'Derived action eligibility for each modeled input',exact:true});
  for (const [action,name] of Object.entries({H:'HIT',S:'STAND',D:'DOUBLE',P:'SPLIT'})) {
    const row=eligibility.locator('tbody tr').filter({has:page.getByRole('rowheader',{name:`${action} (${name})`,exact:true})});
    assert.deepEqual(await row.locator('td').allTextContents(),[String(Object.hasOwn(JSON.parse(first).decision.evs,action)),String(Object.hasOwn(JSON.parse(second).decision.evs,action))]);
  }
  assert.match(await comparison.textContent(),/does not identify a single cause/);
  for (const label of ['a','b']) {
    await page.locator(`#record-file-${label}`).focus();
    assert.equal(await page.locator(`#record-file-${label}`).evaluate(e=>document.activeElement===e),true);
    assert.equal(await page.locator(`#record-file-${label}`).evaluate(e=>getComputedStyle(e).outlineStyle),'solid');
    await page.keyboard.press('Tab');
    assert.equal(await page.locator(`#record-clear-${label}`).evaluate(e=>document.activeElement===e),true);
  }
  await page.locator('#record-clear-b').click();
  assert.equal(await comparison.isVisible(),false);
  assert.equal(await page.locator('#record-result-b').isVisible(),false);
  assert.equal(await page.locator('#record-result-a').isVisible(),true);
  await acceptedRecord(page,'b',first);
  assert.match(await comparison.textContent(),/All modeled inputs agree/);
  await page.locator('#record-clear-all').click();
  for (const label of ['a','b']) {
    assert.equal(await page.locator(`#record-result-${label}`).isVisible(),false);
    assert.equal(await page.locator(`#record-file-${label}`).inputValue(),'');
    assert.equal(await page.locator(`#record-name-${label}`).textContent(),'No local file retained.');
  }
});

test('record replacement errors remove the old answer and allow recovery',async t=>{
  const page=await fixture(t);await ready(page);
  await acceptedRecord(page,'a',recordFixture);
  for (const [name,buffer,message] of [
    ['malformed.json',Buffer.from('{'),/invalid JSON/],
    ['duplicate.json',Buffer.from('{"schema":{},"\\u0073chema":{}}'),/duplicate JSON key/],
    ['future.json',alteredRecord(r=>{r.schema.version=4;}),/unsupported_record/],
    ['missing-controls.json',alteredRecord(r=>{r.schema.version=2;}),/action_controls/],
    ['float-count.json',Buffer.from(recordFixture.toString().replace('"counts": [\n        0','"counts": [\n        0.0')),/integer/],
    ['invalid-utf8.json',Buffer.from([255]),/valid UTF-8/],
    ['oversized.json',Buffer.alloc(65537,32),/65536 UTF-8 bytes/]
  ]) {
    await page.locator('#record-file-a').setInputFiles(suppliedRecord(name,buffer));
    await page.waitForFunction(()=>document.querySelector('#record-status-a').classList.contains('error'));
    assert.match(await page.locator('#record-status-a').textContent(),message);
    assert.equal(await page.locator('#record-result-a').isVisible(),false);
    assert.equal(await page.locator('#record-comparison').isVisible(),false);
    await acceptedRecord(page,'a',recordFixture);
  }
});

test('common records expose model coverage and incompatibility before answers',async t=>{
  const page=await fixture(t,{viewport:{width:390,height:844}});await ready(page);
  const constructed=JSON.parse(recordFixture);
  constructed.schema.version=3;
  Object.assign(constructed.state,{cards:['T','T'],dealer_up:'7',total:20,soft:false,
    action_controls:{can_double:true,can_split:true}});
  constructed.state.shoe.counts=[1,...Array(8).fill(0),5];constructed.rules.max_hands=2;
  Object.assign(constructed.model,{hole_rank_excluded_by_peek:null,
    split:'common_shoe_sequential_two_hand_no_resplit_binary_float_v1',split_hands:2,
    split_deal_order:'finish_first_before_dealing_second',
    split_aces:'one_card_no_double_no_natural_premium',
    split_exhaustion:'refuse_any_unavailable_continuation',enumeration_state_limit:100000});
  constructed.decision={action:'P',action_name:'SPLIT',evs:{S:1,H:-2/3,D:-4/3,P:2},
    margin:1,units:'original_wager',whole_game_estimate:null};
  const common=process.env.SOLVER_RECORD_COMMON ? await readFile(process.env.SOLVER_RECORD_COMMON) :
    Buffer.from(JSON.stringify(constructed));
  const legacy=process.env.SOLVER_RECORD_APPROX ? await readFile(process.env.SOLVER_RECORD_APPROX) : recordFixture;
  console.log('Common inspection inputs:',JSON.stringify({source:process.env.SOLVER_RECORD_COMMON ?
    'provided installed common output' : 'constructed admission fixture',
    sha256:[common,legacy].map(buffer=>createHash('sha256').update(buffer).digest('hex'))}));
  for (const [first,second] of [[legacy,common],[common,legacy]]) {
    await acceptedRecord(page,'a',first);await assertCompleteRecord(page,'a',first);
    await acceptedRecord(page,'b',second);await assertCompleteRecord(page,'b',second);
    const comparison=page.locator('#record-comparison');
    assert.match(await comparison.textContent(),/different mathematical split models/);
    const model=comparison.getByRole('rowheader',{name:'model.split',exact:true});
    const limit=comparison.getByRole('rowheader',{name:'model.enumeration_state_limit',exact:true});
    assert.equal(await model.count(),1);assert.equal(await limit.count(),1);
    const cells=await limit.locator('..').locator('td').allTextContents();
    assert.deepEqual(cells,first===common ? [String(JSON.parse(common).model.enumeration_state_limit),
      'absent (not declared by this model)'] : ['absent (not declared by this model)',
      String(JSON.parse(common).model.enumeration_state_limit)]);
    const order=await comparison.evaluate(node=>{
      const text=node.textContent;return text.indexOf('different mathematical split models')<text.indexOf('4. Recorded answer comparison');
    });
    assert.equal(order,true);
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  }
});

test('all four current controls retain complete inputs and match current action presence',async t=>{
  const page=await fixture(t,{viewport:{width:390,height:844}});await ready(page);
  const records=await actualControlRecords();
  console.log('Current control inputs:',JSON.stringify(records.map(({label,buffer})=>({
    label,source:process.env[`SOLVER_RECORD_${label}`] ? 'provided installed output' : 'constructed representation',
    sha256:createHash('sha256').update(buffer).digest('hex')
  }))));
  for (const {label,double,pair,buffer} of records) {
    const saved=JSON.parse(buffer);
    assert.deepEqual(effectiveControls(saved),{can_double:double,can_split:pair});
    assert.equal(saved.schema.version,double && pair ? 1 : 2);
    // Both the installed tiny pair and the fallback nonpair have two cards,
    // no split state, and enough retained cards. Assert those prerequisites
    // before forming the independent expected current-control action set.
    assert.equal(saved.state.cards.length,2);assert.notEqual(saved.state.total,21);
    assert.equal(saved.state.is_split_hand,false);assert.equal(saved.state.hand_count,1);
    assert.ok(saved.state.shoe.counts.reduce((sum,n)=>sum+n,0)>=3);
    assert.ok(saved.rules.max_hands>1);
    const mayPair=saved.state.cards[0]===saved.state.cards[1];
    const expected=['H','S',...(double ? ['D'] : []),...(pair && mayPair ? ['P'] : [])];
    assert.deepEqual(Object.keys(saved.decision.evs).sort(),[...expected].sort());
    await acceptedRecord(page,'a',buffer,`controls-${label}.json`);
    await assertCompleteRecord(page,'a',buffer,expected);
    assert.equal(await page.locator('#record-result-a [data-action-set-status]').getAttribute('data-action-set-status'),'matches');
    await page.locator('#record-file-a').focus();await page.keyboard.press('Tab');
    assert.equal(await page.locator('#record-clear-a').evaluate(e=>document.activeElement===e),true);
  }
  await acceptedRecord(page,'a',records[1].buffer);await acceptedRecord(page,'b',records[2].buffer);
  const changed=page.locator('#record-comparison').getByRole('region',{name:'Modeled input changes, before answer differences',exact:true});
  for (const [key,left,right] of [['can_double','false','true'],['can_split','true','false']]) {
    const row=changed.locator('tbody tr').filter({has:page.getByRole('rowheader',{name:`state.action_controls.${key}`,exact:true})});
    assert.deepEqual(await row.locator('td').allTextContents(),[left,right]);
  }
});

const lateFixture=({surrender=true,tie=false,hidden=false}={})=>alteredRecord(saved=>{
  saved.schema.version=4;
  Object.assign(saved.state,{cards:['T',tie ? '8' : hidden ? '4' : '6'],dealer_up:'T',
    total:tie ? 18 : hidden ? 14 : 16,soft:false,
    action_controls:{can_double:true,can_split:false,can_surrender:surrender}});
  saved.state.shoe.counts=tie ? [...Array(7).fill(0),2,0,2] : hidden ?
    [0,1,1,0,0,0,1,1,1,1] : [...Array(9).fill(0),3];
  Object.assign(saved.rules,{max_hands:1,surrender:true,resplit_aces:false,hit_split_aces:false});
  saved.model={name:'post_peek_late_surrender',version:1,dealer_information:'hidden_hole_post_peek',
    hole_rank_excluded_by_peek:'A',ten_value_ranks:'collapsed_to_T',insurance_priced:false,
    hit_stand_double:'finite_enumeration_binary_floating_point',split:'excluded_single_original_hand',
    decision_phase:'initial_original_two_card_below_21',
    surrender:'terminal_half_original_wager_post_negative_peek',surrender_after_hit:false,
    surrender_after_double:false,surrender_draws:0,
    player_last_draw:'stand_then_require_dealer_settlement',enumeration_state_limit:100000};
  const evs=hidden ? {S:-0.6666666666666665,H:-0.5916666666666668,D:-1.2000000000000002} :
    {S:tie ? -0.5 : -1,H:-1,D:-2};
  if (surrender) evs.R=-0.5;
  const action=surrender && !tie ? 'R' : hidden ? 'H' : 'S';
  const ranked=Object.values(evs).sort((a,b)=>b-a);
  saved.decision={action,action_name:{S:'STAND',H:'HIT',R:'SURRENDER'}[action],evs,
    margin:ranked[0]-ranked[1],units:'original_wager',whole_game_estimate:null};
});

test('late-surrender records show current permission and family coverage before answers',async t=>{
  const page=await fixture(t,{viewport:{width:390,height:844}});await ready(page);
  const kinds=['WINNING','DISABLED','TIE','HIDDEN'];
  const provided=kinds.map(kind=>process.env[`SOLVER_RECORD_SURRENDER_${kind}`]);
  assert.ok(provided.every(Boolean) || provided.every(value=>!value),
    'Provide all four installed late-surrender records or none');
  const fallback=[lateFixture(),lateFixture({surrender:false}),lateFixture({tie:true}),lateFixture({hidden:true})];
  const records=await Promise.all(kinds.map(async(kind,i)=>({kind,path:provided[i] ?? null,
    buffer:provided[i] ? await readFile(provided[i]) : fallback[i]})));
  const legacyPath=process.env.SOLVER_RECORD_APPROX ?? null;
  const commonPath=process.env.SOLVER_RECORD_COMMON ?? null;
  const legacy=legacyPath ? await readFile(legacyPath) : recordFixture;
  const commonSaved=JSON.parse(recordFixture);
  commonSaved.schema.version=3;
  Object.assign(commonSaved.state,{cards:['T','T'],dealer_up:'7',total:20,soft:false,
    action_controls:{can_double:true,can_split:true}});
  commonSaved.state.shoe.counts=[1,...Array(8).fill(0),5];commonSaved.rules.max_hands=2;
  Object.assign(commonSaved.model,{hole_rank_excluded_by_peek:null,
    split:'common_shoe_sequential_two_hand_no_resplit_binary_float_v1',split_hands:2,
    split_deal_order:'finish_first_before_dealing_second',split_aces:'one_card_no_double_no_natural_premium',
    split_exhaustion:'refuse_any_unavailable_continuation',enumeration_state_limit:100000});
  commonSaved.decision={action:'P',action_name:'SPLIT',evs:{S:1,H:-2/3,D:-4/3,P:2},
    margin:1,units:'original_wager',whole_game_estimate:null};
  const common=commonPath ? await readFile(commonPath) : Buffer.from(JSON.stringify(commonSaved));
  console.log('Late-surrender inspection invocation:',JSON.stringify({
    base_url:base+'/',site_directory:root,published:Boolean(process.env.SOLVER_BROWSER_BASE_URL),
    browser_engine:process.env.SOLVER_BROWSER_ENGINE ?? 'chromium',
    browser_channel:process.env.SOLVER_BROWSER_CHANNEL ?? null,browser_version:browser.version(),
    inputs:[...records,{kind:'LEGACY',path:legacyPath,buffer:legacy},{kind:'COMMON',path:commonPath,buffer:common}]
      .map(({kind,path:source,buffer})=>({kind,path:source,
        origin:source ? 'provided installed output' : 'constructed admission fixture',
        bytes:buffer.length,sha256:createHash('sha256').update(buffer).digest('hex')}))
  }));
  await page.waitForLoadState('networkidle');
  const requests=[];page.on('request',request=>requests.push(request.url()));
  for (const {buffer} of records) {
    const saved=JSON.parse(buffer);
    const permitted=['S','H',...(saved.state.action_controls.can_double ? ['D'] : []),
      ...(saved.state.action_controls.can_surrender ? ['R'] : [])];
    await acceptedRecord(page,'a',buffer);await assertCompleteRecord(page,'a',buffer,permitted);
    assert.match(await page.locator('#record-result-a').textContent(),/original initial two-card hand below 21/);
    assert.match(await page.locator('#record-result-a').textContent(),/Hit continuations offer no surrender or double/);
  }
  const winner=records[0].buffer,disabled=records[1].buffer;
  const comparison=page.locator('#record-comparison');
  for (const previous of [legacy,common]) for (const [a,b] of [[previous,winner],[winner,previous]]) {
    await acceptedRecord(page,'a',a);await assertCompleteRecord(page,'a',a);
    await acceptedRecord(page,'b',b);await assertCompleteRecord(page,'b',b);
    assert.match(await comparison.textContent(),/different mathematical families/);
    const rows=comparison.getByRole('region',{name:'Modeled input changes, before answer differences',exact:true});
    const stored=rows.getByRole('rowheader',{name:'state.action_controls.can_surrender',exact:true}).locator('..');
    const effective=rows.getByRole('rowheader',{name:'effective_action_controls.can_surrender',exact:true}).locator('..');
    assert.deepEqual(await stored.locator('td').allTextContents(),a===winner ?
      ['true','absent (not declared by this model)'] : ['absent (not declared by this model)','true']);
    assert.deepEqual(await effective.locator('td').allTextContents(),a===winner ? ['true','false'] : ['false','true']);
    for (const field of ['model.decision_phase','model.surrender','model.player_last_draw'])
      assert.equal(await rows.getByRole('rowheader',{name:field,exact:true}).count(),1);
    const answers=comparison.getByRole('region',{name:'Union of recorded actions, with absence distinguished from zero',exact:true});
    const r=answers.getByRole('rowheader',{name:'R (SURRENDER)',exact:true}).locator('..');
    assert.deepEqual((await r.locator('td').allTextContents()).slice(0,2),a===winner ? ['-0.5','absent'] : ['absent','-0.5']);
    assert.equal(await comparison.evaluate(node=>node.textContent.indexOf('different mathematical families')<
      node.textContent.indexOf('4. Recorded answer comparison')),true);
  }
  await acceptedRecord(page,'a',winner);await acceptedRecord(page,'b',disabled);
  assert.match(await comparison.textContent(),/same post-peek late-surrender family/);
  const r=page.locator('#record-result-b').getByRole('region',{
    name:'Record B derived permitted actions beside supplied EV presence',exact:true})
    .getByRole('rowheader',{name:'R (SURRENDER)',exact:true}).locator('..');
  assert.deepEqual(await r.locator('td').allTextContents(),['false','absent (no saved value)']);
  assert.deepEqual(requests,[],'Local V4 imports trigger no requests');
  await page.setViewportSize({width:320,height:844});
  await page.addStyleTag({content:'#record-inspector{font-size:34px}#record-inspector .fine{font-size:28px}#record-inspector th{font-size:30px}#record-inspector h3{font-size:40px}'});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.locator('#record-inspector .table-wrap').first().focus();
  assert.equal(await page.locator('#record-inspector .table-wrap').first().evaluate(e=>document.activeElement===e),true);
  await capture(page,'late-surrender-enlarged-320',false);
});

test('mixed version true defaults compare in both directions and disabled saved actions warn',async t=>{
  const page=await fixture(t);await ready(page);
  const declared=alteredRecord(r=>{r.schema.version=2;r.state.action_controls={can_split:true,can_double:true};});
  for (const [a,b] of [[recordFixture,declared],[declared,recordFixture]]) {
    await acceptedRecord(page,'a',a);await acceptedRecord(page,'b',b);
    await assertCompleteRecord(page,'a',a);await assertCompleteRecord(page,'b',b);
    const comparison=page.locator('#record-comparison');
    assert.match(await comparison.textContent(),/All modeled inputs agree/);
    assert.equal(await comparison.getByRole('region',{name:'Modeled input changes, before answer differences',exact:true}).count(),0);
    const metadata=comparison.getByRole('region',{name:'Record label changes',exact:true});
    assert.equal(await metadata.locator('tbody tr').count(),1);
    assert.equal(await metadata.getByRole('rowheader',{name:'schema.version',exact:true}).count(),1);
  }
  const altered=alteredRecord(r=>{
    r.schema.version=2;r.state.action_controls={can_double:false,can_split:false};
    r.decision.action='D';r.decision.action_name='DOUBLE';
  });
  await acceptedRecord(page,'a',altered);await assertCompleteRecord(page,'a',altered,['H','S']);
  assert.match(await page.locator('#record-result-a [data-action-set-status]').textContent(),/Saved EVs include unavailable actions: D/);
  assert.match(await page.locator('#record-result-a [data-action-set-status]').textContent(),/Recorded recommendation D is unavailable/);
});

test('constructed record differences retain split order, absence and raw precision',async t=>{
  const page=await fixture(t);await ready(page);
  const split=alteredRecord(r=>{r.state.cards=['A','4'];r.state.total=15;r.state.soft=true;r.state.is_split_hand=true;r.state.hand_count=2;r.decision.action='P';r.decision.action_name='SPLIT';r.decision.evs.P=99;r.decision.margin=80;});
  await acceptedRecord(page,'a',split);
  await assertCompleteRecord(page,'a',split,['S']);
  const reordered=JSON.parse(split);reordered.state.cards.reverse();delete reordered.decision.evs.D;
  reordered.decision.evs.H=-0.5916666666666667;
  await acceptedRecord(page,'b',Buffer.from(JSON.stringify(reordered)));
  await assertPermittedActions(page,'b',['H','S','D'],reordered);
  const comparison=page.locator('#record-comparison');
  const eligibility=comparison.getByRole('region',{name:'Derived action eligibility for each modeled input',exact:true});
  for (const action of ['H','D']) {
    const row=eligibility.locator('tbody tr').filter({has:page.getByRole('rowheader',{name:new RegExp('^'+action+' \\(')})});
    assert.deepEqual(await row.locator('td').allTextContents(),['false','true']);
  }
  assert.match(await comparison.textContent(),/state.cards/);
  const values=comparison.getByRole('region',{name:'Union of recorded actions, with absence distinguished from zero',exact:true});
  const double=values.locator('tbody tr').filter({has:page.getByRole('rowheader',{name:'D (DOUBLE)',exact:true})});
  assert.deepEqual(await double.locator('td').allTextContents(),['-1.2000000000000002','absent','false','not available: action absent']);
  const hit=values.locator('tbody tr').filter({has:page.getByRole('rowheader',{name:'H (HIT)',exact:true})});
  assert.deepEqual((await hit.locator('td').allTextContents()).slice(0,3),['-0.5916666666666668','-0.5916666666666667','false']);
  const labelOnly=JSON.parse(split);labelOnly.package.version='future <img src=x onerror=alert(1)>';
  await acceptedRecord(page,'b',Buffer.from(JSON.stringify(labelOnly)));
  assert.match(await comparison.textContent(),/All modeled inputs agree/);
  assert.match(await comparison.textContent(),/future <img src=x onerror=alert\(1\)>/);
  assert.equal(await comparison.locator('img').count(),0);
  await assertPermittedActions(page,'b',['S'],labelOnly);
  const huge=recordFixture.toString().replace('"counts": [\n        0','"counts": [\n        '+'1'+'0'.repeat(400));
  await acceptedRecord(page,'a',Buffer.from(huge));
  const count=page.locator('#record-result-a tbody tr').filter({has:page.getByRole('rowheader',{name:'state.shoe.counts.A',exact:true})});
  assert.equal(await count.locator('td').textContent(),'1'+'0'.repeat(400));
  await assertPermittedActions(page,'a',['H','S','D'],JSON.parse(recordFixture));
  const settled=JSON.parse(recordFixture);settled.state.cards=['A','T'];settled.state.total=21;settled.state.soft=true;
  await acceptedRecord(page,'a',Buffer.from(JSON.stringify(settled)));
  await assertCompleteRecord(page,'a',Buffer.from(JSON.stringify(settled)),['S']);
  const oneUnseen=JSON.parse(recordFixture);oneUnseen.state.shoe.counts=[0,1,0,0,0,0,0,0,0,0];
  await acceptedRecord(page,'a',Buffer.from(JSON.stringify(oneUnseen)));
  await assertCompleteRecord(page,'a',Buffer.from(JSON.stringify(oneUnseen)),['S']);
});

test('imports stay out of URLs, requests and storage and reload releases them',async t=>{
  const page=await fixture(t);await ready(page);await page.waitForLoadState('networkidle');
  const requests=[];page.on('request',request=>requests.push({url:request.url(),body:request.postData()}));
  const beforeURL=page.url(),beforeLink=await page.locator('#example-link').getAttribute('href');
  await page.evaluate(()=>{
    window.recordStorageWrites=[];
    const old=Storage.prototype.setItem;
    Storage.prototype.setItem=function(key,value){window.recordStorageWrites.push([key,value]);return old.call(this,key,value);};
    window.recordIDBCalls=0;
    const oldOpen=IDBFactory.prototype.open;
    IDBFactory.prototype.open=function(...args){window.recordIDBCalls++;return oldOpen.apply(this,args);};
  });
  const secret='local-private-marker-47';
  const selected=JSON.parse(controlledRecord(false,false));selected.package.version=secret;
  const selectedBytes=Buffer.from(JSON.stringify(selected));
  await acceptedRecord(page,'a',selectedBytes,secret+'.json');await acceptedRecord(page,'b',selectedBytes,secret+'-second.json');
  assert.equal(page.url(),beforeURL);assert.equal(await page.locator('#example-link').getAttribute('href'),beforeLink);
  assert.deepEqual(await page.evaluate(()=>window.recordStorageWrites),[]);
  assert.equal(await page.evaluate(()=>window.recordIDBCalls),0);
  assert.deepEqual(requests,[],'File imports trigger no requests');
  await page.locator('#choice').selectOption('1');
  assert.ok(!page.url().includes(secret));assert.ok(!(await page.locator('#example-link').getAttribute('href')).includes(secret));
  await page.reload();await page.locator('#record-inspector:visible').waitFor();
  assert.equal(await page.locator('#record-result-a').isVisible(),false);
  assert.equal(await page.locator('#record-result-b').isVisible(),false);
  assert.equal(await page.locator('#record-inspector').textContent().then(text=>text.includes(secret)),false);
});

test('local inspection works when bundled data is unavailable and no-script evidence stays usable',async t=>{
  const page=await fixture(t);
  await page.route('**/data.json',route=>route.fulfill({status:200,contentType:'application/json',body:'{}'}));
  await page.goto(base+'/');await page.locator('#load-error:visible').waitFor();
  await page.locator('#record-inspector:visible').waitFor();
  await acceptedRecord(page,'a',recordFixture);await assertCompleteRecord(page,'a',recordFixture);
  const noScript=await fixture(t,{javaScriptEnabled:false,viewport:{width:320,height:700}});
  await noScript.goto(base+'/');
  assert.equal(await noScript.locator('#record-inspector').isVisible(),false);
  assert.match(await noScript.locator('noscript').allTextContents().then(parts=>parts.join(' ')),/Local saved-record inspection needs JavaScript/);
  assert.equal(await noScript.locator('#composition-figure img:visible').count(),1);
});

for (const width of [320,390]) test(`imported records retain local scrolling and enlarged text at ${width}px`,async t=>{
  const page=await fixture(t,{viewport:{width,height:844},colorScheme:'dark'});await ready(page);
  const records=await actualControlRecords();
  await acceptedRecord(page,'a',records[1].buffer);await acceptedRecord(page,'b',records[3].buffer);
  await assertCompleteRecord(page,'a',records[1].buffer);await assertCompleteRecord(page,'b',records[3].buffer);
  for (const appearance of ['clair','obscur']) {
    await page.locator('#appearance').selectOption(appearance);
    const original=await page.locator('#record-inspector').textContent();
    await page.addStyleTag({content:'#record-inspector{font-size:34px}#record-inspector .fine{font-size:28px}#record-inspector th{font-size:30px}#record-inspector h3{font-size:40px}#record-inspector h2{font-size:54px}'});
    assert.equal(await page.locator('#record-inspector').textContent(),original);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    assert.ok(await page.locator('#record-inspector .table-wrap').first().evaluate(e=>e.scrollWidth>e.clientWidth));
    await page.locator('#record-inspector .table-wrap').first().focus();
    assert.equal(await page.locator('#record-inspector .table-wrap').first().evaluate(e=>document.activeElement===e),true);
    await capture(page,`local-record-${appearance}-${width}`,false);
  }
});

const phoneFonts = [
  {label:'',family:null},
  {label:' with the missing-font system fallback',family:'"Solver deliberately missing face",system-ui,"Segoe UI",sans-serif'},
  {label:' with the missing-font Verdana or sans-serif fallback',family:'"Solver deliberately missing face",Verdana,sans-serif'},
];
for (const route of ['index.html','joint-split.html']) for (const fallback of phoneFonts) test(
  `phone text enlargement keeps ${route} prose inside the configured width` +
    fallback.label, async t => {
    const width = 320;
    const page = await fixture(t, {viewport:{width,height:700},hasTouch:true,isMobile:true});
    await page.goto(base+'/'+route);
    await page.locator('#appearance:not([disabled])').waitFor();
    if (route === 'index.html') await page.locator('#interactive:visible').waitFor();
    if (fallback.family) {
      await page.addStyleTag({content:
        `body{font-family:${fallback.family} !important}`});
      assert.match(await page.locator('h1').evaluate(e => getComputedStyle(e).fontFamily),
        /Solver deliberately missing face/);
    }
    await page.evaluate(() => document.fonts.ready);
    if (process.env.SOLVER_BROWSER_ENGINE !== 'webkit') {
      for (const selector of route === 'index.html' ? ['h1','#engineering h3','#engineering a'] : ['h1']) {
        const providers = await fonts(page,selector);
        assert.ok(providers.length > 0);
        console.log(`Enlarged ${route}${fallback.label} ${selector} glyph providers:`,JSON.stringify(providers));
      }
    }
    const prose = await page.locator('main').textContent();
    await page.evaluate(() => {
      const text = [...document.querySelectorAll('body *')].filter(e =>
        e instanceof HTMLElement && [...e.childNodes].some(node =>
          node.nodeType === Node.TEXT_NODE && node.textContent.trim()));
      const initial = text.map(element => [element,parseFloat(getComputedStyle(element).fontSize)]);
      for (const [element,size] of initial) element.style.fontSize = `${size*2}px`;
    });
    assert.equal(await page.locator('main').textContent(),prose,'Text remains complete');
    assert.equal(await page.locator('h2').first().evaluate(e =>
      parseFloat(getComputedStyle(e).fontSize)),54,'Headings stay enlarged');
    const geometry = await page.evaluate(width => {
      const overflow = [];
      for (const element of document.querySelectorAll('main *')) {
        if (!(element instanceof HTMLElement) || element.closest('.table-wrap,.chart-wrap,pre')) continue;
        for (const node of element.childNodes) {
          if (node.nodeType !== Node.TEXT_NODE || !node.textContent.trim()) continue;
          const range = document.createRange(); range.selectNodeContents(node);
          if ([...range.getClientRects()].some(rect => rect.right > width+1 || rect.left < -1)) {
            overflow.push(node.textContent.trim());
          }
        }
      }
      return {scrollWidth:document.documentElement.scrollWidth,overflow};
    },width);
    assert.ok(geometry.scrollWidth <= width,JSON.stringify(geometry));
    assert.deepEqual(geometry.overflow,[],'Ordinary prose wraps without page overflow');
    if (route === 'joint-split.html') {
      const chart = await page.locator('.chart-wrap').evaluate(element => {
        element.scrollLeft = 120;
        return {width:element.clientWidth,scrollWidth:element.scrollWidth,left:element.scrollLeft};
      });
      assert.ok(chart.scrollWidth >= 980 && chart.left > 0 && chart.width <= width,
        'The quantitative figure retains its local scroll region');
    }
    await capture(page,'enlarged-320-'+route.replace('.html','')+
      (fallback.family?(fallback.family.includes('Verdana')?'-wide-fallback':'-system-fallback'):''),false);
  });

test('Auto and overrides preserve the selected hand, exact saved data and history', async t => {
  const page = await fixture(t, {colorScheme:'dark'});
  await ready(page);
  assert.equal(await background(page), 'rgb(9, 9, 9)');
  await page.locator('#choice').selectOption('1');
  const before = await page.locator('#interactive').textContent();
  const selectedURL = page.url();
  await page.locator('#appearance').selectOption('clair');
  assert.equal(await background(page), 'rgb(248, 247, 243)');
  assert.equal(await page.locator('#interactive').textContent(), before);
  assert.equal(page.url(), selectedURL);
  await page.reload();
  await page.locator('#interactive:visible').waitFor();
  assert.equal(await page.locator('#choice').inputValue(), '1');
  assert.equal(await page.locator('#appearance').inputValue(), 'clair');
  await page.emulateMedia({colorScheme:'dark'});
  assert.equal(await background(page), 'rgb(248, 247, 243)');
  await page.locator('#appearance').selectOption('auto');
  assert.equal(await background(page), 'rgb(9, 9, 9)');
  await page.emulateMedia({colorScheme:'light'});
  assert.equal(await background(page), 'rgb(248, 247, 243)');
  await page.locator('#choice').selectOption('0');
  await page.goBack();
  assert.equal(await page.locator('#choice').inputValue(), '1');
  await page.goForward();
  assert.equal(await page.locator('#choice').inputValue(), '0');
  assert.deepEqual(await page.evaluate(async () => (await fetch('data.json')).json()), evidence);
});

test('blocked storage leaves the controls usable without claiming persistence', async t => {
  const page = await fixture(t, {colorScheme:'light'}, true);
  await ready(page);
  await page.locator('#appearance').selectOption('obscur');
  assert.equal(await background(page), 'rgb(9, 9, 9)');
  await page.reload();
  assert.equal(await background(page), 'rgb(248, 247, 243)');
});

test('no JavaScript keeps Auto, original evidence and model boundaries available', async t => {
  const page = await fixture(t, {javaScriptEnabled:false, colorScheme:'dark'});
  await page.goto(base+'/');
  assert.equal(await page.locator('#appearance').isDisabled(), true);
  assert.equal(await page.locator('#interactive').isHidden(), true);
  assert.equal(await background(page), 'rgb(9, 9, 9)');
  await page.locator('#composition-figure img:visible').scrollIntoViewIfNeeded();
  await page.waitForFunction(() => [...document.querySelectorAll('#composition-figure img')]
    .filter(e => getComputedStyle(e).display !== 'none').every(e => e.complete && e.naturalWidth > 0));
  assert.match(await page.locator('body').textContent(), /Split valuation elsewhere in the project is approximate/);
  assert.equal(await page.locator('a[href="data.json"]').first().isVisible(), true);
  await page.emulateMedia({colorScheme:'light'});
  assert.equal(await background(page), 'rgb(248, 247, 243)');
});

for (const mode of ['clair','obscur']) test(`${mode} preserves loss values and evidence at narrow and enlarged sizes`, async t => {
  const page = await fixture(t);
  await ready(page);
  await page.locator('#appearance').selectOption(mode);
  for (let index = 0; index < evidence.hands.length; index++) {
    await page.locator('#choice').selectOption(String(index));
    const hand = evidence.hands[index];
    const values = Object.values(hand.values).sort((a,b) => b-a).map(n => n.toFixed(6));
    assert.deepEqual(await page.locator('tbody td:last-child').allTextContents(), values);
    assert.equal(await page.locator('.metric strong').nth(1).textContent(), hand.values[hand.action].toFixed(6));
    assert.equal(await page.locator('.metric strong').nth(2).textContent(), hand.margin.toFixed(6));
    assert.match(await page.locator('#finding').textContent(), /expected loss/);
    assert.match(await page.locator('#context').textContent(), /Six decks; visible cards removed/);
  }
  assert.match(await page.locator('body').textContent(), /per original wager, not win probabilities/);
  assert.equal(await page.locator('#composition-figure img:visible').evaluate(e => getComputedStyle(e).filter), 'none');
  const downloadPromise = page.waitForEvent('download');
  await page.locator('a[href="example.svg"][download]').click();
  const download = await downloadPromise;
  assert.deepEqual(await readFile(await download.path()), originalSVG);
  await capture(page, mode+'-wide');
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await capture(page, mode+'-narrow');
  await page.locator('#appearance').focus();
  assert.equal(await page.evaluate(() => document.activeElement.id), 'appearance');
  await page.keyboard.press('Tab');
  assert.equal(await page.evaluate(() => document.activeElement.matches('a.button')), true);
  await page.locator('#choice').focus();
  await page.keyboard.press('ArrowUp');
  assert.equal(await page.locator('#choice').inputValue(), '0');
  assert.equal(await page.locator('#choice').evaluate(e => getComputedStyle(e).outlineStyle), 'solid');
  await page.addStyleTag({content:'body{font-size:34px !important}'});
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await page.locator('.table-wrap').focus();
  assert.equal(await page.locator('.table-wrap').evaluate(e => getComputedStyle(e).outlineStyle), 'solid');
});

test('print uses Clair and forced colors preserve focus without changing the preference', async t => {
  const page = await fixture(t);
  await ready(page);
  await page.locator('#appearance').selectOption('obscur');
  await page.emulateMedia({media:'print'});
  assert.equal(await background(page), 'rgb(248, 247, 243)');
  assert.equal(await page.evaluate(() => localStorage.getItem('exact-blackjack-solver.appearance.v1')), 'obscur');
  await page.emulateMedia({media:'screen', forcedColors:'active'});
  await page.locator('#choice').focus();
  assert.equal(await page.locator('#choice').evaluate(e => getComputedStyle(e).outlineStyle), 'solid');
  assert.equal(await page.evaluate(() => matchMedia('(forced-colors: active)').matches), true);
  await page.emulateMedia({forcedColors:'none'});
  assert.equal(await background(page), 'rgb(9, 9, 9)');
});

async function fonts(page, selector) {
  const session = await page.context().newCDPSession(page);
  try {
    await session.send('DOM.enable'); await session.send('CSS.enable');
    const {root} = await session.send('DOM.getDocument');
    const {nodeId} = await session.send('DOM.querySelector', {nodeId:root.nodeId, selector});
    return (await session.send('CSS.getPlatformFontsForNode', {nodeId})).fonts.filter(f => f.glyphCount > 0);
  } finally { await session.detach(); }
}
test('a missing font supplies readable fallback separately from Inter acceptance', async t => {
  const page = await fixture(t);
  await ready(page);
  await page.evaluate(() => {
    const sample = document.createElement('p'); sample.id='missing-face';
    sample.style.fontFamily='"Solver deliberately missing face", Arial, sans-serif';
    sample.textContent='Readable fallback 123'; document.body.append(sample);
  });
  await page.locator('#missing-face').evaluate(e => e.getBoundingClientRect());
  await page.evaluate(() => document.fonts.ready);
  const providers = await fonts(page, '#missing-face');
  assert.ok(providers.length > 0);
  assert.ok(providers.every(f => !f.postScriptName.startsWith('Inter')));
  console.log('Separate missing-font fallback:', JSON.stringify(providers));
});

const jointEvidence = JSON.parse(await readFile(new URL('../../docs/joint-split-results.json', import.meta.url)));
for (const mode of ['clair','obscur']) test(`joint report ${mode} preserves every condition, downloads and navigation`, async t => {
  const page = await fixture(t);
  await ready(page);
  await page.locator('#joint-reference a').click();
  assert.equal(page.url(), new URL('joint-split.html', base+'/').href);
  await page.locator('#appearance').selectOption(mode);
  assert.equal(await page.locator('#conditions tbody tr').count(), 48);
  assert.equal(await page.locator('#changes tbody tr').count(), 1);
  assert.equal(await page.locator('[data-condition]').count(), 48);
  assert.match(await page.locator('#attempts').textContent(), /first comparison was invalid/);
  const cells = await page.locator('#conditions tbody tr').evaluateAll(rows => rows.map(row =>
    [...row.querySelectorAll('td')].map(cell => cell.textContent)));
  for (let index=0; index<48; index++) {
    const saved = jointEvidence.rows[index];
    assert.equal(cells[index][2], saved.production.values.P.toFixed(9));
    assert.equal(cells[index][3], saved.reference.value.toFixed(9));
    assert.equal(Number(cells[index][4]), Number(saved.signed_gap.toFixed(9)));
    assert.equal(cells[index][9], String(saved.reference.states));
  }
  const downloads = await page.locator('a[download]').evaluateAll(links => [...new Set(links.map(a => a.getAttribute('href')))]);
  assert.equal(downloads.length, 7);
  for (const name of downloads) {
    const pending = page.waitForEvent('download');
    await page.locator(`a[download][href="${name}"]`).first().click();
    const download = await pending;
    assert.deepEqual(await readFile(await download.path()), await readFile(path.join(root, name)));
  }
  await page.evaluate(() => scrollTo(0,0));
  if (process.env.SOLVER_SCREENSHOT_DIR) {
    await mkdir(process.env.SOLVER_SCREENSHOT_DIR,{recursive:true});
    await page.screenshot({path:path.join(process.env.SOLVER_SCREENSHOT_DIR,`joint-${mode}-wide.png`)});
    await page.locator('.chart-wrap').screenshot({path:path.join(process.env.SOLVER_SCREENSHOT_DIR,`joint-${mode}-chart.png`)});
  }
  const before = await page.locator('#conditions').textContent();
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await page.evaluate(() => scrollTo(0,0));
  if (process.env.SOLVER_SCREENSHOT_DIR) await page.screenshot({path:path.join(process.env.SOLVER_SCREENSHOT_DIR,`joint-${mode}-narrow.png`)});
  await page.locator('.chart-wrap').focus();
  await page.keyboard.press('ArrowRight');
  await page.waitForFunction(() => document.querySelector('.chart-wrap').scrollLeft > 0);
  assert.equal(await page.locator('.chart-wrap').evaluate(e => getComputedStyle(e).outlineStyle),'solid');
  await page.locator('#all-conditions .table-wrap').focus();
  await page.keyboard.press('ArrowRight');
  await page.waitForFunction(() => document.querySelector('#all-conditions .table-wrap').scrollLeft > 0);
  await page.addStyleTag({content:'body{font-size:30px !important}'});
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  assert.equal(await page.locator('#conditions').textContent(), before);
  await page.reload();
  assert.equal(await page.locator('#appearance').inputValue(), mode);
  await page.locator('nav a[href="index.html"]').click();
  await page.locator('#interactive:visible').waitFor();
  await page.goBack();
  assert.equal(await page.locator('#conditions tbody tr').count(), 48);
  assert.equal(await page.locator('#appearance').inputValue(), mode);
  await page.goForward();
  await page.locator('#interactive:visible').waitFor();
});

test('joint report Auto, blocked storage, no script and print retain readable evidence', async t => {
  const page = await fixture(t,{colorScheme:'dark'},true);
  await page.goto(base+'/joint-split.html');
  assert.equal(await background(page),'rgb(9, 9, 9)');
  await page.locator('#appearance').selectOption('clair');
  assert.equal(await background(page),'rgb(248, 247, 243)');
  await page.reload();
  assert.equal(await page.locator('#appearance').inputValue(),'auto');
  assert.equal(await background(page),'rgb(9, 9, 9)');
  await page.emulateMedia({colorScheme:'light'});
  assert.equal(await background(page),'rgb(248, 247, 243)');
  await page.locator('#appearance').selectOption('obscur');
  await page.emulateMedia({media:'print',colorScheme:'dark'});
  assert.equal(await background(page),'rgb(248, 247, 243)');
  const marker = page.locator('[data-condition="balanced_high/2/6/das-false"] circle');
  assert.equal(await marker.evaluate(e => getComputedStyle(e).fill),'rgb(54, 95, 120)');
  assert.equal(await page.locator('#appearance').inputValue(),'obscur');
  const noScript = await fixture(t,{javaScriptEnabled:false,colorScheme:'dark'});
  await noScript.goto(base+'/joint-split.html');
  assert.equal(await noScript.locator('#appearance').isDisabled(),true);
  assert.equal(await noScript.locator('#conditions tbody tr').count(),48);
  assert.equal(await noScript.locator('[data-condition]').count(),48);
  assert.equal(await background(noScript),'rgb(9, 9, 9)');
  assert.equal(await noScript.locator('a[href="joint-split.csv"]').isVisible(),true);
});

test('joint report and standalone figures use real local Inter glyph providers',
  {skip:process.env.SOLVER_REQUIRE_INTER !== '1'}, async t => {
  const page = await fixture(t);
  for (const mode of ['clair','obscur']) {
    await page.goto(base+'/joint-split.html');
    await page.locator('#appearance').selectOption(mode);
    await page.evaluate(() => document.fonts.ready);
    for (const [selector,expected] of [['h1','Inter-Bold'],['.lead','Inter-Regular'],
      ['label[for="appearance"]','Inter-SemiBold'],['.chart-wrap svg g text','Inter-SemiBold']]) {
      await page.locator(selector).first().evaluate(e => e.getBoundingClientRect());
      const providers = await fonts(page,selector);
      assert.ok(providers.some(f => f.postScriptName===expected),JSON.stringify({mode,selector,providers}));
      assert.ok(providers.every(f => f.postScriptName===expected));
      console.log('Report glyph provider:',JSON.stringify({mode,selector,providers}));
    }
    await page.goto(base+`/joint-split-${mode}.svg`);
    await page.evaluate(() => document.fonts.ready);
    const providers = await fonts(page,'g text');
    assert.ok(providers.some(f => f.postScriptName==='Inter-SemiBold'),JSON.stringify({mode,providers}));
    console.log('Standalone editable SVG glyph provider:',JSON.stringify({mode,providers}));
  }
});
test('six real Inter faces and ordinary text use the intended local providers',
  {skip:process.env.SOLVER_REQUIRE_INTER !== '1'}, async t => {
  const page = await fixture(t);
  await ready(page);
  const faces = [[400,'normal','Inter-Regular'],[600,'normal','Inter-SemiBold'],[700,'normal','Inter-Bold'],
    [400,'italic','Inter-Italic'],[600,'italic','Inter-SemiBoldItalic'],[700,'italic','Inter-BoldItalic']];
  await page.evaluate(faces => {
    for (const [weight,style,name] of faces) {
      const sample = document.createElement('p'); sample.id=name;
      sample.style.fontWeight=String(weight); sample.style.fontStyle=style;
      sample.textContent='Solver typography sample 123'; document.body.append(sample);
    }
  }, faces);
  await page.evaluate(() => document.fonts.ready);
  for (const mode of ['obscur','clair']) {
    await page.locator('#appearance').selectOption(mode);
    for (const [, , name] of faces) {
      const providers = await fonts(page, '#'+name);
      assert.ok(providers.some(f => f.postScriptName === name), JSON.stringify({mode,name,providers}));
      assert.ok(providers.every(f => f.postScriptName === name), 'Latin specimen cannot use fallback');
      console.log('Controlled local-font specimen:', JSON.stringify({mode,name,providers}));
    }
    for (const [selector,expected] of [['h1','Inter-Bold'],['.lead','Inter-Regular'],['label[for="appearance"]','Inter-SemiBold']]) {
      const providers = await fonts(page, selector);
      assert.ok(providers.some(f => f.postScriptName === expected));
      console.log('Ordinary interface text:', JSON.stringify({mode,selector,providers}));
    }
  }
  assert.match(await page.locator('code').evaluate(e => getComputedStyle(e).fontFamily), /Consolas/);
});

test('composition editions follow Auto and overrides without changing saved evidence', async t => {
  const page = await fixture(t,{colorScheme:'dark',viewport:{width:390,height:844}});
  await ready(page);
  const visible = page.locator('#composition-figure img:visible');
  assert.equal(await visible.getAttribute('src'),'composition-obscur.png');
  await page.locator('#choice').selectOption('1');
  const url = page.url(), values = await page.locator('#interactive').textContent();
  const receipt = await (await page.request.get(base+'/composition-figure.json')).json();
  assert.deepEqual(receipt.evidence.retained_values,evidence);
  assert.equal(receipt.evidence.solver_rerun,false);
  assert.equal(receipt.typography.painted_faces.length,6);
  for (const mode of ['clair','obscur']) {
    await page.locator('#appearance').selectOption(mode);
    assert.equal(await visible.getAttribute('src'),`composition-${mode}.png`);
    await visible.scrollIntoViewIfNeeded();
    await page.waitForFunction(() => [...document.querySelectorAll('#composition-figure img')]
      .filter(e => e.getBoundingClientRect().width > 0).every(e => e.complete && e.naturalWidth===960));
    assert.equal(await visible.evaluate(e => getComputedStyle(e).filter),'none');
    assert.equal(await page.locator('#interactive').textContent(),values);
    assert.equal(page.url(),url);
    for (const ext of ['svg','png']) {
      const name=`composition-${mode}.${ext}`;
      const pending=page.waitForEvent('download');
      await page.locator(`#composition-figure a[href="${name}"][download]`).click();
      const download=await pending;
      assert.deepEqual(await readFile(await download.path()),await readFile(path.join(root,name)));
    }
    for (const width of [1280,390]) {
      await page.setViewportSize({width,height:844});
      await visible.scrollIntoViewIfNeeded();
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth<=innerWidth),true);
      if (process.env.SOLVER_SCREENSHOT_DIR) await visible.screenshot({path:path.join(
        process.env.SOLVER_SCREENSHOT_DIR,`composition-${mode}-${width}.png`)});
    }
    await page.reload();
    await page.locator('#interactive:visible').waitFor();
    assert.equal(await page.locator('#appearance').inputValue(),mode);
    assert.equal(await page.locator('#interactive').textContent(),values);
  }
  await page.emulateMedia({media:'print'});
  assert.equal(await visible.getAttribute('src'),'composition-clair.png');
  assert.equal(await page.locator('#appearance').inputValue(),'obscur');
  await page.emulateMedia({media:'screen',colorScheme:'light'});
  await page.locator('#appearance').selectOption('auto');
  assert.equal(await visible.getAttribute('src'),'composition-clair.png');
  await page.emulateMedia({colorScheme:'dark'});
  assert.equal(await visible.getAttribute('src'),'composition-obscur.png');
  const noScript=await fixture(t,{javaScriptEnabled:false,colorScheme:'dark',viewport:{width:390,height:844}});
  await noScript.goto(base+'/');
  assert.equal(await noScript.locator('#composition-figure img:visible').getAttribute('src'),'composition-obscur.png');
  await noScript.emulateMedia({colorScheme:'light'});
  assert.equal(await noScript.locator('#composition-figure img:visible').getAttribute('src'),'composition-clair.png');
});

test('maintained Markdown pictures select the portable editions at narrow size', async t => {
  const page=await fixture(t,{viewport:{width:390,height:844},colorScheme:'light'});
  for (const name of ['README.md','docs/visual-example.md']) {
    const raw=await readFile(new URL('../../'+name,import.meta.url),'utf8');
    let picture=raw.match(/<picture>[\s\S]*?<\/picture>/)[0];
    picture=picture.replace(/(?:docs\/)?blackjack-composition-(clair|obscur)\.png/g,
      (_,mode)=>base+`/composition-${mode}.png`);
    await page.setContent('<!doctype html><html lang="en"><head><title>Authored picture check</title>'+
      '<style>body{margin:20px}img{max-width:100%;height:auto}</style></head><body>'+picture+'</body></html>');
    for (const [scheme,mode] of [['light','clair'],['dark','obscur']]) {
      await page.emulateMedia({colorScheme:scheme});
      await page.waitForFunction(mode => document.querySelector('img').currentSrc.endsWith(
        `composition-${mode}.png`) && document.querySelector('img').complete,mode);
      assert.equal(await page.locator('img').evaluate(e=>e.naturalWidth),960);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    }
  }
});


test('wide figure follows its container and preserves every delivered file', async t => {
  const page = await fixture(t, {viewport:{width:1280,height:900},colorScheme:'dark'});
  await page.goto(base+'/'); await page.locator('#appearance:not([disabled])').waitFor();
  for (const mode of ['clair','obscur']) {
    await page.locator('#appearance').selectOption(mode);
    const visible=page.locator('#composition-figure img:visible');
    assert.equal(await visible.count(),1);
    assert.equal(await visible.getAttribute('src'),`composition-${mode}-wide.png`);
    await visible.scrollIntoViewIfNeeded(); await visible.evaluate(e=>e.decode());
    assert.deepEqual(await visible.evaluate(e=>[e.naturalWidth,e.naturalHeight]),[1800,1280]);
    const destination=process.env.SOLVER_SCREENSHOT_DIR;
    if(destination){await mkdir(destination,{recursive:true});await visible.screenshot({path:path.join(destination,`composition-${mode}-wide.png`)});}
    await page.locator('#composition-figure').evaluate(e=>e.style.width='400px');
    assert.equal(await visible.getAttribute('src'),`composition-${mode}.png`);
    await page.locator('#composition-figure').evaluate(e=>e.style.removeProperty('width'));
    for(const suffix of ['','-wide'])for(const ext of ['png','svg']){
      const file=`composition-${mode}${suffix}.${ext}`;
      const response=await page.request.get(base+'/'+file);assert.equal(response.status(),200);
      assert.deepEqual(await response.body(),await readFile(path.join(root,file)));
    }
  }
});
