// 蕉彌鐵板燒：對話式點單。對話紀錄由專案狀態重建，所以重新整理或換手機都能往回捲。
const $ = id => document.getElementById(id);
const storageKey = 'banana_teppan_job';
const pendingKey = 'banana_teppan_pending';
const SLOT_COUNT = 8;
const idle = new Set(['kitchen_ready', 'done', 'error', 'cancelled', 'interrupted']);
const paused = new Set(['error', 'cancelled', 'interrupted']);
let job = null, timer, pending = false, restoring = false, reactionTimer;
// 每格：null，或 {file, src, name}（剛選的圖）／{id, src, name}（素材庫裡的圖，例如組合載入的）
let localSlots = Array(SLOT_COUNT).fill(null);
let presets = [], activePreset = '';
let pendingOrder = loadPending();
let chatSignature = '';

const dishMenu = [
  ['🍗', '宮保雞丁'], ['🍲', '三杯雞'], ['🍤', '鳳梨蝦球'], ['🐟', '清蒸石斑'],
  ['🥟', '水晶蝦餃'], ['🍚', '櫻花蝦炒飯'], ['🦀', '避風塘炒蟹'], ['🍖', '糖醋排骨'],
  ['🍜', '紅燒牛肉麵'], ['🥬', '開陽白菜'], ['🍲', '佛跳牆'], ['🦑', '三杯中卷'],
  ['🥩', '黑椒牛柳'], ['🍳', '蟹黃豆腐'], ['🌶️', '麻辣鴨血'], ['🦐', '蒜蓉粉絲蝦'],
  ['🍛', '獅子頭'], ['🍱', '蒲燒鰻魚']
];

function el(tag, options = {}, children = []) {
  const node = document.createElement(tag);
  if (options.text !== undefined) node.textContent = options.text;
  if (options.className) node.className = options.className;
  for (const [key, value] of Object.entries(options.attrs || {})) node.setAttribute(key, value);
  if (options.onClick) node.addEventListener('click', options.onClick);
  for (const child of children) if (child) node.append(child);
  return node;
}
function btn(label, handle, primary = false) {
  return el('button', {text: label, className: 'btn' + (primary ? ' primary' : ''), attrs: {type: 'button'}, onClick: handle});
}
function bubble(role, children, extra = '') {
  return el('div', {className: `msg ${role} ${extra}`.trim()}, children);
}
function para(text, className) {
  return el('p', {text, className});
}
function loadPending() {
  try { return JSON.parse(localStorage.getItem(pendingKey) || 'null'); } catch { return null; }
}
function savePending() {
  try {
    if (pendingOrder) localStorage.setItem(pendingKey, JSON.stringify(pendingOrder));
    else localStorage.removeItem(pendingKey);
  } catch { /* 私密瀏覽等情況可忽略 */ }
}
function showFeedback(message) {
  $('feedback').textContent = message || '';
}

/* ---------- 伺服器 ---------- */
async function api(path, options, stage = '連線到一鍵短片') {
  let response, result;
  try {
    response = await fetch(path, options);
  } catch {
    const next = stage === '送出第一道菜' ? '。重新送出前，請先查看專案清單是否已建立' : '';
    throw Error(stage + '失敗：沒有收到一鍵短片的回應。請確認電腦服務與連線' + next + '。');
  }
  try {
    result = await response.json();
  } catch {
    throw Error(stage + '失敗：未收到可讀取的回應（HTTP ' + response.status + '）。');
  }
  if (!response.ok) throw Error(stage + '失敗：' + (result?.error || 'HTTP ' + response.status));
  return result;
}
function post(action, data, stage = '送出操作') {
  return api('api/' + action, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
  }, stage);
}

