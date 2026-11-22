const $ = id => document.getElementById(id);
const storageKey = 'banana_teppan_job';
const idle = new Set(['kitchen_ready', 'done', 'error', 'cancelled', 'interrupted']);
let job = null, timer, pending = false, restoring = false, repeating = false;
const menuInput = $('menu');
let imageMention = null, composing = false;
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

function menuReferences() {
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

function closeImageMention() {
  imageMention = null;
  $('menu-image-suggestions').hidden = true;
  menuInput.removeAttribute('aria-activedescendant');
}

function selectImageOption(index, scroll = false) {
  const rows = [...$('menu-image-list').children];
  imageMention.index = index;
  rows.forEach((row, i) => row.setAttribute('aria-selected', String(i === index)));
  if (!rows[index]) {
    menuInput.removeAttribute('aria-activedescendant');
    return;
  }
  menuInput.setAttribute('aria-activedescendant', rows[index].id);
  if (scroll) rows[index].scrollIntoView({block: 'nearest'});
}

function insertImageMention(slot) {
  if (!imageMention) return;
  const {start, end} = imageMention;
  const text = '@圖片' + slot + (/\s/.test(menuInput.value[end] ?? '') ? '' : ' ');
  if (menuInput.value.length - (end - start) + text.length > menuInput.maxLength) {
    showFeedback('菜單已達字數上限。');
    return;
  }
  menuInput.setRangeText(text, start, end, 'end');
  closeImageMention();
  menuInput.focus({preventScroll: true});
}

function updateImageMention() {
  if (composing || menuInput.disabled || menuInput.selectionStart !== menuInput.selectionEnd) {
    closeImageMention();
    return;
  }
  const end = menuInput.selectionStart;
  const before = menuInput.value.slice(0, end);
  const match = /[@＠](?:圖片?|图片?|image)?([1-8])?$/i.exec(before);
  if (!match || (match.index > 0 && /[a-z0-9_.]/i.test(before[match.index - 1]))) {
    closeImageMention();
    return;
  }
  const images = menuReferences();
  const matches = images.filter(ref => !match[1] || ref.slot === Number(match[1]));
  imageMention = {start: match.index, end, index: 0};
  const list = $('menu-image-list');
  list.replaceChildren();
  for (const ref of matches) {
    const option = button('', () => insertImageMention(ref.slot));
    option.id = 'menu-ref-' + ref.slot;
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
  const empty = $('menu-image-empty');
  empty.hidden = matches.length > 0;
  empty.textContent = images.length ? '找不到這個圖號。' : '這桌還沒有參考圖。';
  $('menu-image-add').hidden = Boolean(job) || images.length > 0;
  $('menu-image-suggestions').hidden = false;
  selectImageOption(0);
}

menuInput.addEventListener('input', event => {
  if (!event.isComposing) updateImageMention();
});
menuInput.addEventListener('click', updateImageMention);
menuInput.addEventListener('compositionstart', () => {
  composing = true;
  closeImageMention();
});
menuInput.addEventListener('compositionend', () => {
  composing = false;
  updateImageMention();
});
menuInput.addEventListener('blur', event => {
  if (!$('menu-image-suggestions').contains(event.relatedTarget)) closeImageMention();
});
menuInput.addEventListener('keydown', event => {
  if (composing || event.isComposing || !imageMention) return;
  const rows = $('menu-image-list').children;
  if (event.key === 'Escape') {
    event.preventDefault();
    closeImageMention();
  } else if (rows.length && ['ArrowUp', 'ArrowDown', 'Enter'].includes(event.key)) {
    event.preventDefault();
    if (event.key === 'Enter') rows[imageMention.index].click();
    else {
      const step = event.key === 'ArrowUp' ? -1 : 1;
      selectImageOption((imageMention.index + step + rows.length) % rows.length, true);
    }
  }
});
$('menu-image-add').onclick = () => {
  $('settings').open = true;
  closeImageMention();
  $('references').querySelector('input')?.focus();
};
$('references').addEventListener('change', clearLocalImageUrls);

async function api(path, options) {
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) throw Error(result.error || '請求失敗。');
  return result;
}

function post(action, data) {
  return api('api/' + action, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data)
  });
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

function dishName(dish, index) {
  const lines = dish.attempts[0]?.menu?.trim().split(/\r?\n/) ?? [];
  const named = lines.find(line => /^(?:菜名|標題)[：:]/.test(line.trim()));
  const title = (named?.trim().replace(/^(?:菜名|標題)[：:]\s*/, '') || lines[0] || '').trim();
  return title || '第 ' + (index + 1) + ' 道菜';
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
    const title = element('span', dishName(dish, index));
    title.className = 'dish-name';
    const label = element('span', state);
    label.className = 'dish-state';
    const summary = element('summary');
    summary.append(title, label);
    card.append(summary);
    if (card.open) appendVersions();
    else card.addEventListener('toggle', () => {
      if (card.open && card.childElementCount === 1) appendVersions();
    });
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

function render() {
  const dish = latestDish();
  const status = job?.status;
  const working = pending || restoring || (Boolean(status) && !idle.has(status));
  const ready = status === 'kitchen_ready';
  const accepted = dish?.selected !== undefined;
  const progress = $('progress');
  const clips = dish?.attempts.at(-1).clips ?? [];
  const count = clips.filter(index => job.segments[index]?.status === 'done').length;
  const rewriting = job?.segments?.[job.current - 1]?.status === 'rewriting';
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
  $('initial-settings').hidden = Boolean(job);
  $('menu-label').textContent = !job ? '第一道菜單' : repeating ? '重炒菜單' : '下一道菜單';
  const canCook = !job || (ready && (accepted || repeating));
  $('cook').textContent = !job ? '開始炒菜' : repeating ? '重炒這道' : '繼續炒';
  $('cook').disabled = working || !canCook;
  $('menu').disabled = working || !canCook;
  if ($('menu').disabled) closeImageMention();
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
    if (action === 'start') updated = await post('film/kitchen/start', await firstRequest());
    else if (['stop', 'resume'].includes(action)) {
      updated = await post('mv/' + action, {id: job.id});
    } else updated = await post('film/kitchen/' + action, {id: job.id, ...fields});
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
    await sync(id);
  } catch (error) {
    showFeedback(error.message);
  } finally {
    pending = false;
    render();
  }
}

async function firstRequest() {
  const slots = [];
  for (const input of $('references').querySelectorAll('input')) {
    const file = input.files[0];
    const asset = file ? await api('api/upload', {
      method: 'POST', headers: {'X-Filename': encodeURIComponent(file.name)}, body: file
    }) : null;
    slots.push(asset?.id ?? null);
  }
  slots.push(null);
  const aspect = $('aspect').value, resolution = Number($('resolution').value);
  const shared = $('shared').value.trim(), menu = $('menu').value.trim();
  const prompt = [shared, menu].filter(Boolean).join('\n\n');
  if (Array.from(prompt).length > 30000) throw Error('共同設定和菜單合計最多 30000 字。');
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
  closeImageMention();
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
