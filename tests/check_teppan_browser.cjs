// 蕉彌鐵板燒對話介面：真實 Chromium 走一輪 點單→估價→開炒→試菜→採用→上菜（後端為假資料，不用 GPU）。
const assert = require('node:assert/strict'), fs = require('node:fs'), http = require('node:http'), path = require('node:path');
const {chromium} = require('playwright');
const web = path.resolve('banana_mv/web');
const shots = process.env.TEPPAN_SHOTS;
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64');

let job = null, polls = 0;
const requests = [];
function makeJob(menu, seconds) {
  return {id: 'job1', title: '鐵板測試', status: 'planning_story', request: {aspect: '9:16', width: 480, sampling_steps: 6,
    image_slots: ['a1', null, null, null, null, null, null, null, null], kitchen_shared_setup: '@圖片1 是蕉彌'},
    segments: [], kitchen: {dishes: [{attempts: [{menu, seconds, clips: []}]}]}};
}
function cook() {
  const attempt = job.kitchen.dishes.at(-1).attempts.at(-1);
  const base = job.segments.length;
  job.segments.push({index: base, seconds: 10, status: 'done', preview: '/clip.mp4', prompt: 'subject_definitions: …'},
                    {index: base + 1, seconds: 6, status: 'done', preview: '/clip.mp4', prompt: 'subject_definitions: …'});
  attempt.clips = [base, base + 1];
  job.status = 'kitchen_ready';
}
const server = http.createServer((req, res) => {
  const url = req.url.split('?')[0];
  let body = '';
  req.on('data', chunk => { body += chunk; });
  req.on('end', () => {
    const json = data => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(data)); };
    if (url.startsWith('/api/')) requests.push([url, body]);
    if (url === '/api/film/kitchen/projects') return json([]);
    if (url === '/api/film/kitchen/estimate') return json({seconds: 16, windows: [10, 6], clips: 2, render_seconds: 180, source: 'estimate', native_h3: false});
    if (url === '/api/upload') return json({id: 'a1'});
    if (url === '/api/mv/reference') { res.setHeader('Content-Type', 'image/png'); return res.end(PNG); }
    if (url === '/api/film/kitchen/start') { const b = JSON.parse(body); job = makeJob(b.kitchen_menu, b.max_seconds); polls = 0; return json(job); }
    if (url === '/api/film/kitchen/adopt') { job.kitchen.dishes.at(-1).selected = JSON.parse(body).attempt; return json(job); }
    if (url === '/api/film/kitchen/repeat') {
      const b = JSON.parse(body); job.kitchen.dishes.at(-1).attempts.push({menu: b.menu, seconds: b.seconds, clips: []});
      job.status = 'planning_story'; polls = 0; return json(job);
    }
    if (url === '/api/film/kitchen/serve') {
      job.kitchen.serving = true; job.status = 'done'; job.video = '/final.mp4'; return json(job);
    }
    if (url === '/api/mv/status') { if (job && job.status === 'planning_story' && ++polls > 1) cook(); return json(job); }
    if (url.endsWith('.mp4')) { res.writeHead(404); return res.end(); }
    const file = path.join(web, url === '/' ? 'teppan.html' : url);
    if (!file.startsWith(web + path.sep) || !fs.existsSync(file)) { res.writeHead(404); return res.end(); }
    res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html');
    res.end(fs.readFileSync(file));
  });
});

(async () => {
  await new Promise(resolve => server.listen(0, resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch();
  const page = await browser.newPage({viewport: {width: 390, height: 844}, deviceScaleFactor: 2, hasTouch: true});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const snap = async name => { if (shots) await page.screenshot({path: path.join(shots, name + '.png')}); };
  await page.goto(base + '/teppan.html');
  await page.waitForSelector('.msg.bot');
  assert.match(await page.locator('#profile').textContent(), /9:16 · 480P · 6步 · 10秒/);
  await snap('1-welcome');

  // 加圖 → 出現在輸入框上方與共同設定
  const png = path.join(require('node:os').tmpdir(), 'teppan-ref.png');
  fs.writeFileSync(png, PNG);
  await page.setInputFiles('#image-picker', png);
  await page.waitForSelector('.attachment img');
  assert.equal(await page.locator('#shared-count').textContent(), '1');
  await page.click('#open-shared');
  await page.fill('#shared', '@圖片1 是蕉彌');
  await snap('2-shared-sheet');
  await page.click('#sheet-shared [data-close]');

  // 參數面板：預設值打勾
  await page.click('#open-settings');
  assert.equal(await page.locator('[data-target="seconds"] [data-value="10"]').getAttribute('aria-checked'), 'true');
  assert.equal(await page.locator('[data-target="steps"] [data-value="6"]').getAttribute('aria-checked'), 'true');
  await snap('3-settings-sheet');
  await page.click('#sheet-settings [data-close]');

  // 點單 → 估價泡泡 → 開炒
  await page.fill('#menu', '蕉大師進店點七分熟牛排，@圖片1 甩鍋噴火。');
  await page.click('#cook');
  await page.waitForSelector('text=照你選的 10 秒');
  await snap('4-estimate');
  await page.click('text=開炒');
  await page.waitForSelector('text=炒好了！', {timeout: 8000});
  const start = JSON.parse(requests.find(([url]) => url === '/api/film/kitchen/start')[1]);
  assert.equal(start.max_seconds, 10);
  assert.equal(start.kitchen_shared_setup, '@圖片1 是蕉彌');
  assert.equal(start.sampling_steps, 6);
  await snap('5-cooked');

  // 採用 → 出菜區多一道 → 上菜
  await page.click('.msg.bot .btn.primary:has-text("採用")');
  await page.waitForSelector('.tray-dish');
  await page.waitForSelector('text=上桌了');
  await snap('6-adopted');
  await page.click('.msg.bot .btn.primary:has-text("上菜")');
  await page.waitForSelector('text=滿漢全席上桌');
  await snap('7-served');
  assert.deepEqual(errors, []);
  await browser.close();
  server.close();
  console.log('Teppan chat checks passed: attach, shared sheet, defaults, estimate bubble, cook, adopt tray, serve.');
})().catch(error => { console.error(error); process.exit(1); });