/* ---------- 參考圖 ---------- */
function imageReferences() {
  if (job) {
    let image = 0;
    return (job.request?.image_slots ?? []).flatMap((asset, index) => {
      if (!asset) return [];
      const query = new URLSearchParams({id: job.id, image: String(image++)});
      return [{slot: index + 1, src: 'api/mv/reference?' + query}];
    });
  }
  return localSlots.flatMap((item, index) => item ? [{slot: index + 1, src: item.src, name: item.name}] : []);
}
function fileSlot(file) {
  return {file, src: URL.createObjectURL(file), name: file.name};
}
function releaseSlot(item) {
  if (item?.file) URL.revokeObjectURL(item.src);
}
function clearSlots() {
  localSlots.forEach(releaseSlot);
  localSlots = Array(SLOT_COUNT).fill(null);
}
function addImages(files) {
  if (files.length) showFeedback('');
  for (const file of files) {
    const free = localSlots.indexOf(null);
    if (free < 0) {
      showFeedback('最多 8 張參考圖。');
      break;
    }
    localSlots[free] = fileSlot(file);
  }
  renderReferences();
}
function setSlot(index, file) {
  releaseSlot(localSlots[index]);
  localSlots[index] = file ? fileSlot(file) : null;
  renderReferences();
}
function renderReferences() {
  const refs = imageReferences();
  $('shared-count').textContent = String(refs.length);
  const attachments = $('attachments');
  attachments.replaceChildren(...refs.map(ref => el('div', {className: 'attachment'}, [
    el('img', {attrs: {src: ref.src, alt: '圖片' + ref.slot}}), el('span', {text: '圖片' + ref.slot})
  ])));
  attachments.hidden = Boolean(job) || !refs.length;
  const grid = $('references');
  const bySlot = new Map(refs.map(ref => [ref.slot, ref]));
  grid.replaceChildren();
  for (let slot = 1; slot <= SLOT_COUNT; slot++) {
    const ref = bySlot.get(slot);
    const cell = el('div', {className: 'ref-cell'});
    const tile = el('button', {
      className: 'ref-slot' + (ref ? ' filled' : ''),
      attrs: {type: 'button', 'aria-label': ref ? `圖片${slot}，點一下換圖` : `圖片${slot}，空格，點一下加圖`}
    });
    if (ref) tile.append(el('img', {attrs: {src: ref.src, alt: ''}}), el('span', {className: 'ref-label', text: '圖片' + slot}));
    else tile.append(el('span', {text: '＋'}), el('span', {text: '圖片' + slot}));
    if (job) tile.disabled = true;
    else tile.onclick = () => pickInto(slot - 1);
    cell.append(tile);
    if (ref && !job) {
      const clear = el('button', {className: 'ref-clear', text: '✕', attrs: {type: 'button', 'aria-label': `清除圖片${slot}`}});
      clear.onclick = () => setSlot(slot - 1, null);
      cell.append(clear);
    }
    grid.append(cell);
  }
  $('refs-locked').hidden = !job;
}
// 只用一個固定掛在頁面上的選檔元件：手機開相簿要好幾秒，臨時建立的元件可能被回收，選完圖就沒反應。
let pickTarget = null;
function openPicker(index = null) {
  const picker = $('image-picker');
  pickTarget = index;
  picker.multiple = index === null;
  picker.value = '';
  picker.click();
}
function pickInto(index) {
  openPicker(index);
}
function takePicked() {
  const picker = $('image-picker');
  const files = [...picker.files];
  if (!files.length) return;
  const images = files.filter(file => /^image\/(png|jpeg|webp)$/i.test(file.type) || /\.(png|jpe?g|webp)$/i.test(file.name));
  if (images.length < files.length) showFeedback('只支援 PNG、JPG、WebP 圖片；其他格式已略過。');
  if (pickTarget !== null && images[0]) setSlot(pickTarget, images[0]);
  else addImages(images);
  pickTarget = null;
  picker.value = '';
}
$('add-image').onclick = () => openPicker();
$('image-picker').addEventListener('change', takePicked);
$('image-picker').addEventListener('input', takePicked);

/* ---------- @ 選圖 ---------- */
function bindImageMentions(field, fieldLabel) {
  const input = $(field);
  const suggestions = $(field + '-image-suggestions');
  const list = $(field + '-image-list');
  const empty = $(field + '-image-empty');
  const add = $(field + '-image-add');
  let mention = null, composing = false;
  function close() {
    mention = null;
    suggestions.hidden = true;
    input.removeAttribute('aria-activedescendant');
  }
  function select(index, scroll = false) {
    const rows = [...list.children];
    mention.index = index;
    rows.forEach((row, i) => row.setAttribute('aria-selected', String(i === index)));
    if (!rows[index]) return input.removeAttribute('aria-activedescendant');
    input.setAttribute('aria-activedescendant', rows[index].id);
    if (scroll) rows[index].scrollIntoView({block: 'nearest'});
  }
  function insert(slot) {
    if (!mention) return;
    const {start, end} = mention;
    const text = '@圖片' + slot + (/\s/.test(input.value[end] ?? '') ? '' : ' ');
    if (input.value.length - (end - start) + text.length > input.maxLength) return showFeedback(fieldLabel + '已達字數上限。');
    input.setRangeText(text, start, end, 'end');
    close();
    input.focus({preventScroll: true});
    input.dispatchEvent(new Event('input'));
  }
  function update() {
    if (composing || input.disabled || input.selectionStart !== input.selectionEnd) return close();
    const end = input.selectionStart;
    const before = input.value.slice(0, end);
    const match = /[@＠](?:圖片?|图片?|image)?([1-8])?$/i.exec(before);
    if (!match || (match.index > 0 && /[a-z0-9_.]/i.test(before[match.index - 1]))) return close();
    const images = imageReferences();
    const matches = images.filter(ref => !match[1] || ref.slot === Number(match[1]));
    mention = {start: match.index, end, index: 0};
    list.replaceChildren(...matches.map(ref => {
      const option = el('button', {className: 'menu-image-option', attrs: {
        type: 'button', id: field + '-ref-' + ref.slot, role: 'option', tabindex: '-1'}});
      option.onpointerdown = event => event.preventDefault();
      option.onclick = () => insert(ref.slot);
      const label = el('span', {text: '@圖片' + ref.slot});
      if (ref.name) label.append(el('small', {text: ref.name}));
      option.append(el('img', {attrs: {src: ref.src, alt: ''}}), label);
      return option;
    }));
    empty.hidden = matches.length > 0;
    empty.textContent = images.length ? '找不到這個圖號。' : '這桌還沒有參考圖。';
    add.hidden = Boolean(job) || images.length > 0;
    suggestions.hidden = false;
    select(0);
  }
  input.addEventListener('input', event => { if (!event.isComposing) update(); });
  input.addEventListener('click', update);
  input.addEventListener('compositionstart', () => { composing = true; close(); });
  input.addEventListener('compositionend', () => { composing = false; update(); });
  input.addEventListener('blur', event => { if (!suggestions.contains(event.relatedTarget)) close(); });
  input.addEventListener('keydown', event => {
    if (composing || event.isComposing || !mention) return;
    const rows = list.children;
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
    } else if (rows.length && ['ArrowUp', 'ArrowDown', 'Enter'].includes(event.key)) {
      event.preventDefault();
      if (event.key === 'Enter') rows[mention.index].click();
      else select((mention.index + (event.key === 'ArrowUp' ? -1 : 1) + rows.length) % rows.length, true);
    }
  });
  add.onclick = () => { close(); openPicker(); };
  return close;
}
const closeMenuMention = bindImageMentions('menu', '菜單');
const closeSharedMention = bindImageMentions('shared', '共同設定');

