const $ = id => document.getElementById(id);
const storageKey = 'banana_teppan_job';
const idle = new Set(['kitchen_ready', 'done', 'error', 'cancelled', 'interrupted']);
let job = null, timer, pending = false, restoring = false, repeating = false;
let renderedSignature = '';

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

function renderDishes() {
  const dishes = job?.kitchen?.dishes ?? [];
  const signature = JSON.stringify([job?.id, job?.status, dishes,
    job?.segments?.map(segment => [segment.preview, segment.prompt])]);
  if (signature === renderedSignature) return;
  renderedSignature = signature;
  $('dishes').replaceChildren();
  dishes.forEach((dish, index) => {
    const current = index === dishes.length - 1;
    const card = element('article');
    card.className = 'dish';
    const accepted = dish.selected !== undefined;
    card.append(element('h2', '第 ' + (index + 1) + ' 道菜' + (accepted ? ' · 已採用' : '')));
    dish.attempts.forEach((attempt, version) => {
      const clips = attempt.clips.map(clip => job.segments[clip]);
      const ready = clips.length > 0 && clips.every(clip => clip?.preview);
      const entry = element('details');
      entry.open = version === (accepted ? dish.selected : dish.attempts.length - 1);
      entry.append(element('summary', '第 ' + (version + 1) + ' 版' + (ready ? ' · 毛片' : ' · 製作中')));
      if (entry.open) appendAttempt(entry);
      else entry.addEventListener('toggle', () => {
        if (entry.open && entry.childElementCount === 1) appendAttempt(entry);
      });
      card.append(entry);

      function appendAttempt(target) {
        target.append(element('p', attempt.menu));
        clips.forEach((clip, clipIndex) => {
          if (!clip.preview) return;
          if (clips.length > 1) {
            const label = element('p', '片段 ' + (clipIndex + 1));
            label.className = 'shot-label';
            target.append(label);
          }
          target.append(video(clip.preview));
          if (clip.prompt) {
            const prompt = element('details');
            prompt.append(element('summary', 'H3 使用的提示詞'), element('pre', clip.prompt));
            target.append(prompt);
          }
        });
        if (ready && current && !accepted && job.status === 'kitchen_ready') {
          const actions = element('div');
          actions.className = 'dish-actions';
          actions.append(
            button('採用此道菜', () => perform('adopt', {attempt: version})),
            button('此菜重炒', () => beginRepeat(attempt), true)
          );
          target.append(actions);
        }
      }
    });
    $('dishes').append(card);
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
    ['assembling', 'upscaling_1080p'].includes(status) ? 'serving' :
    working ? 'planning' : 'idle';
  $('project-title').hidden = !job;
  $('project-title').textContent = job?.title ?? '';
  const messages = {
    planning_story: '9B 正在讀菜單…',
    running: (rewriting ? '9B 正在備料 · ' : '鐵板加熱中 · ') + count + ' / ' + clips.length + ' 段完成',
    kitchen_ready: accepted ? '這道已採用，可以繼續炒或上菜。' : '出鍋了，先看看毛片。',
    assembling: '正在上菜，合成已採用的毛片…',
    upscaling_1080p: '大火收汁・升頻 2K 中…',
    done: '上菜完成。',
    error: '製作暫停，完成的毛片已保存。',
    cancelled: '已停爐。',
    interrupted: '製作中斷，可繼續製作。'
  };
  $('status').textContent = messages[status] || (working ? '正在準備鐵板…' : '鐵板就位，等你的第一道菜單。');
  progress.hidden = status !== 'running' || !clips.length;
  progress.max = clips.length || 1;
  progress.value = count;
  $('initial-settings').hidden = Boolean(job);
  $('menu-label').textContent = !job ? '第一道菜單' : repeating ? '重炒菜單' : '下一道菜單';
  const canCook = !job || (ready && (accepted || repeating));
  $('cook').textContent = !job ? '開始炒菜' : repeating ? '重炒這道' : '繼續炒';
  $('cook').disabled = working || !canCook;
  $('menu').disabled = working || !canCook;
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
$('new-project').onclick = () => {
  clearTimeout(timer);
  localStorage.removeItem(storageKey);
  job = null;
  repeating = false;
  $('menu-form').reset();
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
