"""Colab launcher for the separate VNext UI on port 8192."""
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request

import colab_runtime as base

install = base.install

def download(namespace, use_drive_cache=False):
    return base.download(namespace, include_rewriter=True, use_drive_cache=use_drive_cache)


def launch(namespace, save_to_drive=True):
    home = Path("/content/banana_film_vnext_data")
    if save_to_drive:
        from google.colab import drive
        drive.mount("/content/drive")
        home = Path("/content/drive/MyDrive/BananaFilmVNext")
    home.mkdir(parents=True, exist_ok=True)
    cfg_path = home / "config.json"
    cfg = {}
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg.update(comfy_url="http://127.0.0.1:8188",
               comfy_input_dir=str(base.COMFY / "input"),
               free_after_rewrite=True)
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    (base.COMFY / "input").mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen("http://127.0.0.1:8188/system_stats", timeout=2):
            pass
    except OSError:
        base.launch_once(namespace, "banana_comfy_process",
                         [sys.executable, "main.py", "--listen", "127.0.0.1", "--port", "8188"],
                         cwd=base.COMFY, log_path="/content/comfyui.log")
    base.wait_http("http://127.0.0.1:8188/system_stats", timeout=600,
                   process=namespace.get("banana_comfy_process"),
                   label="ComfyUI", log_path="/content/comfyui.log")
    health = "http://127.0.0.1:8192/api/health"
    try:
        with urllib.request.urlopen(health, timeout=2) as response:
            info = json.load(response)
        if info.get("service") != "banana-film-vnext":
            raise RuntimeError("8192 埠已有其他服務，不能覆蓋。請換新的 Colab 執行階段。")
        print("已沿用執行中的 VNext 網頁服務。")
    except urllib.error.URLError:
        repo = Path(__file__).resolve().parents[1]
        env = dict(os.environ, BANANA_DATA=str(home), BANANA_VNEXT_DATA=str(home),
                   BANANA_VNEXT_PORT="8192")
        base.launch_once(namespace, "banana_vnext_frontend_process",
                         [sys.executable, "-m", "banana_mv.vnext_server"],
                         cwd=repo, env=env, log_path="/content/banana_film_vnext.log")
    base.wait_http(health, timeout=120,
                   process=namespace.get("banana_vnext_frontend_process"),
                   label="VNext 完整前端", log_path="/content/banana_film_vnext.log")
    from google.colab import output
    print("✅ VNext 全片製片前端已啟動；作品位置：", home)
    print("提示：先測 15–30 秒的短片。9B 劇本與 H3 GPU 效果仍待真實實拍驗收。")
    output.serve_kernel_port_as_window(8192, anchor_text="🍌 打開 VNext 全片製片所")


show_shutdown_control = base.show_shutdown_control