/* ---------- 底部面板與參數 ---------- */
function openSheet(id) {
  closeMenuMention();
  for (const sheet of document.querySelectorAll('.sheet')) sheet.hidden = sheet.id !== id;
  $('sheet-backdrop').hidden = false;
  $(id).querySelector('button')?.focus();
}
function closeSheets() {
  closeSharedMention();
  for (const sheet of document.querySelectorAll('.sheet')) sheet.hidden = true;
  $('sheet-backdrop').hidden = true;
  render();
}
$('open-settings').onclick = () => openSheet('sheet-settings');
$('open-shared').onclick = () => { renderReferences(); renderPresets(); fetchPresets(); openSheet('sheet-shared'); };
$('sheet-backdrop').onclick = closeSheets;
for (const close of document.querySelectorAll('[data-close]')) close.onclick = closeSheets;
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && !$('sheet-backdrop').hidden) closeSheets();
});
for (const group of document.querySelectorAll('.pills')) {
  const target = $(group.dataset.target);
  for (const option of group.querySelectorAll('button')) {
    option.setAttribute('role', 'radio');
    option.onclick = () => {
      target.value = option.dataset.value;
      syncPills();
      scheduleEstimate();
      render();
    };
  }
}
function syncPills() {
  for (const group of document.querySelectorAll('.pills')) {
    const value = $(group.dataset.target).value;
    for (const option of group.querySelectorAll('button')) {
      option.setAttribute('aria-checked', String(option.dataset.value === value));
    }
  }
}
function dishSeconds() {
  const value = $('seconds').value;
  return value === 'auto' ? 'auto' : Number(value);
}
function profileText() {
  const request = job?.request;
  const aspect = request?.aspect ?? $('aspect').value;
  const resolution = request ? (request.width > 854 || (request.aspect !== '16:9' && request.width > 480) ? '720' : '480')
    : $('resolution').value;
  const steps = request?.sampling_steps ?? $('steps').value;
  const seconds = $('seconds').value === 'auto' ? '蕉彌估' : $('seconds').value + '秒';
  const link = (request?.mode ?? $('mode').value) === 'chain5' ? '末五幀' : '首尾幀';
  return `${aspect} · ${link} · ${resolution}P · ${steps}步 · ${seconds}`;
}

/* ---------- 估價 ---------- */
function clipWindows(total, cap = 10) {
  const minimum = 124 / 24;
  total = Math.max(total, minimum);
  const count = Math.max(1, Math.ceil(total / cap - 1e-9));
  if (count === 1) return [Math.min(total, cap)];
  const tail = total - (count - 1) * cap;
  if (tail >= minimum) return [...Array(count - 1).fill(cap), tail];
  if (tail < 1.5) return Array(count - 1).fill(cap);
  return [...Array(count - 2).fill(cap), (cap + tail) / 2, (cap + tail) / 2];
}
function formatWait(seconds) {
  const minutes = Math.max(1, Math.ceil(seconds / 60));
  return minutes >= 60 ? Math.floor(minutes / 60) + ' 小時 ' + (minutes % 60) + ' 分' : minutes + ' 分鐘';
}
function describeEstimate(result, chosen) {
  if (result.native_h3) {
    return `老闆，這是 H3 全咒，照你寫的 ${result.clips} 段（${result.windows.map(w => w.toFixed(1)).join('／')} 秒）直接上鐵板，不經 9B 改寫，約 ${formatWait(result.render_seconds)}出菜。`;
  }
  if (chosen === 'auto') {
    const lead = {declared: '照菜單寫的全片長度', timecode: '照菜單時間碼'}[result.source] || '這道我看大概';
    return `老闆，${lead} ${result.seconds.toFixed(1)} 秒，切 ${result.clips} 段（${result.windows.map(w => w.toFixed(1)).join('／')} 秒），約 ${formatWait(result.render_seconds)}出菜。`;
  }
  const windows = clipWindows(chosen);
  return `老闆，這道照你選的 ${chosen} 秒，切 ${windows.length} 段（${windows.map(w => w.toFixed(1)).join('／')} 秒），約 ${formatWait(windows.length * 90)}出菜。我估這份菜單大概要 ${result.seconds.toFixed(0)} 秒。`;
}
let estimateTimer, estimateSerial = 0;
function scheduleEstimate() {
  clearTimeout(estimateTimer);
  const menu = $('menu').value.trim();
  if (!menu || $('menu').disabled) {
    $('estimate').hidden = true;
    return;
  }
  estimateTimer = setTimeout(async () => {
    const serial = ++estimateSerial;
    try {
      const result = await post('film/kitchen/estimate', {menu}, '蕉彌估價');
      if (serial !== estimateSerial || $('menu').value.trim() !== menu) return;
      $('estimate').textContent = describeEstimate(result, dishSeconds());
      $('estimate').hidden = false;
    } catch {
      if (serial === estimateSerial) $('estimate').hidden = true;
    }
  }, 450);
}
$('menu').addEventListener('input', () => { scheduleEstimate(); autoGrow(); });
function autoGrow() {
  const menu = $('menu');
  menu.style.height = 'auto';
  menu.style.height = Math.min(menu.scrollHeight, window.innerHeight * 0.4) + 'px';
}

