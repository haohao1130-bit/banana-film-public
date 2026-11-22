'use strict';
// Only local addition to the original Colab Film Studio frontend.
// All original Colab forms, camera views, project lists and actions remain intact.
(function () {
  const header = document.querySelector('header');
  if (!header || document.getElementById('film5070-version')) return;
  const label = document.createElement('span');
  label.id = 'film5070-version';
  label.setAttribute('aria-label', '目前本機 FILM 5070 程式版本');
  label.textContent = '5070 · 讀取版本中…';
  label.style.cssText = [
    'display:inline-block', 'font:11px/1.5 ui-monospace,Consolas,monospace',
    'color:#f1d391', 'background:#23312d', 'border:1px solid #806f48',
    'border-radius:9px', 'padding:4px 9px', 'max-width:100%',
    'overflow-wrap:anywhere', 'margin:6px 0'
  ].join(';');
  // Keep the original Colab masthead layout; place only the commit stamp in its edition label.
  (document.getElementById('film-studio-tools') || header).append(label);
  const restart = document.createElement('button');
  restart.type = 'button';
  restart.textContent = '重啟廚房';
  restart.hidden = true;
  const switchRoom = document.createElement('button');
  switchRoom.type = 'button';
  switchRoom.className = 'secondary';
  switchRoom.disabled = true;
  switchRoom.title = '切換服務尚未啟用';
  switchRoom.textContent = '切換至煉丹室（MV）';
  label.after(switchRoom, restart);
  let restarting = false;
  restart.addEventListener('click', async () => {
    if (!window.confirm('重啟本機短片廚房？')) return;
    restarting = true;
    restart.disabled = true;
    restart.textContent = '重啟中…';
    try {
      const response = await fetch('/api/film/restart', {
        method: 'POST', headers: {'X-Banana-Control': 'film-restart'}
      });
      if (!response.ok) throw Error(response.status === 409 ? '作品處理中' : 'HTTP ' + response.status);
    } catch (error) {
      restarting = false;
      restart.textContent = '重啟廚房';
      window.alert('重啟失敗：' + error.message);
      void refreshVersion();
    }
  });
  let instance = null;
  async function refreshVersion() {
    try {
      const response = await fetch('/api/health', {cache:'no-store'});
      if (!response.ok) throw Error('HTTP ' + response.status);
      const health = await response.json();
      if (health.engine !== 'colab_film' ||
          health.variant !== 'rtx5070-fdrive') throw Error('非 5070 製片服務');
      restart.hidden = !health.restart_available;
      restart.disabled = restarting || health.busy;
      const version = health.version || {};
      const branch = version.branch || 'unknown';
      const commit = version.commit || 'unknown';
      label.textContent = '5070 · ' + commit;
      label.title = '分支：' + branch + '\nCommit：' + commit;
      if (instance && health.instance && instance !== health.instance) {
        window.location.reload();
        return;
      }
      instance = health.instance || instance;
    } catch (error) {
      label.textContent = '5070 · 版本讀取失敗';
      label.title = String(error);
    }
  }
  void refreshVersion();
  setInterval(() => { void refreshVersion(); }, 3000);
})();

(function () {
  const transport = document.getElementById('progress')?.closest('.transport');
  if (!transport) return;
  const panel = document.createElement('details');
  panel.innerHTML = '<summary>ComfyUI 即時進度</summary>'
    + '<p class="muted" data-stage role="status"></p>'
    + '<progress aria-label="目前節點進度" hidden></progress>'
    + '<p class="muted" data-count hidden></p>';
  transport.after(panel);
  const stage = panel.querySelector('[data-stage]');
  const bar = panel.querySelector('progress');
  const count = panel.querySelector('[data-count]');
  let timer, polling = false;

  function show(message, value, max, unit, speed) {
    if (stage.textContent !== message) stage.textContent = message;
    bar.hidden = count.hidden = !(max > 0);
    if (!bar.hidden) {
      bar.max = max;
      bar.value = value;
      count.textContent = value + ' / ' + max + ' ' + unit
        + (speed ? ' · ' + speed + ' 秒／' + unit : '');
    }
  }

  async function refresh() {
    if (!panel.open || polling) return;
    polling = true;
    try {
      const response = await fetch('/api/film/progress', {cache: 'no-store'});
      if (!response.ok) throw Error(response.status);
      const task = await response.json();
      if (task.connection !== 'connected') {
        show(task.connection === 'unavailable' ? '目前的 Python 無法讀取即時事件。' : '等待 ComfyUI 連線…');
      } else if (!task.busy) {
        show('廚房待命');
      } else if (task.state === 'finished') {
        show('ComfyUI 節點已完成，廚房正在處理結果。');
      } else if (task.state === 'failed' || task.state === 'interrupted') {
        show(task.state === 'failed' ? 'ComfyUI 節點失敗，請查看作品狀態。' : 'ComfyUI 節點已中斷。');
      } else if (task.node) {
        const node = task.node;
        const label = node === 'TextGenerate' ? '9B 寫稿'
          : /sampler/i.test(node) ? 'H3 影片採樣'
          : /VAEDecode/i.test(node) ? 'VAE 解碼' : node;
        const unit = node === 'TextGenerate' ? 'token' : '步';
        show(label, task.value, task.max, unit, task.seconds_per_unit);
      } else {
        show(task.state === 'queued' ? 'ComfyUI 排隊中…' : '等候節點回報…');
      }
    } catch (_) {
      show('正在重新連線到廚房…');
    } finally {
      polling = false;
      if (panel.open) timer = setTimeout(refresh, 1000);
    }
  }

  panel.addEventListener('toggle', () => {
    clearTimeout(timer);
    void refresh();
  });
})();

(function () {
 const button = Array.from(document.querySelectorAll('header button')).find(b => b.textContent === '切換至煉丹室（MV）');
 if (!button) return;
 let switching = false;
 async function refresh() {
   if (switching) return;
   try {
     const response = await fetch('/api/5070/switch', {cache:'no-store'});
     const state = await response.json();
     button.hidden = false;
     button.disabled = !state.available || state.busy;
     button.title = state.busy ? '作品處理中' : state.available ? '' : '找不到另一套 5070 啟動器';
   } catch (_) { button.disabled = true; }
 }
 button.onclick = async () => {
   if (switching || !window.confirm(button.textContent + '？')) return;
   switching = true;
   button.disabled = true;
   const label = button.textContent;
   try {
     const response = await fetch('/api/5070/switch', {method:'POST', headers:{'X-Banana-Control':'5070-room-switch'}});
     if (!response.ok) throw Error((await response.json()).error || response.status);
     button.textContent = '正在切換…';
     const deadline = Date.now() + 180000;
     while (Date.now() < deadline) {
       await new Promise(resolve => setTimeout(resolve, 2000));
       try {
         const result = await fetch('/api/health', {cache:'no-store'});
         if (result.ok && (await result.json()).service === 'banana-mv') {
           window.location.replace('/');
           return;
         }
       } catch (_) {}
     }
     throw Error('切換逾時，請查看桌面啟動器。');
   } catch (error) { window.alert(error.message); }
   finally {
     switching = false;
     button.textContent = label;
     void refresh();
   }
 };
 void refresh();
 setInterval(refresh, 3000);
})();
