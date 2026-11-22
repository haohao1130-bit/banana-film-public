const $ = id => document.getElementById(id);
const storageKey = 'banana_teppan_job';
const idle = new Set(['kitchen_ready', 'done', 'error', 'cancelled', 'interrupted']);
let job = null, timer, pending = false, restoring = false, repeating = false;
let reactionTimer;
const localImageUrls = new Map();

for (let index = 1; index <= 8; index++) {
  const label = element('label', '@圖片' + index);
  const input = element('input');
  input.type = 'file';
  input.accept = 'image/png,image/jpeg,image/webp';
  label.append(input);
  $('references').append(label);
}

function element(tag, text) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  return node;
}

function imageReferences() {
  if (job) {
    let image = 0;
    return (job.request?.image_slots ?? []).flatMap((asset, index) => {
      if (!asset) return [];
      const query = new URLSearchParams({id: job.id, image: String(image++)});
      return [{slot: index + 1, src: 'api/mv/reference?' + query}];
    });
  }
  return [...$('references').querySelectorAll('input')].flatMap((input, index) => {
    const file = input.files[0];
    if (!file) return [];
    if (!localImageUrls.has(file)) localImageUrls.set(file, URL.createObjectURL(file));
    return [{slot: index + 1, src: localImageUrls.get(file), name: file.name}];
  });
}

function clearLocalImageUrls() {
  for (const url of localImageUrls.values()) URL.revokeObjectURL(url);
  localImageUrls.clear();
}

function bindImageMentions(field, fieldLabel) {
  const input = $(field);
  const suggestions = $(field + '-image-suggestions');
  const list = $(field + '-image-list');
  const empty = $(field + '-image-empty');
  const add = $(field + '-image-add');
  let imageMention = null, composing = false;

  function close() {
    imageMention = null;
    suggestions.hidden = true;
    input.removeAttribute('aria-activedescendant');
  }

  function selectImageOption(index, scroll = false) {
    const rows = [...list.children];
    imageMention.index = index;
    rows.forEach((row, i) => row.setAttribute('aria-selected', String(i === index)));
    if (!rows[index]) {
      input.removeAttribute('aria-activedescendant');
      return;
    }
    input.setAttribute('aria-activedescendant', rows[index].id);
    if (scroll) rows[index].scrollIntoView({block: 'nearest'});
  }

  function insertImageMention(slot) {
    if (!imageMention) return;
    const {start, end} = imageMention;
    const text = '@圖片' + slot + (/\s/.test(input.value[end] ?? '') ? '' : ' ');
    if (input.value.length - (end - start) + text.length > input.maxLength) {
      showFeedback(fieldLabel + '已達字數上限。');
      return;
    }
    input.setRangeText(text, start, end, 'end');
    close();
    input.focus({preventScroll: true});
  }

  function updateImageMention() {
    if (composing || input.disabled || input.selectionStart !== input.selectionEnd) {
      close();
      return;
    }
    const end = input.selectionStart;
    const before = input.value.slice(0, end);
    const match = /[@＠](?:圖片?|图片?|image)?([1-8])?$/i.exec(before);
    if (!match || (match.index > 0 && /[a-z0-9_.]/i.test(before[match.index - 1]))) {
      close();
      return;
    }
    const images = imageReferences();
    const matches = images.filter(ref => !match[1] || ref.slot === Number(match[1]));
    imageMention = {start: match.index, end, index: 0};
    list.replaceChildren();
    for (const ref of matches) {
      const option = button('', () => insertImageMention(ref.slot));
      option.id = field + '-ref-' + ref.slot;
      option.className = 'menu-image-option';
      option.setAttribute('role', 'option');
      option.tabIndex = -1;
      option.onpointerdown = event => event.preventDefault();
      const image = element('img');
      image.src = ref.src;
      image.alt = '';
      const label = element('span', '@圖片' + ref.slot);
      if (ref.name) label.append(element('small', ref.name));
      option.append(image, label);
      list.append(option);
    }
    empty.hidden = matches.length > 0;
    empty.textContent = images.length ? '找不到這個圖號。' : '這桌還沒有參考圖。';
    add.hidden = Boolean(job) || images.length > 0;
    suggestions.hidden = false;
    selectImageOption(0);
  }

  input.addEventListener('input', event => {
    if (!event.isComposing) updateImageMention();
  });
  input.addEventListener('click', updateImageMention);
  input.addEventListener('compositionstart', () => {
    composing = true;
    close();
  });
  input.addEventListener('compositionend', () => {
    composing = false;
    updateImageMention();
  });
  input.addEventListener('blur', event => {
    if (!suggestions.contains(event.relatedTarget)) close();
  });
  input.addEventListener('keydown', event => {
    if (composing || event.isComposing || !imageMention) return;
    const rows = list.children;
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
    } else if (rows.length && ['ArrowUp', 'ArrowDown', 'Enter'].includes(event.key)) {
      event.preventDefault();
      if (event.key === 'Enter') rows[imageMention.index].click();
      else {
        const step = event.key === 'ArrowUp' ? -1 : 1;
        selectImageOption((imageMention.index + step + rows.length) % rows.length, true);
      }
    }
  });
  add.onclick = () => {
    $('settings').open = true;
    close();
    $('references').querySelector('input')?.focus();
  };
  return close;
}