/* ---------- 對話 ---------- */
function latestDish() {
  return job?.kitchen?.dishes.at(-1);
}
function nextAction() {
  if (!job) return 'start';
  const dish = latestDish();
  return dish && dish.selected === undefined ? 'repeat' : 'append';
}
function canOrder() {
  if (pending || restoring) return false;
  if (!job) return true;
  const status = job.status;
  if (job.kitchen?.serving || status === 'done') return false;
  return status === 'kitchen_ready' || paused.has(status);
}
function dishTitle(index) {
  return dishMenu[index % dishMenu.length];
}
function videoNode(src) {
  const node = el('video', {attrs: {controls: '', playsinline: '', preload: 'metadata'}});
  node.src = src;
  return node;
}
function previewable(clip) {
  return clip?.status === 'done' && Boolean(clip.preview);
}
function workingText() {
  const status = job.status;
  const clips = latestDish()?.attempts.at(-1).clips ?? [];
  const done = clips.filter(index => job.segments[index]?.status === 'done').length;
  if (status === 'planning_story') return '蕉彌正在讀菜單、分配每段要演什麼…';
  if (status === 'running') return `蕉彌正在炒菜，${done} / ${clips.length} 段完成。`;
  return '蕉彌正在準備鐵板…';
}
function buildMessages() {
  const nodes = [];
  nodes.push(bubble('bot', [para(job
    ? '老闆歡迎回來！往上捲可以看這桌的點單紀錄。'
    : '老闆歡迎光臨！先按 ＋ 丟角色圖，或直接跟我說想拍什麼。秒數、比例這些在下面的參數可以改。')]));
  if (job) {
    const dishes = job.kitchen?.dishes ?? [];
    const working = !idle.has(job.status);
    dishes.forEach((dish, d) => {
      const [icon, fallback] = dishTitle(d);
      const lastDish = d === dishes.length - 1;
      dish.attempts.forEach((attempt, v) => {
        const lastAttempt = v === dish.attempts.length - 1;
        const user = bubble('user', [], '');
        if (d === 0 && v === 0) {
          const refs = imageReferences();
          if (refs.length) user.append(el('div', {className: 'thumbs'}, refs.map(ref =>
            el('img', {attrs: {src: ref.src, alt: '圖片' + ref.slot}}))));
        }
        user.append(el('span', {className: 'tag', text: `第 ${d + 1} 道` + (v ? `・重炒第 ${v + 1} 版` : '') +
          (attempt.estimated ? '・蕉彌估秒' : `・${attempt.seconds} 秒`)}), para(attempt.menu));
        if (lastAttempt && v === 0) user.id = 'dish-' + d;
        nodes.push(user);

        const clips = attempt.clips.map(index => job.segments[index]);
        const previews = clips.flatMap((clip, i) => previewable(clip) ? [{clip, i}] : []);
        const ready = previews.length > 0 && previews.length === clips.length;
        const accepted = dish.selected === v;
        const canChoose = lastDish && dish.selected === undefined && job.status === 'kitchen_ready';
        if (previews.length) {
          const total = clips.reduce((sum, clip) => sum + (clip.seconds || 0), 0);
          const head = !ready ? `已出菜 ${previews.length} / ${clips.length} 段，可以先試看：`
            : accepted ? `${icon} 已採用這版「${fallback}」`
            : dish.selected !== undefined ? '這版沒有採用。'
            : `炒好了！${clips.length} 段、共 ${total.toFixed(1)} 秒` + (attempt.native_h3 ? '（H3 全咒直上）' : '') + '，先試試看：';
          const grid = el('div', {className: 'clips'}, previews.map(({clip, i}) => {
            const box = el('div', {className: 'clip'}, [videoNode(clip.preview), el('span', {className: 'meta', text: `片段 ${i + 1} · ${clip.seconds.toFixed(1)} 秒`})]);
            if (clip.prompt) box.append(el('details', {}, [el('summary', {text: 'H3 提示詞'}), el('pre', {text: clip.prompt})]));
            return box;
          }));
          const children = [para(head), grid];
          if (ready && canChoose && lastAttempt) {
            children.push(el('div', {className: 'actions'}, [
              btn('採用', () => perform('adopt', {attempt: v}), true),
              btn('重炒', () => perform('repeat', {menu: attempt.menu, seconds: attempt.estimated ? 'auto' : attempt.seconds})),
              btn('改菜單再炒', () => editMenu(attempt))
            ]));
          } else if (ready && canChoose) {
            children.push(el('div', {className: 'actions'}, [btn('採用這版', () => perform('adopt', {attempt: v}))]));
          }
          const preview = bubble('bot', children, 'wide');
          preview.id = `dish-preview-${d}-${v}`;
          nodes.push(preview);
        }
        if (!ready && lastDish && lastAttempt && working && !job.kitchen?.serving) {
          nodes.push(bubble('bot', [el('span', {className: 'typing', attrs: {'aria-hidden': 'true'}}, [el('i'), el('i'), el('i')]),
            para(workingText())]));
        } else if (!ready && lastDish && lastAttempt && paused.has(job.status) && !job.kitchen?.serving) {
          nodes.push(bubble('bot', [
            para(job.status === 'error' ? '鐵板出了點狀況，完成的毛片都保存了。' : '已停爐，完成的毛片都保存了。'),
            job.error ? para(job.error, 'meta') : null,
            el('div', {className: 'actions'}, [
              btn('繼續製作', () => perform('resume'), true),
              btn('改菜單再炒', () => editMenu(attempt))
            ])
          ], 'error'));
        } else if (!previews.length) {
          nodes.push(bubble('bot', [para('這版沒有炒完。')]));
        }
      });
    });
    const dish = latestDish();
    if (job.status === 'kitchen_ready' && dish?.selected !== undefined && !job.kitchen?.serving) {
      nodes.push(bubble('bot', [
        para(`第 ${dishes.length} 道上桌了！直接跟我說下一道想拍什麼，或現在上菜合成` +
          ($('upscale').checked ? '（會升頻 2K）。' : '。')),
        el('div', {className: 'actions'}, [btn('上菜', () => perform('serve', {upscale: $('upscale').checked}), true)])
      ]));
    }
    if (job.kitchen?.serving && !job.video) {
      if (working) nodes.push(bubble('bot', [el('span', {className: 'typing', attrs: {'aria-hidden': 'true'}}, [el('i'), el('i'), el('i')]),
        para(job.status === 'upscaling_1080p' ? '蕉彌正在大火收汁，升頻 2K 中…' : '蕉彌正在上菜，合成整部片中…')]));
      else if (paused.has(job.status)) nodes.push(bubble('bot', [para('上菜時出了狀況。'), job.error ? para(job.error, 'meta') : null,
        el('div', {className: 'actions'}, [btn('繼續上菜', () => perform('resume'), true)])], 'error'));
    }
    if (job.video) {
      const upscale = job.final_versions?.findLast(row => row.reason === 'upscale_1440p');
      const src = upscale?.download || job.video;
      const links = [el('a', {className: 'btn primary', text: upscale ? '下載 2K 成片' : '下載成片',
        attrs: {href: src, download: (job.title || 'BananaFilm') + '.mp4'}})];
      if (upscale) links.push(el('a', {className: 'btn', text: '下載原尺寸母片', attrs: {href: job.video, download: (job.title || 'BananaFilm') + '-母片.mp4'}}));
      nodes.push(bubble('bot', [para('滿漢全席上桌！整部片在這裡：'), videoNode(src), el('div', {className: 'actions'}, links),
        job.upscale_error ? para('2K 升頻未完成，母片可下載。' + job.upscale_error, 'meta') : null], 'wide final'));
    }
  }
  if (pendingOrder && (!job || canOrder())) {
    nodes.push(bubble('user', [el('span', {className: 'tag', text: pendingOrder.hung ? '掛單中' : '點單'}), para(pendingOrder.menu)]));
    const actions = el('div', {className: 'actions'}, [
      btn('開炒', () => cookPending(), true),
      pendingOrder.hung ? null : btn('掛單', () => { pendingOrder.hung = true; savePending(); render(); }),
      btn('收回改一下', () => { $('menu').value = pendingOrder.menu; pendingOrder = null; savePending(); autoGrow(); scheduleEstimate(); render(); $('menu').focus(); })
    ]);
    nodes.push(bubble('bot', [para(pendingOrder.hung ? '好，先掛單，鐵板不開火。想好了按開炒。' : (pendingOrder.estimate || '蕉彌估價中…')), actions]));
  }
  return nodes;
}
function renderChat() {
  const status = job?.status;
  const dishes = job?.kitchen?.dishes ?? [];
  const signature = JSON.stringify([job?.id, status, job?.error, job?.video, job?.final_versions?.length, job?.kitchen,
    dishes.map(dish => dish.attempts.map(a => a.clips.map(i => [job.segments[i]?.preview, job.segments[i]?.status, Boolean(job.segments[i]?.prompt)]))),
    pendingOrder, Boolean(job) && workingText(), $('upscale').checked, imageReferences().length]);
  if (signature === chatSignature) return;
  const chat = $('chat');
  const nearBottom = chat.scrollHeight - chat.scrollTop - chat.clientHeight < 160;
  const playing = [...$('messages').querySelectorAll('video')].some(video => !video.paused);
  if (playing && !idle.has(status ?? 'kitchen_ready')) return;   // 正在看毛片時不打斷，下一輪再更新
  chatSignature = signature;
  $('messages').replaceChildren(...buildMessages());
  if (nearBottom) chat.scrollTop = chat.scrollHeight;
}
function renderTray() {
  const dishes = job?.kitchen?.dishes ?? [];
  const available = dishes.flatMap((dish, d) => {
    const v = dish.selected ?? dish.attempts.findLastIndex(attempt =>
      attempt.clips.some(i => previewable(job.segments[i])));
    return v < 0 ? [] : [{d, v}];
  });
  $('tray-dishes').replaceChildren(...available.map(({d, v}) => {
    const [icon, name] = dishTitle(d);
    return el('button', {className: 'tray-dish', text: icon, attrs: {type: 'button', 'aria-label': `第 ${d + 1} 道 ${name}，跳到試菜預覽`},
      onClick: () => ($(`dish-preview-${d}-${v}`) ?? $('dish-' + d))
        ?.scrollIntoView({behavior: 'smooth', block: 'start'})});
  }));
  $('tray-empty').hidden = available.length > 0;
}
function renderComfyProgress(status, segment) {
  const panel = $('comfy-progress');
  panel.hidden = !['planning_story', 'running'].includes(status);
  if (panel.hidden) return;
  const task = job.comfy_progress;
  const writing = task?.node === 'TextGenerate';
  const sampling = ['SamplerCustomAdvanced', 'KSampler', 'KSamplerAdvanced'].includes(task?.node);
  const measured = task?.state === 'running' && (writing || sampling) && Number.isInteger(task.value) &&
    Number.isInteger(task.max) && task.max > 0 && task.value >= 0 && task.value <= task.max;
  let label = status === 'planning_story' ? '9B 規劃菜單' : segment?.status === 'rewriting' ? '9B 撰寫分鏡' : 'H3 影片生成';
  if (task?.state === 'queued') label += ' · 排隊中';
  else if (task?.state === 'finished') label = '正在整理生成結果';
  else if (task?.state === 'failed') label = 'ComfyUI 回報錯誤';
  else if (task?.state === 'interrupted') label = 'ComfyUI 已中斷';
  else if (sampling) label = 'H3 影片採樣';
  else if (/VAEDecode/i.test(task?.node ?? '')) label = 'H3 解碼影片';
  if (measured) label += ' · ' + task.value + ' / ' + task.max + (writing ? ' tokens' : ' 步');
  if (measured && sampling && task.value < task.max && Number.isFinite(task.seconds_per_unit) && task.seconds_per_unit > 0) {
    label += ' · 約 ' + Math.ceil((task.max - task.value) * task.seconds_per_unit) + ' 秒';
  }
  if ($('comfy-stage').textContent !== label) $('comfy-stage').textContent = label;
  const bar = $('comfy-count');
  bar.hidden = !measured;
  if (measured) { bar.max = task.max; bar.value = task.value; }
}
function render() {
  const status = job?.status;
  const working = pending || restoring || (Boolean(status) && !idle.has(status));
  const dish = latestDish();
  const clips = dish?.attempts.at(-1).clips ?? [];
  const count = clips.filter(index => job.segments[index]?.status === 'done').length;
  const segment = job?.segments?.[job.current - 1];
  const rewriting = segment?.status === 'rewriting';
  $('counter').dataset.phase = status === 'running' && !rewriting ? 'cooking' :
    status === 'upscaling_1080p' ? 'finishing' : status === 'assembling' ? 'serving' : working ? 'planning' : 'idle';
  $('project-title').hidden = !job;
  $('project-title').textContent = job?.title ?? '';
  const messages = {
    planning_story: '蕉彌正在讀菜單…', running: (rewriting ? '備料中 · ' : '炒菜中 · ') + count + ' / ' + clips.length + ' 段',
    kitchen_ready: dish?.selected !== undefined ? '可以點下一道或上菜' : '炒好了，等你試菜',
    assembling: '上菜中・合成影片', upscaling_1080p: '升頻 2K 中', done: '上菜完成',
    error: '製作暫停', cancelled: '已停爐', interrupted: '製作中斷'
  };
  $('status').textContent = messages[status] || (working ? '準備鐵板中…' : '鐵板就位');
  $('progress').hidden = status !== 'running' || !clips.length;
  $('progress').max = clips.length || 1;
  $('progress').value = count;
  renderComfyProgress(status, segment);

  const orderable = canOrder() && !(pendingOrder && !pendingOrder.hung);
  $('menu').disabled = !orderable;
  $('cook').disabled = !orderable;
  $('menu').placeholder = !job ? '跟蕉彌說你想拍什麼…輸入 @ 選圖'
    : status === 'done' ? '這桌已上菜，按右上「新開一桌」再點'
    : !canOrder() ? '蕉彌忙著，等這道炒完…'
    : nextAction() === 'repeat' ? '不滿意？直接寫新菜單重炒這道…' : '下一道想拍什麼？';
  if ($('menu').disabled) closeMenuMention();
  $('add-image').hidden = Boolean(job);
  $('stop').hidden = !job || idle.has(status);
  $('stop').disabled = pending;
  $('new-project').hidden = !job || working;
  $('restore-wrap').hidden = Boolean(job) || $('restore-project').options.length <= 1;
  $('profile').textContent = profileText();
  $('sheet-settings').classList.toggle('locked', Boolean(job));
  $('settings-locked').hidden = !job;
  $('shared').disabled = Boolean(job);
  if (job) $('shared').value = job.request?.kitchen_shared_setup ?? '';
  renderReferences();
  renderPresets();
  renderChat();
  renderTray();
}

