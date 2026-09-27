import assert from 'node:assert/strict';
import {before, after, test} from 'node:test';
import {createServer} from 'node:http';
import {readFile, mkdir} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

// An owned loopback server, headless sandbox and fresh temporary contexts only.
// Never connect to an existing browser or fall back to a visible window.
const root = fileURLToPath(new URL('../../_site/', import.meta.url));
const evidence = JSON.parse(await readFile(new URL('../../docs/visual-example-data.json', import.meta.url)));
const originalSVG = await readFile(new URL('../../docs/blackjack-composition-example.svg', import.meta.url));
const mime = {'.html':'text/html', '.css':'text/css', '.js':'text/javascript',
  '.mjs':'text/javascript', '.json':'application/json', '.svg':'image/svg+xml'};
let browser, server, base;
before(async () => {
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
  const channel = process.env.SOLVER_BROWSER_CHANNEL;
  if (channel && !['chrome','chromium'].includes(channel)) throw Error('Unsupported channel');
  browser = await chromium.launch({headless:true, chromiumSandbox:true, ...(channel ? {channel} : {})});
  console.log(`Isolated headless browser ${browser.version()}; sandbox requested; fresh contexts`);
});
after(async () => {
  if (browser) await browser.close();
  if (server) await new Promise(resolve => server.close(resolve));
});
async function fixture(t, options = {}, blockedStorage = false) {
  const context = await browser.newContext({viewport:{width:1280,height:900}, ...options});
  const failures = [], external = [];
  await context.route('**/*', route => {
    if (new URL(route.request().url()).origin !== base) {
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
async function capture(page, name) {
  if (!process.env.SOLVER_SCREENSHOT_DIR) return;
  await mkdir(process.env.SOLVER_SCREENSHOT_DIR, {recursive:true});
  await page.screenshot({path:path.join(process.env.SOLVER_SCREENSHOT_DIR, name+'.png'), fullPage:true});
}

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
  assert.equal(await page.locator('img').evaluate(e => e.complete && e.naturalWidth > 0), true);
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
  assert.equal(await page.locator('img').evaluate(e => getComputedStyle(e).filter), 'none');
  const downloadPromise = page.waitForEvent('download');
  await page.locator('a[download]').click();
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
  const providers = await fonts(page, '#missing-face');
  assert.ok(providers.length > 0);
  assert.ok(providers.every(f => !f.postScriptName.startsWith('Inter')));
  console.log('Separate missing-font fallback:', JSON.stringify(providers));
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