const closeMenuImageMention = bindImageMentions('menu', '菜單');
const closeSharedImageMention = bindImageMentions('shared', '共同設定');

function closeImageMentions() {
  closeMenuImageMention();
  closeSharedImageMention();
}

$('references').addEventListener('change', () => {
  closeImageMentions();
  clearLocalImageUrls();
});

async function api(path, options, stage = '連線到一鍵短片') {
  let response, result;
  try {
    response = await fetch(path, options);
  } catch {
    const next = stage === '送出第一道菜' ? '。重新送出前，請先查看專案清單是否已建立' : '';
    throw Error(stage + '失敗：手機沒有收到一鍵短片的回應。請確認電腦服務與手機連線' + next + '。');
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
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data)
  }, stage);
}

function showFeedback(message) {
  $('feedback').textContent = message;
}

function latestDish() {
  return job?.kitchen?.dishes.at(-1);
}

function button(label, handle, secondary = false) {
  const node = element('button', label);
  node.type = 'button';
  if (secondary) node.className = 'quiet';
  node.onclick = handle;
  return node;
}

function video(src) {
  const node = element('video');
  node.controls = true;
  node.playsInline = true;
  node.preload = 'metadata';
  node.src = src;
  return node;
}

function beginRepeat(attempt) {
  repeating = true;
  $('menu').value = attempt.menu;
  if ([...$('seconds').options].some(option => Number(option.value) === attempt.seconds)) {
    $('seconds').value = String(attempt.seconds);
  }
  render();
  $('menu').focus();
}

const dishMenu = [
  ['🍗', '宮保雞丁'], ['🍲', '三杯雞'], ['🍤', '鳳梨蝦球'], ['🐟', '清蒸石斑'],
  ['🥟', '水晶蝦餃'], ['🍚', '櫻花蝦炒飯'], ['🦀', '避風塘炒蟹'], ['🍖', '糖醋排骨'],
  ['🍜', '紅燒牛肉麵'], ['🥬', '開陽白菜'], ['🍲', '佛跳牆'], ['🦑', '三杯中卷'],
  ['🥩', '黑椒牛柳'], ['🍳', '蟹黃豆腐'], ['🌶️', '麻辣鴨血'], ['🦐', '蒜蓉粉絲蝦'],
  ['🍛', '獅子頭'], ['🍱', '蒲燒鰻魚']
];

function dishName(dish, fallback) {
  const menu = dish.attempts[0]?.menu ?? '';
  const name = /^\s*(?:菜名|標題)[：:]\s*([^\r\n]+)/m.exec(menu);
  return name?.[1].trim() || fallback;
}