/* ---------- 動作 ---------- */
function editMenu(attempt) {
  $('menu').value = attempt.menu;
  $('seconds').value = attempt.estimated ? 'auto' : String(attempt.seconds);
  syncPills();
  autoGrow();
  scheduleEstimate();
  render();
  $('menu').focus();
}
async function placeOrder(menu) {
  pendingOrder = {menu, seconds: dishSeconds(), action: nextAction(), hung: false, estimate: ''};
  savePending();
  clearTimeout(estimateTimer);
  estimateSerial++;
  $('menu').value = '';
  $('estimate').hidden = true;
  autoGrow();
  render();
  try {
    const result = await post('film/kitchen/estimate', {menu}, '蕉彌估價');
    if (pendingOrder?.menu === menu) {
      pendingOrder.estimate = describeEstimate(result, pendingOrder.seconds);
      savePending();
    }
  } catch (error) {
    if (pendingOrder?.menu === menu) pendingOrder.estimate = '老闆，我估不出來（' + error.message + '），可以直接開炒。';
  }
  render();
}
async function cookPending() {
  if (!pendingOrder) return;
  const order = pendingOrder;
  const action = !job ? 'start' : nextAction();
  const ok = await perform(action, {menu: order.menu, seconds: order.seconds});
  if (ok) {
    pendingOrder = null;
    savePending();
    render();
  }
}
async function perform(action, fields = {}) {
  if (pending || restoring) return false;
  pending = true;
  showFeedback('');
  render();
  try {
    let updated;
    if (action === 'start') {
      const request = await firstRequest(fields.menu, fields.seconds);
      showFeedback('正在送出第一道菜…');
      updated = await post('film/kitchen/start', request, '送出第一道菜');
    } else if (['stop', 'resume'].includes(action)) {
      updated = await post('mv/' + action, {id: job.id});
    } else {
      updated = await post('film/kitchen/' + action, {id: job.id, ...fields});
    }
    if (action === 'repeat') {
      clearTimeout(reactionTimer);
      $('counter').classList.add('is-surprised');
      reactionTimer = setTimeout(() => $('counter').classList.remove('is-surprised'), 820);
    }
    const id = action === 'start' ? updated.id : job.id;
    if (updated.kitchen) {
      job = updated;
      localStorage.setItem(storageKey, id);
    }
    showFeedback('');
    await sync(id);
    $('chat').scrollTop = $('chat').scrollHeight;
    return true;
  } catch (error) {
    showFeedback(error.message);
    return false;
  } finally {
    pending = false;
    render();
  }
}
async function firstRequest(menu, seconds) {
  const shared = $('shared').value.trim();
  const prompt = [shared, menu].filter(Boolean).join('\n\n');
  if (Array.from(prompt).length > 30000) throw Error('共同設定和菜單合計最多 30000 字。');
  const slots = await uploadSlots(showFeedback);
  slots.push(null);
  const aspect = $('aspect').value, resolution = Number($('resolution').value);
  return {
    project_name: $('name').value.trim(), prompt, image_slots: slots,
    kitchen_menu: menu, kitchen_shared_setup: shared,
    max_seconds: seconds, duration_preference: 'selector',
    segment_seconds: 10, mode: $('mode').value === 'chain5' ? 'chain5' : 'chain', sound_mode: $('sound').value, aspect,
    width: aspect === '16:9' ? (resolution === 480 ? 854 : 1280) : resolution,
    sampling_steps: Number($('steps').value), rewriter_thinking: $('thinking').checked,
    kitchen_attention: true, sparse_attention: false, motion_lora: false
  };
}
// 把還沒上傳的圖送到電腦的素材庫，回傳 8 格圖片編號（空格為 null）。上傳過的會記住編號，不重傳。
async function uploadSlots(report) {
  const ids = [];
  for (let index = 0; index < SLOT_COUNT; index++) {
    const item = localSlots[index];
    if (!item) { ids.push(null); continue; }
    if (!item.id) {
      const reference = '@圖片' + (index + 1);
      const stage = '上傳 ' + reference;
      report('正在' + stage + '…');
      if (item.file.size > 256 * 1024 * 1024) throw Error(reference + ' 超過單檔上限 256 MiB。');
      let bytes;
      try { bytes = await item.file.arrayBuffer(); } catch { throw Error('無法讀取 ' + reference + '，請重新選擇圖片。'); }
      if (!bytes.byteLength) throw Error(reference + ' 是空檔案，請重新選擇圖片。');
      const asset = await api('api/upload', {
        method: 'POST', headers: {'X-Filename': encodeURIComponent(item.file.name)}, body: bytes
      }, stage);
      if (!asset?.id) throw Error(stage + '失敗：伺服器未回傳圖片編號。');
      item.id = asset.id;
    }
    ids.push(item.id);
  }
  report('');
  return ids;
}

