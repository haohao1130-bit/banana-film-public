"""Banana's small ComfyUI HTTP client."""
import json
import shutil
from threading import Lock
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

CLIENT_ID = 'banana-' + uuid.uuid4().hex
on_prompt_queued = None
_active = {}
_active_lock = Lock()


def comfy(cfg, path, payload=None, timeout=60):
    body = None if payload is None else json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(cfg['comfy_url'].rstrip('/') + path, data=body,
                                     headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            if not raw.strip():
                # ComfyUI /free acknowledges with HTTP 200 and no JSON body.
                if payload is not None and path in ('/free', '/interrupt', '/queue'):
                    return {}
                raise RuntimeError(f'ComfyUI {path} 回傳空內容（HTTP {response.status}），請檢查 ComfyUI 是否仍在執行。')
            try:
                result = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                kind = response.headers.get('Content-Type', 'unknown')
                raise RuntimeError(f'ComfyUI {path} 回傳非 JSON（HTTP {response.status}，{kind}），請檢查服務與代理連線。') from None
            if not isinstance(result, dict):
                raise RuntimeError(f'ComfyUI {path} 回應不是預期的 JSON 物件。')
            return result
    except urllib.error.HTTPError as error:
        detail = error.read(4000).decode('utf-8', errors='replace')
        raise RuntimeError(f'ComfyUI HTTP {error.code}: {detail}') from None


def queue_prompt(cfg, graph):
    check_cancelled(cfg)
    result = comfy(cfg, '/prompt', {'prompt': graph, 'client_id': CLIENT_ID})
    if result.get('error') or not result.get('prompt_id'):
        raise RuntimeError('ComfyUI 拒絕工作流：' + json.dumps(result, ensure_ascii=False)[:4000])
    prompt_id = result['prompt_id']
    track_prompt(cfg, prompt_id)
    check_cancelled(cfg)
    if on_prompt_queued is not None:
        on_prompt_queued(prompt_id, graph)
    return prompt_id


def track_prompt(cfg, prompt_id):
    job_id = cfg.get('_banana_stop_job')
    if job_id is not None:
        with _active_lock:
            _active[job_id] = (cfg, prompt_id)


def release_prompt(cfg, prompt_id):
    with _active_lock:
        job_id = cfg.get('_banana_stop_job')
        if (row := _active.get(job_id)) and row[1] == prompt_id:
            _active.pop(job_id)


def active_prompt(job_id):
    with _active_lock:
        return job_id in _active


def interrupt_active(job_id):
    with _active_lock:
        row = _active.pop(job_id, None)
    if not row:
        return 'cancel_requested'
    cfg, prompt_id = row
    if not isinstance(prompt_id, str) or not prompt_id.strip():
        raise ValueError('缺少可確認的 ComfyUI 任務 ID。')

    def includes(queue, group):
        return any(isinstance(item, (list, tuple)) and len(item) >= 2 and item[1] == prompt_id
                   for item in queue.get(group, ()))

    queue = comfy(cfg, '/queue', timeout=5)
    if includes(queue, 'queue_pending'):
        comfy(cfg, '/queue', {'delete': [prompt_id]}, timeout=5)
        queue = comfy(cfg, '/queue', timeout=5)
        if not includes(queue, 'queue_running') and not includes(queue, 'queue_pending'):
            return 'removed_from_queue'
    if includes(queue, 'queue_running'):
        comfy(cfg, '/interrupt', {'prompt_id': prompt_id}, timeout=5)
        return 'interrupt_requested'
    return 'already_finished_or_unknown'


def check_cancelled(cfg):
    cancelled = cfg.get('_banana_stop_check')
    if cancelled is not None and cancelled():
        try:
            interrupt_active(cfg['_banana_stop_job'])
        except (OSError, RuntimeError, ValueError) as error:
            raise InterruptedError(f'已停止後續處理，ComfyUI 中斷未確認：{error}') from error
        raise InterruptedError('使用者緊急停爐。')


def history_entry(cfg, prompt_id):
    key = urllib.parse.quote(str(prompt_id), safe='')
    return comfy(cfg, '/history/' + key).get(str(prompt_id))


def execution_error(entry):
    for event in entry.get('status', {}).get('messages', []):
        if len(event) == 2 and event[0] == 'execution_error':
            info = event[1]
            return f"{info.get('node_type', 'ComfyUI')}: {info.get('exception_message', '').strip()}"
    return 'ComfyUI 生成失敗，請查看 comfyui.log。'


def wait_prompt(cfg, prompt_id, timeout=1800):
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            check_cancelled(cfg)
            entry = history_entry(cfg, prompt_id)
            check_cancelled(cfg)
            if entry:
                status = entry.get('status', {})
                if status.get('status_str') == 'error':
                    raise RuntimeError(execution_error(entry))
                if status.get('completed'):
                    return entry
            time.sleep(1)
        raise RuntimeError('等待 ComfyUI 逾時；未取消伺服器上的工作，請先檢查佇列。')
    finally:
        release_prompt(cfg, prompt_id)


def comfy_download(cfg, fileinfo, dest):
    query = urllib.parse.urlencode({key: fileinfo.get(key, default) for key, default in
                                    [('filename', ''), ('subfolder', ''), ('type', 'output')]})
    with urllib.request.urlopen(cfg['comfy_url'].rstrip('/') + '/view?' + query, timeout=600) as response:
        with open(dest, 'wb') as output:
            shutil.copyfileobj(response, output)