function renderDishes() {
  const list = $('dishes');
  const project = job?.id ?? '';
  if (list.dataset.project !== project) {
    list.replaceChildren();
    list.dataset.project = project;
  }
  const dishes = job?.kitchen?.dishes ?? [];
  dishes.forEach((dish, index) => {
    const accepted = dish.selected !== undefined;
    const current = index === dishes.length - 1;
    const canChoose = current && !accepted && job.status === 'kitchen_ready';
    const versions = dish.attempts.map(attempt => attempt.clips.map(clip => job.segments[clip]));
    const allReady = versions.at(-1)?.length && versions.at(-1).every(clip => clip?.preview);
    const state = accepted ? '已採用' : allReady ? '可試菜' :
      idle.has(job.status) ? '尚未完成' : '製作中';
    const signature = JSON.stringify([dish, state, canChoose,
      versions.map(clips => clips.map(clip => [clip?.preview, clip?.prompt]))]);
    const existing = list.children[index];
    if (existing?.dataset.signature === signature) return;
    const card = element('details');
    card.className = 'dish dish-card';
    card.dataset.signature = signature;
    card.open = existing?.open ?? false;
    card.setAttribute('name', 'teppan-dishes');
    const [icon, fallback] = dishMenu[index % dishMenu.length];
    const plate = element('span', icon);
    plate.className = 'dish-plate';
    plate.setAttribute('aria-hidden', 'true');
    const title = element('strong', dishName(dish, fallback));
    title.className = 'dish-name';
    const label = element('span', '第 ' + (index + 1) + ' 道 · ' + state);
    label.className = 'dish-state';
    const heading = element('span');
    heading.className = 'dish-heading';
    heading.append(label, title);
    const summary = element('summary');
    summary.append(plate, heading);
    card.append(summary);
    card.addEventListener('toggle', () => {
      if (card.open) {
        if (card.childElementCount === 1) appendVersions();
      } else {
        for (const video of card.querySelectorAll('video')) video.pause();
      }
    });
    if (card.open) appendVersions();
    if (existing) existing.replaceWith(card);
    else list.append(card);

    function appendVersions() {
      const panel = element('div');
      panel.className = 'dish-versions';
      dish.attempts.forEach((attempt, version) => {
        const clips = versions[version];
        const ready = clips.length > 0 && clips.every(clip => clip?.preview);
        const entry = element('details');
        entry.open = version === (accepted ? dish.selected : dish.attempts.length - 1);
        const status = ready ? ' · 毛片' : ' · 尚未完成';
        entry.append(element('summary', '第 ' + (version + 1) + ' 版' + status));
        if (entry.open) appendAttempt();
        else entry.addEventListener('toggle', () => {
          if (entry.open && entry.childElementCount === 1) appendAttempt();
        });
        panel.append(entry);

        function appendAttempt() {
          entry.append(element('p', attempt.menu));
          clips.forEach((clip, clipIndex) => {
            if (!clip?.preview) return;
            if (clips.length > 1) {
              const shot = element('p', '片段 ' + (clipIndex + 1));
              shot.className = 'shot-label';
              entry.append(shot);
            }
            entry.append(video(clip.preview));
            if (clip.prompt) {
              const prompt = element('details');
              prompt.append(element('summary', 'H3 使用的提示詞'), element('pre', clip.prompt));
              entry.append(prompt);
            }
          });
          if (ready && canChoose) {
            const actions = element('div');
            actions.className = 'dish-actions';
            actions.append(
              button('採用此道菜', () => perform('adopt', {attempt: version})),
              button('此菜重炒', () => beginRepeat(attempt), true)
            );
            entry.append(actions);
          }
        }
      });
      card.append(panel);
    }
  });
}

function renderFinal() {
  const output = $('served');
  output.hidden = !job?.video;
  const upscale = job?.final_versions?.findLast(row => row.reason === 'upscale_1440p');
  const src = upscale?.download || job?.video;
  if (!src || output.dataset.src === src) return;
  output.dataset.src = src;
  const download = element('a', upscale ? '下載 2K 成片' : '下載成片');
  download.href = src;
  download.download = (job.title || 'BananaFilm') + '.mp4';
  output.replaceChildren(element('h2', '已上菜'), video(src), download);
  if (upscale && job.video) {
    const master = element('a', '下載原尺寸母片');
    master.href = job.video;
    master.download = (job.title || 'BananaFilm') + '-母片.mp4';
    output.append(element('p'), master);
  }
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
  let label = status === 'planning_story' ? '9B 規劃菜單'
    : segment?.status === 'rewriting' ? '9B 撰寫分鏡' : 'H3 影片生成';
  if (task?.state === 'queued') label += ' · 排隊中';
  else if (task?.state === 'finished') label = '正在整理生成結果';
  else if (task?.state === 'failed') label = 'ComfyUI 回報錯誤';
  else if (task?.state === 'interrupted') label = 'ComfyUI 已中斷';
  else if (sampling) label = 'H3 影片採樣';
  else if (/VAEDecode/i.test(task?.node ?? '')) label = 'H3 解碼影片';
  if (measured) label += ' · ' + task.value + ' / ' + task.max + (writing ? ' tokens' : ' 步');
  const stage = $('comfy-stage'), bar = $('comfy-count');
  if (stage.textContent !== label) stage.textContent = label;
  bar.hidden = !measured;
  if (measured) {
    bar.max = task.max;
    bar.value = task.value;
  }
}