/* ---------- 共同設定組合 ---------- */
function presetFeedback(message) {
  $('preset-feedback').textContent = message || '';
}
async function fetchPresets() {
  try {
    presets = await api('api/film/kitchen/presets', undefined, '讀取組合');
  } catch (error) {
    presetFeedback(error.message);
  }
  renderPresets();
}
function renderPresets() {
  const list = $('preset-list');
  list.replaceChildren(...presets.map(preset => {
    const count = (preset.slots || []).filter(Boolean).length;
    const load = el('button', {className: 'preset-load', attrs: {type: 'button'}}, [
      document.createTextNode(preset.name),
      el('small', {text: `${count} 張圖` + (preset.missing?.length ? `・缺圖片${preset.missing.join('、')}` : '')})
    ]);
    load.disabled = Boolean(job);
    load.onclick = () => loadPreset(preset);
    const remove = el('button', {className: 'preset-delete', text: '✕', attrs: {type: 'button', 'aria-label': `刪除組合「${preset.name}」`}});
    remove.onclick = async () => {
      if (!remove.classList.contains('confirm')) {
        remove.classList.add('confirm');
        remove.textContent = '確定刪除？';
        setTimeout(() => { remove.classList.remove('confirm'); remove.textContent = '✕'; }, 3000);
        return;
      }
      try {
        presets = await post('film/kitchen/preset_delete', {id: preset.id}, '刪除組合');
        presetFeedback(`已刪除「${preset.name}」。`);
      } catch (error) {
        presetFeedback(error.message);
      }
      renderPresets();
    };
    return el('div', {className: 'preset' + (preset.name === activePreset ? ' active' : '')}, [load, remove]);
  }));
  $('preset-empty').hidden = presets.length > 0;
  updateSaveLabel();
}
function updateSaveLabel() {
  const name = $('preset-name').value.trim();
  const existing = presets.some(preset => preset.name === name);
  $('save-preset').textContent = existing ? `更新「${name}」` : '存成新組合';
}
function loadPreset(preset) {
  if (job) return;
  clearSlots();
  const missing = new Set(preset.missing || []);
  localSlots = (preset.slots || []).slice(0, SLOT_COUNT).map((id, index) => id && !missing.has(index + 1)
    ? {id, src: 'api/film/kitchen/asset?id=' + encodeURIComponent(id), name: `${preset.name} 圖片${index + 1}`} : null);
  while (localSlots.length < SLOT_COUNT) localSlots.push(null);
  $('shared').value = preset.shared || '';
  $('preset-name').value = preset.name;
  activePreset = preset.name;
  presetFeedback(`已載入「${preset.name}」` + (missing.size ? `，但圖片${[...missing].join('、')} 已不在素材庫，請補上。` : '。可以按 ＋ 補這次的客人。'));
  renderPresets();
  render();
}
async function savePreset() {
  const name = $('preset-name').value.trim();
  if (!name) {
    presetFeedback('先幫這個組合取個名字。');
    $('preset-name').focus();
    return;
  }
  $('save-preset').disabled = true;
  try {
    const slots = job ? (job.request?.image_slots ?? []).slice(0, SLOT_COUNT) : await uploadSlots(presetFeedback);
    while (slots.length < SLOT_COUNT) slots.push(null);
    const shared = job ? (job.request?.kitchen_shared_setup ?? '') : $('shared').value;
    const replacing = presets.some(preset => preset.name === name);
    presets = await post('film/kitchen/preset_save', {name, shared, slots}, '儲存組合');
    activePreset = name;
    presetFeedback(replacing ? `已更新組合「${name}」。` : `已存成組合「${name}」，下次新開一桌就能載入。`);
  } catch (error) {
    presetFeedback(error.message);
  } finally {
    $('save-preset').disabled = false;
    renderPresets();
  }
}
$('save-preset').onclick = savePreset;
$('preset-name').addEventListener('input', updateSaveLabel);
$('preset-name').addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.isComposing) { event.preventDefault(); savePreset(); }
});

