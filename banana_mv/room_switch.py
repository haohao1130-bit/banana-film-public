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
    local = os.environ.get('LOCALAPPDATA')
    candidates = []
    if target == 'film':
        if local:
            candidates.append(Path(local) / 'BananaFilm-5070-CU130-Launcher' / 'Bootstrap_BANANA_FILM_5070.ps1')
        candidates.append(Path(r'F:\AI\BANANA_FILM_5070_STUDIO\Launcher\Bootstrap_BANANA_FILM_5070.ps1'))
    elif target == 'mv' and local:
        candidates.append(Path(local) / 'BananaMV-5070-CU130-Launcher' / 'Launch_Banana_5070.ps1')
    return next((path for path in candidates if path.is_file()), None)


# 另一套服務有自己的 Python、torch 與 CUDA。沿用這邊的 PATH 和虛擬環境變數，
# Windows 會先載到這邊的 DLL：從鐵板燒切到 MV 後，音樂分析載入 torch_python.dll
# 被擋（WinError 4551），手動重開 MV 就正常。
_INHERITED = ('BANANA_', 'PYTHON', 'VIRTUAL_ENV', 'CONDA', 'PIP_', 'CUDA_VISIBLE_DEVICES')
SYSTEM_PATH = ("$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + "
               "[Environment]::GetEnvironmentVariable('Path','User'); ")


def clean_environment(environ=None):
    """給另一套服務的環境：拿掉這邊的虛擬環境與 Banana 設定；PATH 由 PowerShell 重設成系統原本的。"""
    environ = os.environ if environ is None else environ
    return {name: value for name, value in environ.items() if not name.upper().startswith(_INHERITED)}


def same_origin_control(headers, control):
    """Check browser control requests against the direct or forwarded host."""
    try:
        origin = urlsplit(headers.get('Origin', ''))
    except ValueError:
        return False
    hosts = [headers.get(name, '').casefold() for name in ('Host', 'X-Forwarded-Host')]
    return (
        origin.scheme in ('http', 'https')
        and bool(origin.netloc)
        and origin.netloc.casefold() in hosts
        and not (origin.path or origin.query or origin.fragment)
        and headers.get('Sec-Fetch-Site', 'same-origin') in ('same-origin', 'none')
        and headers.get('X-Banana-Control') == control
    )


def switch(handler, target, backend, gpu_lock):
    path = launcher(target, backend.PORT)
    if not path:
        return handler.send_json({'ok': False, 'error': '找不到另一套 5070 桌面啟動器。'}, 503)
    if not same_origin_control(handler.headers, '5070-room-switch'):
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
            + SYSTEM_PATH +
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
        env = clean_environment()
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
