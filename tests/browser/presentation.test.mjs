import assert from 'node:assert/strict';
import {before, after, test} from 'node:test';
import {createServer} from 'node:http';
import {readFile, mkdir} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium, webkit} from 'playwright';

// An owned loopback server, headless sandbox and fresh temporary contexts only.
// Never connect to an existing browser or fall back to a visible window.
const root = fileURLToPath(new URL('../../_site/', import.meta.url));
const evidence = JSON.parse(await readFile(new URL('../../docs/visual-example-data.json', import.meta.url)));
const originalSVG = await readFile(new URL('../../docs/blackjack-composition-example.svg', import.meta.url));
const mime = {'.html':'text/html', '.css':'text/css', '.js':'text/javascript',
  '.mjs':'text/javascript', '.json':'application/json', '.svg':'image/svg+xml', '.png':'image/png'};
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
async function capture(page, name, fullPage = true) {
  if (!process.env.SOLVER_SCREENSHOT_DIR) return;
  await mkdir(process.env.SOLVER_SCREENSHOT_DIR, {recursive:true});
  await page.screenshot({path:path.join(process.env.SOLVER_SCREENSHOT_DIR, name+'.png'), fullPage});
}

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
        if (fallback.family) assert.ok(providers.every(f => !f.postScriptName.startsWith('Inter')));
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
  assert.equal(new URL(page.url()).pathname, '/joint-split.html');
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
