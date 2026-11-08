"""Film-only launch; model installation/download stays on the tested MV baseline."""
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request
import colab_runtime as base

ROOT=Path(__file__).resolve().parents[1]
install=base.install


def download(ns,use_drive_cache=False):
    return base.download(ns,include_rewriter=True,use_drive_cache=use_drive_cache)


def launch(ns,save_to_drive=True):
    data=Path('/content/banana_film_data')
    if save_to_drive:
        from google.colab import drive
        drive.mount('/content/drive')
        data=Path('/content/drive/MyDrive/BananaFilmStudio')
    data.mkdir(parents=True,exist_ok=True)
    cfg={'comfy_url':'http://127.0.0.1:8188','comfy_input_dir':str(base.COMFY/'input'),'free_after_rewrite':True}
    path=data/'config.json'
    if path.exists():cfg={**json.loads(path.read_text()),**cfg}
    path.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
    (base.COMFY/'input').mkdir(parents=True,exist_ok=True)
    try:
        with urllib.request.urlopen('http://127.0.0.1:8188/system_stats',timeout=2):pass
    except OSError:
        base.launch_once(ns,'banana_comfy_process',[sys.executable,'main.py','--listen','127.0.0.1','--port','8188'],
                         cwd=base.COMFY,log_path='/content/comfyui.log')
    base.wait_http('http://127.0.0.1:8188/system_stats',timeout=600,process=ns.get('banana_comfy_process'),label='ComfyUI',log_path='/content/comfyui.log')
    health_url='http://127.0.0.1:8191/api/health'
    try:
        with urllib.request.urlopen(health_url,timeout=2) as response:health=json.load(response)
        if health.get('service')!='banana-film':raise RuntimeError('8191 已有其他服務，請用新的執行階段。')
    except urllib.error.HTTPError:raise RuntimeError('8191 已有其他前端，請用新的執行階段。') from None
    except urllib.error.URLError:
        base.launch_once(ns,'banana_film_frontend_process',[sys.executable,'-m','banana_mv.film_server'],cwd=ROOT,
                         env=dict(os.environ,BANANA_DATA=str(data),BANANA_PORT='8191'),log_path='/content/banana_film.log')
    base.wait_http(health_url,timeout=180,process=ns.get('banana_film_frontend_process'),label='映像製片所',log_path='/content/banana_film.log')
    with urllib.request.urlopen(health_url,timeout=5) as response:health=json.load(response)
    if health.get('service')!='banana-film':raise RuntimeError('短片服務辨識失敗。')
    from google.colab import output
    print('🎬 蕉宗映像製片所｜作品資料：',data)
    print('請先試拍 15 秒；不要與其他 MV 工作共用 ComfyUI 同時生成。')
    output.serve_kernel_port_as_window(8191,anchor_text='🎬 打開蕉宗映像製片所')


show_shutdown_control=base.show_shutdown_control

