// 蕉彌鐵板燒對話介面：真實 Chromium 走一輪 點單→估價→開炒→試菜→採用→上菜（後端為假資料，不用 GPU）。
const assert = require('node:assert/strict'), fs = require('node:fs'), http = require('node:http'), path = require('node:path');
const {chromium} = require('playwright');
const web = path.resolve('banana_mv/web');
const shots = process.env.TEPPAN_SHOTS;
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64');

let job = null, polls = 0, uploads = 0, presets = [];
const requests = [];
let finishCooking = false;
function makeJob(menu, seconds) {
  return {id: 'job1', title: '鐵板測試', status: 'planning_story', request: {aspect: '9:16', width: 480, sampling_steps: 6,
    image_slots: ['a1', null, null, null, null, null, null, null, null], kitchen_shared_setup: '@圖片1 是蕉彌'},
    segments: [], kitchen: {dishes: [{attempts: [{menu, seconds, clips: []}]}]}};
}
function cook() {
  const attempt = job.kitchen.dishes.at(-1).attempts.at(-1);
  if (job.status === 'running') {
    const next = job.segments[attempt.clips[1]];
    Object.assign(next, {status: 'done', preview: '/clip.mp4'});
    job.status = 'kitchen_ready';
    return;
  }
  const base = job.segments.length;
  job.segments.push({index: base, seconds: 10, status: 'done', preview: '/clip.mp4', prompt: 'subject_definitions: …'},
                    {index: base + 1, seconds: 6, status: 'rewriting'});
  // 第 1 段拍完：從畫面幫沒圖的 S6 抓了一張提示圖
  job.cast_refs = [{role: 'S6', name: '白髮老人靈魂', picture: 2, image_index: 1, source: 'frame', segment: base, sha256: 'abcdef0123'}];
  attempt.clips = [base, base + 1];
  job.status = 'running';
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
    if (url === '/api/upload') return json({id: 'a' + (++uploads)});
    if (url === '/api/film/kitchen/presets') return json(presets);
    if (url === '/api/film/kitchen/asset') { res.setHeader('Content-Type', 'image/png'); return res.end(PNG); }
    if (url === '/api/film/kitchen/preset_save') {
      const b = JSON.parse(body); presets = presets.filter(p => p.name !== b.name);
      presets.unshift({id: 'p' + presets.length, missing: [], ...b}); return json(presets);
    }
    if (url === '/api/mv/reference') { res.setHeader('Content-Type', 'image/png'); return res.end(PNG); }
    if (url === '/api/film/kitchen/start') { const b = JSON.parse(body); job = makeJob(b.kitchen_menu, b.max_seconds); polls = 0; return json(job); }
    if (url === '/api/mv/retake') { job.retakeBody = JSON.parse(body); return json(job); }
    if (url === '/api/film/kitchen/continue') { job.continueBody = JSON.parse(body); return json(job); }
    if (url === '/api/film/kitchen/cast') {
      const b = JSON.parse(body); job.castBody = b;
      job.kitchen.cast_log = [{dish: 0, action: 'replace', command: b.command, reply: '@圖片1 換成 小狐（S9）。', picture: 1, image_index: 0}];
      job.shared_setup = '<Picture 1>＝小狐＝S9'; return json(job);
    }
    if (url === '/api/film/kitchen/adopt') { job.kitchen.dishes.at(-1).selected = JSON.parse(body).attempt; return json(job); }
    if (url === '/api/film/kitchen/repeat') {
      const b = JSON.parse(body); job.kitchen.dishes.at(-1).attempts.push({menu: b.menu, seconds: b.seconds, clips: []});
      job.status = 'planning_story'; polls = 0; return json(job);
    }
    if (url === '/api/film/kitchen/serve') {
      job.kitchen.serving = true; job.status = 'done'; job.video = '/final.mp4'; return json(job);
    }
    if (url === '/api/mv/status') { if (job && ((job.status === 'planning_story' && ++polls > 1) || (job.status === 'running' && finishCooking))) cook(); return json(job); }
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
  assert.match(await page.locator('#profile').textContent(), /9:16 · 首尾幀 · 480P · 6步 · 蕉彌估/);
  await snap('1-welcome');

  // 加圖 → 出現在輸入框上方與共同設定
  const png = path.join(require('node:os').tmpdir(), 'teppan-ref.png');
  fs.writeFileSync(png, PNG);
  await page.setInputFiles('#image-picker', png);
  await page.waitForSelector('.attachment img');
  assert.equal(await page.locator('#shared-count').textContent(), '1');
  await page.click('#open-shared');
  await page.fill('#shared', '@圖片1=小巫=S1，S1=溫柔甜美女聲。');
  await page.fill('#preset-name', '異世界食堂');
  await page.click('#save-preset');
  await page.waitForSelector('.preset-load:has-text("異世界食堂")');
  assert.deepEqual(presets[0].slots, ['a1', null, null, null, null, null, null, null]);
  await snap('2-shared-sheet');
  await page.click('#sheet-shared [data-close]');

  // 重新整理＝新開一桌：載入組合後再補一位客人
  await page.reload();
  await page.click('#open-shared');
  await page.click('.preset-load:has-text("異世界食堂")');
  assert.equal(await page.inputValue('#shared'), '@圖片1=小巫=S1，S1=溫柔甜美女聲。');
  assert.equal(await page.locator('.ref-slot.filled').count(), 1);
  assert.equal(await page.locator('#save-preset').textContent(), '更新「異世界食堂」');
  await page.fill('#preset-name', '異世界食堂 第二季');
  assert.equal(await page.locator('#save-preset').textContent(), '存成新組合');
  await page.click('#sheet-shared [data-close]');
  await page.setInputFiles('#image-picker', png);
  await page.waitForFunction(() => document.getElementById('shared-count').textContent === '2');

  // 參數面板：預設值打勾
  await page.click('#open-settings');
  assert.equal(await page.locator('[data-target="seconds"] [data-value="auto"]').getAttribute('aria-checked'), 'true');
  assert.equal(await page.locator('[data-target="steps"] [data-value="6"]').getAttribute('aria-checked'), 'true');
  assert.equal(await page.locator('[data-target="mode"] [data-value="chain"]').getAttribute('aria-checked'), 'true');
  assert.equal(await page.isChecked('#cast-frames'), true);    // A 預設勾
  assert.equal(await page.isChecked('#cast-fitting'), false);  // B 預設不勾
  await page.click('[data-target="mode"] [data-value="chain5"]');   // 改成末五幀
  assert.equal(await page.locator('[data-target="mode"] [data-value="chain5"]').getAttribute('aria-checked'), 'true');
  await snap('3-settings-sheet');
  await page.click('#sheet-settings [data-close]');

  // 點單 → 估價泡泡 → 開炒
  await page.fill('#menu', '蕉大師進店點七分熟牛排，@圖片1 甩鍋噴火。');
  await page.click('#cook');
  await page.waitForSelector('text=這道我看大概 16.0 秒');
  await snap('4-estimate');
  await page.click('text=開炒');
  await page.waitForSelector('text=已出菜 1 / 2 段', {timeout: 8000});
  await page.waitForSelector('.thumbs.cast figcaption:has-text("S6 白髮老人靈魂・@圖片2")');
  assert.match(await page.locator('.thumbs.cast img').getAttribute('src'), /api\/mv\/reference\?id=job1&image=1/);
  assert.equal(await page.locator('#dish-preview-0-0 video').count(), 1);
  assert.equal(await page.locator('.tray-dish').count(), 1);
  assert.equal(await page.getByRole('button', {name: '採用', exact: true}).count(), 0);
  await page.click('.tray-dish');
  finishCooking = true;
  await page.waitForSelector('text=炒好了！', {timeout: 8000});
  assert.equal(await page.locator('#dish-preview-0-0 video').count(), 2);
  const start = JSON.parse(requests.find(([url]) => url === '/api/film/kitchen/start')[1]);
  assert.equal(start.max_seconds, 'auto');
  assert.equal(start.kitchen_shared_setup, '@圖片1=小巫=S1，S1=溫柔甜美女聲。');
  assert.deepEqual(start.image_slots.slice(0, 3), ['a1', 'a2', null]);   // 組合的圖不重傳，客人圖新上傳
  assert.equal(start.sampling_steps, 6);
  assert.equal(start.mode, 'chain5');
  assert.equal(start.auto_cast_frames, true);
  assert.equal(start.cast_fitting, false);
  await snap('5-cooked');

  // 沒熟重炒：點開提示詞、改提示詞、重炒；這段 OK 後面接著重炒
  await page.click('#dish-preview-0-0 .clip:first-child summary');
  await page.fill('#dish-preview-0-0 .clip:first-child .prompt-edit', 'subject_definitions: 改過');
  await page.locator('#dish-preview-0-0 .clip:first-child .clip-editor').scrollIntoViewIfNeeded();
  await snap('5a-clip-editor');
  await page.click('#dish-preview-0-0 .clip:first-child .btn:has-text("沒熟，重炒")');
  await new Promise(r => setTimeout(r, 300));
  assert.deepEqual(job.retakeBody, {id: 'job1', indices: [0], prompts: {0: 'subject_definitions: 改過'}});
  await page.evaluate(() => { document.querySelector('#dish-preview-0-0 .clip:first-child details').open = true; });
  await page.click('#dish-preview-0-0 .clip:first-child .btn:has-text("這段 OK，後面接著重炒")');
  await new Promise(r => setTimeout(r, 300));
  assert.deepEqual(job.continueBody, {id: 'job1', index: 0});

  // 換角：開桌後 ＋ 放新圖，打「取代@圖片1」
  assert.equal(await page.isHidden('#add-image'), false);
  await page.setInputFiles('#image-picker', png);
  await page.waitForSelector('.attachment img[alt="換角新圖"]');
  await page.fill('#menu', '取代@圖片1\n@圖片1＝小狐＝S9\n活潑清脆的少女聲線。');
  await page.click('#cook');
  await page.waitForSelector('text=@圖片1 換成 小狐（S9）。');
  assert.equal(job.castBody.command, '取代@圖片1\n@圖片1＝小狐＝S9\n活潑清脆的少女聲線。');
  assert.match(job.castBody.image, /^a\d+$/);
  await page.click('#open-shared');
  assert.equal(await page.inputValue('#shared'), '@圖片1＝小狐＝S9');
  assert.equal(await page.isHidden('#shared-save-row'), false);
  await snap('5b-cast-swap');
  await page.click('#sheet-shared [data-close]');

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
  console.log('Teppan chat checks passed: attach, save/load preset + guest image, defaults, estimate bubble, cook, clip retake, continue, cast swap, adopt tray, serve.');
})().catch(error => { console.error(error); process.exit(1); });
