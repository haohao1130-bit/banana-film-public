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


class Handler(app.Handler):
    def do_GET(self):
        path=urllib.parse.urlparse(self.path).path
        if path in ('/','/film','/mv'):return self.send_file(app.WEB/'film.html')
        if path in ('/film.js','/film_review.js','/kitchen.js'):return self.send_file(app.WEB/path.lstrip('/'))
        if path=='/api/health':return self.send_json({'service':'banana-film','standalone':True})
        return super().do_GET()

    def do_POST(self):
        path=urllib.parse.urlparse(self.path).path
        if path=='/api/upload':
            try:
                if not app.GPU_LOCK.acquire(blocking=False):
                    raise ValueError('短片執行中，請完成後再上傳參考圖。')
                try:
                    filename=urllib.parse.unquote(self.headers.get('X-Filename',''))
                    return self.send_json(app.backend.add_asset(app.backend.load_config(),filename,self.read_body(),image_only=True))
                finally:
                    app.GPU_LOCK.release()
            except Exception as error:return self.send_json({'error':str(error)},400)
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
        if job['status'] not in ('done','error','cancelled','interrupted','script_ready'):
            job.update(status='interrupted',error='執行階段重啟，已完成片段保留。');app.write_state(job)
    print(f'Banana Film Studio on http://127.0.0.1:{app.backend.PORT}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',app.backend.PORT),Handler).serve_forever()


if __name__=='__main__':main()

