"""Local 5070 handoff between the two installed desktop launchers."""
import os
import base64
from pathlib import Path
import subprocess
import threading
from urllib.parse import urlsplit


def launcher(target, port):
    if os.name != 'nt' or port != 8193:
        return None
    if target == 'film':
        path = Path(r'F:\AI\BANANA_FILM_5070_STUDIO\Launcher\Bootstrap_BANANA_FILM_5070.ps1')
    else:
        local = os.environ.get('LOCALAPPDATA')
        if not local:
            return None
        path = Path(local) / 'BananaMV-5070-CU130-Launcher' / 'Launch_Banana_5070.ps1'
    return path if path.is_file() else None


def switch(handler, target, backend, gpu_lock):
    path = launcher(target, backend.PORT)
    if not path:
        return handler.send_json({'ok': False, 'error': '找不到另一套 5070 桌面啟動器。'}, 503)
    origin = urlsplit(handler.headers.get('Origin', ''))
    hosts = [handler.headers.get(name, '').casefold() for name in ('Host', 'X-Forwarded-Host')]
    if (origin.scheme not in ('http', 'https') or not origin.netloc
            or origin.netloc.casefold() not in hosts
            or handler.headers.get('Sec-Fetch-Site', 'same-origin') not in ('same-origin', 'none')
            or handler.headers.get('X-Banana-Control') != '5070-room-switch'):
        return handler.send_json({'ok': False, 'error': '切換請求來源無效。'}, 403)
    if not gpu_lock.acquire(blocking=False):
        return handler.send_json({'ok': False, 'error': '作品處理中，請等完成再切換。'}, 409)
    try:
        queue = backend.comfy(backend.load_config(), '/queue')
        if not isinstance(queue, dict) or queue.get('queue_running') or queue.get('queue_pending'):
            gpu_lock.release()
            return handler.send_json({'ok': False, 'error': 'ComfyUI 還有任務。'}, 409)
        script = str(path).replace("'", "''")
        args = ' -Port 8193 -NoBrowser' if target == 'film' else ''
        # The desktop launcher must run from its own folder with its own configuration.
        command = (
            "$ErrorActionPreference = 'Stop'; "
            "$deadline = (Get-Date).AddSeconds(45); "
            "while ($true) { "
            "$client = New-Object System.Net.Sockets.TcpClient; "
            "try { $client.Connect('127.0.0.1',8193); $listening = $true } "
            "catch { $listening = $false } finally { $client.Dispose() }; "
            "if (-not $listening) { break }; "
            "if ((Get-Date) -ge $deadline) { throw 'Port 8193 did not close.' }; "
            "Start-Sleep -Milliseconds 250 }; "
            f"& '{script}'{args}"
        )
        encoded = base64.b64encode(command.encode('utf-16-le')).decode('ascii')
        env = {name: value for name, value in os.environ.items()
               if not name.upper().startswith(('BANANA_', 'PYTHONPATH', 'PYTHONHOME'))}
        log = backend.DATA / 'room-switch.log'
        with log.open('wb') as output:
            subprocess.Popen(
                ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', encoded],
                cwd=str(path.parent), env=env, stdin=subprocess.DEVNULL,
                stdout=output, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
    except Exception:
        gpu_lock.release()
        return handler.send_json({'ok': False, 'error': '無法確認佇列或啟動另一個服務。'}, 503)
    try:
        return handler.send_json({'ok': True}, 202)
    finally:
        threading.Thread(target=handler.server.shutdown, daemon=True).start()
