"""Build the public, independently deployed film studio notebook."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def md(text):return {'cell_type':'markdown','metadata':{},'source':text.splitlines(True)}
def code(text):return {'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':text.splitlines(True)}

clone=(ROOT/'tools/public_clone.py').read_text()
cells=[md('''# 🎬 大乘蕉宗・映像製片所

故事＋角色／場景圖 → 9B 劇本預覽／細修 → 確認開拍 → H3 原生影音 → 完整短片。這是公開測試版，使用你自己的 Colab GPU，作品保存在自己的執行階段或 Drive。

**初版尚待 GPU 實測，請先用 15 秒上限試拍。** 執行階段選 G4 或 A100 GPU，依序執行①②③。模型與既有 MV 版本相同，9B 為必要元件。

程式可匿名下載，不需要 GitHub Token。模型通常可匿名下載；需要時可在 Colab 左側 🔑 設定唯讀 `HF_TOKEN`，不要貼進程式。

本入口不需歌曲，聲音由 H3 逐段生成；跨段聲線與配樂連續性不保證。第一次選無對白、15 秒試拍。
'''),code('#@title ① 安裝獨立短片製作所\n'+clone+'''
PROJECT=Path('/content/banana-film-public')
clone_project(PROJECT,'https://github.com/haohao1130-bit/banana-film-public.git')
sys.path.insert(0,str(PROJECT/'tools'))
import film_runtime as runtime
runtime.install(globals())
'''),code('''#@title ② 下載 H3 與 9B 導演模型
USE_DRIVE_CACHE = False #@param {type:"boolean"}
runtime.download(globals(),use_drive_cache=USE_DRIVE_CACHE)
'''),code('''#@title ③ 啟動蕉宗映像製片所
SAVE_TO_DRIVE = True #@param {type:"boolean"}
runtime.launch(globals(),save_to_drive=SAVE_TO_DRIVE)
'''),md('''## 劇本確認、開拍與補拍

九格獨立選圖（空格不遞補）、輸入故事，用 `@圖片1`、`@圖片2` 指定用途。選全片時間上限及風格，按「生成劇本」。預覽後可直接編輯或填意見按「請導演修這版」，最後按「確認劇本並開拍」。也可按「直接開拍」，規劃完成後直接生成影片。9B 自行安排自然長度，不強制湊滿。

毛片保留原生音訊，可直接播放驗收。局部修改只影響勾選片段；留空只換 Seed，成功後另存完整新版。開啟已存作品可續拍，不需重新上傳。

作品獨立儲存在 `MyDrive/BananaFilmStudio/films/工作編號/final.mp4`；歷史版為 `final_v001.mp4` 等。未存 Drive 的資料可能隨 Colab 回收消失。

末幀模式將上一段末幀加入參考圖，不是硬鎖首幀，也不繼承動作 latent。跨段聲線、環境音及音樂可能跳接，請看片驗收。不要與其他 MV 任務共用 ComfyUI 同時生成。
'''),code('''#@title 🔍 診斷
subprocess.run(['nvidia-smi'])
for name in ('comfyui','banana_film'):
    log=Path('/content')/(name+'.log')
    print(name,log.read_text(errors='replace')[-4000:] if log.exists() else '尚無紀錄')
'''),code('''#@title 🧯 手動關閉 ComfyUI（全部執行只顯示按鈕）
runtime.show_shutdown_control(globals())
''')]
for i,cell in enumerate(cells):cell['id']=f'banana-film-{i:02d}'
nb={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'name':'python3','display_name':'Python 3'},'language_info':{'name':'python'},'colab':{'provenance':[],'gpuType':'G4'},'accelerator':'GPU'},'cells':cells}
(ROOT/'Banana_Film_Studio.ipynb').write_text(json.dumps(nb,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')

