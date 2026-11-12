'use strict';
const $ = id => document.getElementById(id);
const ROOT = '/api/film-v2/';
const TERMINAL = ['script_ready', 'done', 'error', 'cancelled', 'interrupted'];
let current = null, timer = null, scriptRevision = '', submitting = false;
for (let i = 1; i <= 9; i++) {
  const label = document.createElement('label');
  label.textContent = '@圖片' + i;
  const input = document.createElement('input');
  input.id = 'image-' + i;
  input.type = 'file';
  input.accept = 'image/png,image/jpeg,image/webp';
  label.append(input);
  $('uploads').append(label);
}
function note(text) { $('status').textContent = text; }
function lock(active) {
  for (const id of ['draft', 'direct', 'approve', 'revise', 'resume']) $(id).disabled = active;
}
async function request(path, body) {
  const options = body === undefined ? {} : {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  };
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok || data.error) throw Error(data.error || '請求失敗');
  return data;
}
function draft() {
  try { return JSON.parse($('script').value); }
  catch (e) { throw Error('劇本 JSON 格式不正確：' + e.message); }
}
function width() {
  const sizes = {
    '480p': {'16:9':854,'9:16':480,'4:5':480,'1:1':480},
    '720p': {'16:9':1280,'9:16':720,'4:5':720,'1:1':720}
  };
  return sizes[$('resolution').value][$('aspect').value];
}
function renderClips(job) {
  $('clips').replaceChildren();
  for (const clip of job.segments || []) {
    const panel = document.createElement('section');
    panel.className = 'scene';
    const details = document.createElement('details');
    const title = document.createElement('summary');
    title.textContent = '第 ' + (clip.index + 1) + ' 段 · ' +
      clip.start.toFixed(2) + '–' + (clip.start + clip.seconds).toFixed(2) +
      ' 秒 · ' + clip.status;
    const text = document.createElement('pre');
    text.textContent = 'Python 事件：\n' + (clip.director_plan?.event || '') +
      '\n\nH3 攝影稿：\n' + (clip.prompt || '尚未產生');
    details.append(title, text);
    panel.append(details);
    if (clip.preview) {
      const video = document.createElement('video');
      video.controls = true; video.playsInline = true; video.preload = 'none';
      video.src = clip.preview;
      panel.append(video);
    }
    if (job.status === 'done' && clip.preview) {
      const instruction = document.createElement('textarea');
      instruction.rows = 2;
      instruction.placeholder = '本段補拍意見（留空只換 Seed）';
      const retake = document.createElement('button');
      retake.className = 'secondary';
      retake.textContent = '補拍第 ' + (clip.index + 1) + ' 段';
      retake.onclick = () => perform('retake', {index: clip.index, instruction: instruction.value});
      panel.append(instruction, retake);
      const select = document.createElement('select');
      const ready = [1, ...(clip.takes || []).filter(t => t.status === 'ready').map(t => t.version)];
      for (const version of ready) {
        const option = document.createElement('option');
        option.value = String(version);
        option.textContent = '毛片 v' + version + (version === clip.selected_version ? ' · 已採用' : '');
        select.append(option);
      }
      select.value = String(clip.selected_version || 1);
      const candidate = document.createElement('video');
      candidate.controls = true;
      candidate.playsInline = true;
      candidate.preload = 'none';
      const updateCandidate = () => {
        candidate.src = ROOT + 'clip?id=' + encodeURIComponent(job.id) +
          '&index=' + clip.index + '&version=' + Number(select.value);
      };
      select.onchange = updateCandidate;
      updateCandidate();
      const adopt = document.createElement('button');
      adopt.className = 'secondary';
      adopt.textContent = '採用選定毛片並重新合成';
      adopt.onclick = () => perform('adopt', {index:clip.index, version:Number(select.value)});
      panel.append(select, candidate, adopt);
    }
    $('clips').append(panel);
  }
}
function render(job) {
  current = job;
  localStorage.setItem('banana_film_v2_job', job.id);
  const all = job.segments || [];
  const done = all.filter(x => x.status === 'done').length;
  $('progress').max = all.length || 1;
  $('progress').value = done;
  $('progress-label').textContent = all.length ?
    done + ' / ' + all.length + ' 段，預計 ' + job.duration.toFixed(2) + ' 秒' :
    '9B 編劇正在建立全片事件';
  note([job.title + ' · ' + job.id, '狀態：' + job.status,
        job.current ? '目前第 ' + job.current + ' / ' + all.length + ' 段' : '',
        job.error ? '錯誤：' + job.error : '',
        job.revision_error || '', job.retake?.error || '', job.continuity_warning || ''].filter(Boolean).join('\n'));
  $('resume').hidden = !['error', 'cancelled', 'interrupted'].includes(job.status);
  $('stop').hidden = !['planning_story', 'running', 'retaking', 'revising_story'].includes(job.status);
  $('review').hidden = job.status !== 'script_ready';
  if (job.status === 'script_ready' && scriptRevision !== job.script_revision) {
    $('script').value = JSON.stringify(job.script_draft, null, 2);
    scriptRevision = job.script_revision;
  }
  $('movie').hidden = !job.video;
  $('output-video-path').value = job.output_video || (job.video ? 'Export pending - check Media/videos folder' : '');
  if (job.video) {
    if ($('video').getAttribute('src') !== job.video) $('video').src = job.video;
    $('download').href = job.video;
  }
  $('versions').replaceChildren();
  for (const version of job.final_versions || []) {
    const link = document.createElement('a');
    link.href = version.download;
    link.target = '_blank';
    link.textContent = '成片 v' + version.version + (version.version === job.current_master ? '（目前）' : '') + '　';
    $('versions').append(link);
  }
  renderClips(job);
  lock(!TERMINAL.includes(job.status));
}
async function poll() {
  if (!current) return;
  clearTimeout(timer);
  try {
    const job = await request(ROOT + 'status?id=' + encodeURIComponent(current.id));
    render(job);
    if (!TERMINAL.includes(job.status)) timer = setTimeout(poll, 3000);
  } catch (error) {
    note('讀取狀態失敗：' + error.message + '；稍後自動重查，不會重送生成。');
    timer = setTimeout(poll, 7000);
  }
}
async function refreshProjects() {
  const list = await request(ROOT + 'projects');
  $('projects').replaceChildren();
  $('projects').append(new Option('選擇作品', ''));
  for (const job of list) $('projects').append(new Option(
    job.title + ' · ' + job.status + ' · ' + job.completed + '/' + job.total, job.id));
}
async function start(direct) {
  if (submitting) return;
  submitting = true;
  lock(true);
  note('正在上傳圖片、檢查 ComfyUI 並建立專案……');
  try {
    const slots = [];
    for (let i = 1; i <= 9; i++) {
      const file = $('image-' + i).files[0];
      if (!file) { slots.push(null); continue; }
      const response = await fetch('/api/upload', {
        method:'POST', headers:{'X-Filename':encodeURIComponent(file.name)}, body:file
      });
      const result = await response.json();
      if (!response.ok || result.error) throw Error(result.error || '圖片上傳失敗');
      slots.push(result.id);
    }
    const body = {
      project_name:$('project').value, prompt:$('story').value,
      image_slots:slots, max_seconds:Number($('length').value),
      segment_seconds:Number($('segment').value), mode:$('mode').value,
      sound_mode:$('sound').value, aspect:$('aspect').value,
      width:width(), visual_style:$('style').value, intensity:$('intensity').value,
      auto_director:$('auto').checked, script_review:!direct,
      kitchen_attention:$('kitchen').checked, sparse_attention:false,
      motion_lora:$('motion').checked, seed:$('seed').value, rewrite_retries:2
    };
    current = await request(ROOT + 'start', body);
    scriptRevision = '';
    render(current);
    await poll();
  } catch (error) {
    note('建立失敗：' + error.message);
    lock(false);
  } finally {
    submitting = false;
  }
}
async function perform(action, data = {}) {
  if (!current) return;
  lock(true);
  try {
    const result = await request(ROOT + action, {id:current.id, ...data});
    if (result.id) {
      render(result);
      await poll();
    } else {
      note(result.message || '已送出要求。');
    }
  } catch (error) {
    note(action + ' 失敗：' + error.message);
    lock(false);
  }
}
$('draft').onclick = () => start(false);
$('direct').onclick = () => start(true);
$('approve').onclick = () => {
  try { perform('approve', {revision:scriptRevision, draft:draft()}); }
  catch (error) { note(error.message); }
};
$('revise').onclick = () => {
  try { perform('revise', {revision:scriptRevision, instruction:$('instruction').value, draft:draft()}); }
  catch (error) { note(error.message); }
};
$('resume').onclick = () => perform('resume');
$('stop').onclick = () => perform('stop');
$('refresh').onclick = () => refreshProjects().catch(e => note(e.message));
$('load').onclick = async () => {
  const id = $('projects').value;
  if (!id) return;
  clearTimeout(timer);
  try {
    current = await request(ROOT + 'status?id=' + encodeURIComponent(id));
    scriptRevision = '';
    render(current);
    await poll();
  } catch (error) { note(error.message); }
};
const saved = localStorage.getItem('banana_film_v2_job');
refreshProjects().catch(() => {});
if (saved) { current = {id:saved}; poll(); }
