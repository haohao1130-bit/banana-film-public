"""Dedicated film HTTP entry. Its data, port, UI and creation endpoint are separate."""
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('BANANA_DATA','/content/banana_film_data')
os.environ.setdefault('BANANA_PORT','8191')

import json
import urllib.parse
from http.server import ThreadingHTTPServer
from banana_mv import server as app, film
from banana_mv.takes import describe


# 同一份網頁給 Colab 與 5070 用；各環境的預設值由伺服器告訴網頁。
# Colab：沒有 RTX VSR（不能升頻 2K），所以直接 720P 生成。
PROFILE_DEFAULTS = {
    'colab': {'profile': 'colab', 'resolution': 720, 'sampling_steps': 6, 'segment_seconds': 10,
              'auto_director': True, 'rewriter_thinking': True, 'upscale_available': False},
    '5070': {'profile': '5070', 'upscale_available': True},
}


def profile_defaults():
    profile = os.environ.get('BANANA_FILM_PROFILE', 'colab')
    return dict(PROFILE_DEFAULTS.get(profile, PROFILE_DEFAULTS['colab']))


class Handler(app.Handler):
    def comfy_progress(self, job_id):
        return None

    def do_GET(self):
        path=urllib.parse.urlparse(self.path).path
        # 蕉彌鐵板燒是首頁；蕉其林中餐廳（手動介面）改從 /film 進入。
        if path in ('/film','/mv'):return self.send_file(app.WEB/'film.html')
        if path in ('/film.js','/film_review.js','/kitchen.js'):return self.send_file(app.WEB/path.lstrip('/'))
        if path in ('/','/teppan'):return self.send_file(app.WEB/'teppan.html')
        if path in ('/teppan.html','/teppan.js','/teppan.css'):return self.send_file(app.WEB/path.lstrip('/'))
        if path in ('/api/film/kitchen/projects', '/api/mv/projects'):
            return self.send_json(app.projects(kitchen=(path == '/api/film/kitchen/projects')))
        if path=='/api/mv/status':
            job_id=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get('id',[''])[0]
            try:
                job=app.read_state(job_id)
            except FileNotFoundError:
                return self.send_json({'error':'找不到作品狀態','code':'film_state_missing'},404)
            except ValueError as error:
                return self.send_json({'error':str(error)},400)
            view=describe(job)
            if job.get('kitchen') and job['status'] in ('planning_story', 'casting', 'running', 'retaking'):
                view['comfy_progress']=self.comfy_progress(job_id)
            return self.send_json(view)
        if path=='/api/film/kitchen/presets':
            from banana_mv import teppan_presets
            return self.send_json(teppan_presets.list_presets())
        if path=='/api/film/kitchen/asset':
            try:
                from banana_mv import teppan_presets
                asset_id=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get('id',[''])[0]
                return self.send_file(teppan_presets.image_asset(asset_id)[1])
            except (ValueError,OSError) as error:
                return self.send_json({'error':str(error)},404)
        if path=='/api/health':return self.send_json({'service':'banana-film','standalone':True})
        if path=='/api/film/defaults':return self.send_json(profile_defaults())
        return super().do_GET()

    def do_POST(self):
        path=urllib.parse.urlparse(self.path).path
        if path=='/api/upload':
            try:
                # Consume the incoming body before a busy response so mobile
                # clients can receive the JSON instead of a closed connection.
                body=self.read_body()
                if not app.GPU_LOCK.acquire(blocking=False):
                    raise ValueError('短片執行中，請完成後再上傳參考圖。')
                try:
                    filename=urllib.parse.unquote(self.headers.get('X-Filename',''))
                    asset=app.backend.add_asset(app.backend.load_config(),filename,body,image_only=True)
                finally:
                    app.GPU_LOCK.release()
                return self.send_json(asset)
            except Exception as error:return self.send_json({'error':str(error)},400)
        if path.startswith('/api/film/kitchen/'):
            try:
                from banana_mv import film_kitchen
                action = path.rsplit('/', 1)[-1]
                body = self.body_json()
                if action in ('preset_save', 'preset_delete'):
                    from banana_mv import teppan_presets
                    handler = teppan_presets.save_preset if action == 'preset_save' else teppan_presets.delete_preset
                    return self.send_json(handler(body))
                if action == 'estimate':
                    from banana_mv.teppan_timing import estimate_menu
                    return self.send_json(estimate_menu(body.get('menu')))
                if action == 'start':
                    defaults = {'sampling_steps': 6, 'rewriter_thinking': True, 'width': 854,
                                'segment_seconds': 10, 'max_seconds': 10, 'mode': 'chain',
                                'upscale_resolution': 1440}
                    return self.send_json(film.start(defaults | body | {'kitchen_mode': True}))
                if action in ('append', 'repeat', 'adopt', 'serve'):
                    return self.send_json(film_kitchen.update(body, action))
                if action == 'continue':
                    return self.send_json(film_kitchen.continue_from(body))
                if action in ('clip_prompt', 'clip_rethink'):
                    return self.send_json(film_kitchen.fix_stuck_clip(body, action))
                if action in ('cast', 'shared'):
                    return self.send_json(film_kitchen.edit_cast(body, action))
                return self.send_json({'error': '找不到此操作。'}, 404)
            except Exception as error:
                return self.send_json({'error': str(error)}, 400)
        if path in ('/api/film/start','/api/film/plan'):
            try:
                body=self.body_json()
                if path.endswith('/plan'):body['script_review']=True
                return self.send_json(film.start(body))
            except Exception as error:return self.send_json({'error':str(error)},400)
        if path in ('/api/film/script','/api/film/render'):
            try:
                body=self.body_json()
                return self.send_json(film.save_script(body['id'],body.get('script'),body.get('revision'),render=path.endswith('/render')))
            except Exception as error:return self.send_json({'error':str(error)},400)
        if path=='/api/film/revise':
            try:
                body=self.body_json()
                return self.send_json(film.revise_script(body['id'],body.get('script'),body.get('revision'),body.get('instruction')))
            except Exception as error:return self.send_json({'error':str(error)},400)
        if path=='/api/mv/start':return self.send_json({'error':'此入口只建立短片，請使用短片表單。'},400)
        return super().do_POST()


def main():
    app.RUNS=app.backend.DATA/'films'
    app.RUNS.mkdir(parents=True,exist_ok=True)
    app.backend.LIBRARY.mkdir(parents=True,exist_ok=True)
    for path in app.RUNS.glob('*/status.json'):
        job=json.loads(path.read_text(encoding='utf-8'))
        if job['status'] not in ('done','error','cancelled','interrupted','script_ready','kitchen_ready'):
            job.update(status='interrupted',error='執行階段重啟，已完成片段保留。');app.write_state(job)
    print(f'Banana Film Studio on http://127.0.0.1:{app.backend.PORT}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',app.backend.PORT),Handler).serve_forever()


if __name__=='__main__':main()

