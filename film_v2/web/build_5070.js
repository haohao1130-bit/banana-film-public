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
