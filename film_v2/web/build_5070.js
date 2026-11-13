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
  (header.querySelector('.edition') || header).append(label);
  let instance = null;
  async function refreshVersion() {
    try {
      const response = await fetch('/api/health', {cache:'no-store'});
      if (!response.ok) throw Error('HTTP ' + response.status);
      const health = await response.json();
      if (health.engine !== 'colab_film' ||
          health.variant !== 'rtx5070-fdrive') throw Error('非 5070 製片服務');
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
  setInterval(() => { void refreshVersion(); }, 15000);
})();
