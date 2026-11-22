"""BANANA FILM V2 Colab integration; separate app/data, same pinned H3+9B models."""
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request

import colab_runtime as base

ROOT = Path(__file__).resolve().parents[1]
COMFY = base.COMFY


def install(ns):
    return base.install(ns)


def download(ns, use_drive_cache=False):
    return base.download(ns, include_rewriter=True, use_drive_cache=use_drive_cache)


def launch(ns, save_to_drive=True):
    data = Path("/content/banana_film_v2_data")
    if save_to_drive:
        from google.colab import drive
        drive.mount("/content/drive")
        data = Path("/content/drive/MyDrive/BananaFilmV2")
    data.mkdir(parents=True, exist_ok=True)
    cfg = {"comfy_url": "http://127.0.0.1:8188",
           "comfy_input_dir": str(COMFY / "input"), "free_after_rewrite": True}
    path = data / "config.json"
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        cfg = {**old, **cfg}
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    (COMFY / "input").mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen("http://127.0.0.1:8188/system_stats", timeout=2):
            pass
    except OSError:
        base.launch_once(ns, "banana_comfy_process",
                         [sys.executable, "main.py", "--listen", "127.0.0.1", "--port", "8188"],
                         cwd=COMFY, log_path="/content/comfyui.log")
    base.wait_http("http://127.0.0.1:8188/system_stats", timeout=600,
                   process=ns.get("banana_comfy_process"), label="ComfyUI",
                   log_path="/content/comfyui.log")
    health_url = "http://127.0.0.1:8194/api/health"
    try:
        with urllib.request.urlopen(health_url, timeout=2) as response:
            health = json.load(response)
        if health.get("service") != "banana-film-v2":
            raise RuntimeError("8194 已被其他程式佔用，請使用新的 Colab 執行階段。")
    except urllib.error.HTTPError as exc:
        raise RuntimeError("8194 已被其他服務佔用。") from exc
    except urllib.error.URLError:
        base.launch_once(ns, "banana_film_v2_process",
                         [sys.executable, "-m", "film_v2.server"], cwd=ROOT,
                         env=dict(os.environ, BANANA_DATA=str(data), BANANA_PORT="8194"),
                         log_path="/content/banana_film_v2.log")
    base.wait_http(health_url, timeout=180, process=ns.get("banana_film_v2_process"),
                   label="BANANA FILM V2", log_path="/content/banana_film_v2.log")
    with urllib.request.urlopen(health_url, timeout=5) as response:
        health = json.load(response)
    if health.get("service") != "banana-film-v2" or health.get("engine") != "python_owned_film_v2":
        raise RuntimeError("V2 引擎辨識錯誤；禁止誤接舊前端。")
    from google.colab import output
    print("🍌 BANANA FILM V2｜獨立測試")
    print("Engine:", health["engine"], "| 前端埠：8194", "| 作品資料：", data)
    print("第一次建議 15 秒、480p、無對白；先做劇本確認與兩段 Chain5 試拍。")
    output.serve_kernel_port_as_window(8194, anchor_text="🎬 打開 BANANA FILM V2")


show_shutdown_control = base.show_shutdown_control