async function sync(id) {
  clearTimeout(timer);
  try {
    const result = await api('api/mv/status?id=' + encodeURIComponent(id));
    if (!result.kitchen) throw Error('這個專案不屬於蕉彌鐵板燒。');
    job = result;
    localStorage.setItem(storageKey, id);
    if (!idle.has(result.status)) timer = setTimeout(() => sync(id), 1600);
  } catch (error) {
    showFeedback(error.message);
    if (job?.id === id && !idle.has(job.status)) timer = setTimeout(() => sync(id), 5000);
  } finally {
    restoring = false;
    render();
  }
}
async function projects() {
  try {
    const rows = await api('api/film/kitchen/projects');
    const select = $('restore-project');
    select.replaceChildren(new Option('選擇專案', ''));
    for (const row of rows) select.add(new Option(row.title, row.id));
  } catch (error) {
    if (!job) showFeedback(error.message);
  }
  render();
}

$('menu-form').onsubmit = event => {
  event.preventDefault();
  const menu = $('menu').value.trim();
  if (!menu || !canOrder()) return;
  placeOrder(menu);
};
$('menu').addEventListener('keydown', event => {
  // 電腦上 Enter 送出、Shift+Enter 換行；手機輸入法照常換行。
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && matchMedia('(pointer: fine)').matches &&
      $('menu-image-suggestions').hidden) {
    event.preventDefault();
    $('menu-form').requestSubmit();
  }
});
$('stop').onclick = () => perform('stop');
$('upscale').onchange = render;
$('restore-project').onchange = () => {
  const id = $('restore-project').value;
  if (id && !pending && !restoring && !job) {
    restoring = true;
    render();
    sync(id);
  }
};
$('new-project').onclick = () => {
  clearTimeout(timer);
  localStorage.removeItem(storageKey);
  job = null;
  pendingOrder = null;
  savePending();
  clearSlots();
  activePreset = '';
  presetFeedback('');
  $('menu').value = '';
  $('shared').value = '';
  chatSignature = '';
  showFeedback('');
  render();
  projects();
};

// 執行環境預設（Colab：720P、沒有 2K 升頻；5070：照網頁原本的 480P＋升頻）。
async function applyProfileDefaults() {
  let defaults;
  try { defaults = await (await fetch('api/film/defaults', {cache: 'no-store'})).json(); } catch { return; }
  if (!defaults || typeof defaults !== 'object') return;
  if (defaults.resolution) $('resolution').value = String(defaults.resolution);
  if (defaults.sampling_steps) $('steps').value = String(defaults.sampling_steps);
  if (typeof defaults.rewriter_thinking === 'boolean') $('thinking').checked = defaults.rewriter_thinking;
  if (defaults.upscale_available === false) {
    $('upscale').checked = false;
    $('upscale').closest('label').hidden = true;
  }
  syncPills();
  render();
}

syncPills();
fetchPresets();
applyProfileDefaults();
const saved = localStorage.getItem(storageKey);
if (saved) {
  restoring = true;
  sync(saved).then(() => { if (!job) projects(); });
} else projects();
render();