function render() {
  const dish = latestDish();
  const status = job?.status;
  const working = pending || restoring || (Boolean(status) && !idle.has(status));
  const ready = status === 'kitchen_ready';
  const accepted = dish?.selected !== undefined;
  const progress = $('progress');
  const clips = dish?.attempts.at(-1).clips ?? [];
  const count = clips.filter(index => job.segments[index]?.status === 'done').length;
  const segment = job?.segments?.[job.current - 1];
  const rewriting = segment?.status === 'rewriting';
  $('counter').dataset.phase = status === 'running' && !rewriting ? 'cooking' :
    status === 'upscaling_1080p' ? 'finishing' : status === 'assembling' ? 'serving' :
    working ? 'planning' : 'idle';
  $('project-title').hidden = !job;
  $('project-title').textContent = job?.title ?? '';
  const messages = {
    planning_story: '蕉彌正在讀菜單…',
    running: (rewriting ? '蕉彌正在備料 · ' : '蕉彌正在炒菜 · ') + count + ' / ' + clips.length + ' 段完成',
    kitchen_ready: accepted ? '這道已採用，可以繼續炒或上菜。' : '蕉彌炒好了，先看看毛片。',
    assembling: '蕉彌正在上菜・合成影片中…',
    upscaling_1080p: '蕉彌正在大火收汁・升頻 2K 中…',
    done: '蕉彌上菜完成。',
    error: '製作暫停，完成的毛片已保存。',
    cancelled: '已停爐。',
    interrupted: '製作中斷，可繼續製作。'
  };
  $('status').textContent = messages[status] || (working ? '蕉彌正在準備鐵板…' : '鐵板就位，等你的第一道菜單。');
  progress.hidden = status !== 'running' || !clips.length;
  progress.max = clips.length || 1;
  progress.value = count;
  renderComfyProgress(status, segment);
  $('initial-settings').hidden = Boolean(job);
  $('shared-setup').hidden = Boolean(job);
  $('shared').disabled = working;
  $('menu-label').textContent = !job ? '第一道菜單' : repeating ? '重炒菜單' : '下一道菜單';
  const canCook = !job || (ready && (accepted || repeating));
  $('cook').textContent = !job ? '開始炒菜' : repeating ? '重炒這道' : '繼續炒';
  $('cook').disabled = working || !canCook;
  $('menu').disabled = working || !canCook;
  if ($('menu').disabled) closeImageMentions();
  $('seconds').disabled = working;
  $('stop').hidden = !job || idle.has(status);
  $('stop').disabled = pending;
  $('resume').hidden = !['error', 'cancelled', 'interrupted'].includes(status);
  $('resume').disabled = working;
  $('service').hidden = !(ready && accepted);
  $('serve').disabled = working;
  $('menu-form').hidden = status === 'done';
  $('new-project').hidden = !job || working;
  const request = job?.request;
  const resolution = request ? (request.width > 854 || (request.aspect !== '16:9' && request.width > 480) ? '720' : '480') : $('resolution').value;
  const steps = request?.sampling_steps ?? $('steps').value;
  const thinking = request?.rewriter_thinking ?? $('thinking').checked;
  $('profile').textContent = resolution + 'P · ' + steps + ' 步 · ' + $('seconds').value + ' 秒' + (thinking ? ' · Thinking' : '');
  renderDishes();
  renderFinal();
  if (status === 'error') showFeedback(job.error);
  if (status === 'done' && job.upscale_error) showFeedback('2K 升頻未完成，母片可下載。' + job.upscale_error);
}

async function sync(id) {
  clearTimeout(timer);
  try {
    const result = await api('api/mv/status?id=' + encodeURIComponent(id));
    if (!result.kitchen) throw Error('這個專案不屬於蕉彌鐵板燒。');
    job = result;
    localStorage.setItem(storageKey, id);
    $('restore-wrap').hidden = true;
    if (!idle.has(result.status)) timer = setTimeout(() => sync(id), 1600);
  } catch (error) {
    showFeedback(error.message);
    if (job?.id === id && !idle.has(job.status)) timer = setTimeout(() => sync(id), 5000);
  } finally {
    restoring = false;
    render();
  }
}

async function perform(action, fields = {}) {
  if (pending || restoring) return;
  pending = true;
  showFeedback('');
  render();
  try {
    let updated;
    if (action === 'start') {
      const request = await firstRequest();
      showFeedback('正在送出第一道菜…');
      updated = await post('film/kitchen/start', request, '送出第一道菜');
    } else if (['stop', 'resume'].includes(action)) {
      updated = await post('mv/' + action, {id: job.id});
    } else updated = await post('film/kitchen/' + action, {id: job.id, ...fields});
    if (action === 'repeat') {
      const counter = $('counter');
      clearTimeout(reactionTimer);
      counter.classList.add('is-surprised');
      reactionTimer = setTimeout(() => counter.classList.remove('is-surprised'), 820);
    }
    if (['start', 'append', 'repeat', 'adopt'].includes(action)) {
      $('menu').value = '';
      $('settings').open = false;
      repeating = false;
    }
    const id = action === 'start' ? updated.id : job.id;
    if (updated.kitchen) {
      job = updated;
      localStorage.setItem(storageKey, id);
    }
    showFeedback('');
    await sync(id);
  } catch (error) {
    showFeedback(error.message);
  } finally {
    pending = false;
    render();
  }
}

async function firstRequest() {
  const shared = $('shared').value.trim(), menu = $('menu').value.trim();
  const prompt = [shared, menu].filter(Boolean).join('\n\n');
  if (Array.from(prompt).length > 30000) throw Error('共同設定和菜單合計最多 30000 字。');
  const slots = [];
  for (const input of $('references').querySelectorAll('input')) {
    const file = input.files[0];
    if (!file) {
      slots.push(null);
      continue;
    }
    const reference = '@圖片' + (slots.length + 1);
    const stage = '上傳 ' + reference;
    showFeedback('正在' + stage + '…');
    if (file.size > 256 * 1024 * 1024) throw Error(reference + ' 超過單檔上限 256 MiB。');
    let bytes;
    try {
      bytes = await file.arrayBuffer();
    } catch {
      throw Error('手機無法讀取 ' + reference + '。請重新選擇已下載到手機的圖片。');
    }
    if (!bytes.byteLength) throw Error(reference + ' 是空檔案，請重新選擇圖片。');
    const asset = await api('api/upload', {
      method: 'POST', headers: {'X-Filename': encodeURIComponent(file.name)}, body: bytes
    }, stage);
    if (!asset?.id) throw Error(stage + '失敗：伺服器未回傳圖片編號。');
    slots.push(asset.id);
  }
  slots.push(null);
  const aspect = $('aspect').value, resolution = Number($('resolution').value);
  return {
    project_name: $('name').value.trim(), prompt, image_slots: slots,
    kitchen_menu: menu, kitchen_shared_setup: shared,
    max_seconds: Number($('seconds').value), duration_preference: 'selector',
    segment_seconds: 10, mode: 'chain', sound_mode: $('sound').value, aspect,
    width: aspect === '16:9' ? (resolution === 480 ? 854 : 1280) : resolution,
    sampling_steps: Number($('steps').value), rewriter_thinking: $('thinking').checked,
    kitchen_attention: true, sparse_attention: false, motion_lora: false
  };
}

async function projects() {
  try {
    const rows = await api('api/film/kitchen/projects');
    const select = $('restore-project');
    select.replaceChildren(new Option('選擇專案', ''));
    for (const row of rows) select.add(new Option(row.title, row.id));
    $('restore-wrap').hidden = Boolean(job) || !rows.length;
  } catch (error) {
    if (!job) showFeedback(error.message);
  }
}

$('menu-form').onsubmit = event => {
  event.preventDefault();
  const menu = $('menu').value.trim();
  if (!menu) return;
  perform(!job ? 'start' : repeating ? 'repeat' : 'append', {menu, seconds: Number($('seconds').value)});
};
$('serve').onclick = () => perform('serve', {upscale: $('upscale').checked});
$('resume').onclick = () => perform('resume');
$('stop').onclick = () => perform('stop');
$('restore-project').onchange = () => {
  const id = $('restore-project').value;
  if (id && !pending && !restoring && !job) {
    restoring = true;
    render();
    sync(id);
  }
};
$('expand-menu').onclick = () => {
  const expand = $('expand-menu').getAttribute('aria-expanded') !== 'true';
  $('expand-menu').setAttribute('aria-expanded', String(expand));
  $('expand-menu').textContent = expand ? '收起輸入框' : '拉開輸入框';
  $('menu').style.removeProperty('height');
  $('menu').classList.toggle('is-expanded', expand);
};
$('new-project').onclick = () => {
  clearTimeout(timer);
  localStorage.removeItem(storageKey);
  job = null;
  repeating = false;
  $('menu-form').reset();
  closeImageMentions();
  clearLocalImageUrls();
  $('upscale').checked = true;
  $('served').dataset.src = '';
  $('served').replaceChildren();
  showFeedback('');
  render();
  projects();
};
$('settings').onchange = render;
const saved = localStorage.getItem(storageKey);
if (saved) {
  restoring = true;
  sync(saved).then(() => { if (!job) projects(); });
} else projects();
render();
