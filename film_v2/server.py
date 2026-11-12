"""Standalone V2 Film HTTP API, isolated from legacy film and MV routes."""
import json
import os
from pathlib import Path
import sys
import urllib.parse
from http.server import ThreadingHTTPServer

os.environ.setdefault("BANANA_DATA", "/content/banana_film_v2_data")
os.environ.setdefault("BANANA_PORT", "8194")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from banana_mv import server as app
from banana_mv.http_server import WebHandler
from film_v2 import service

WEB = Path(__file__).parent / "web"


class Handler(WebHandler):
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        path = url.path
        try:
            if path in ("/", "/film", "/film-v2"):
                return self.send_file(WEB / "index.html")
            if path == "/app.js":
                return self.send_file(WEB / "app.js")
            if path == "/api/health":
                return self.send_json({"service": "banana-film-v2",
                                       "engine": service.ENGINE, "port": app.backend.PORT})
            if path == "/api/film-v2/projects":
                return self.send_json(service.projects())
            params = dict(urllib.parse.parse_qsl(url.query))
            if path == "/api/film-v2/status":
                return self.send_json(service.get(params["id"]))
            if path == "/api/film-v2/clip":
                version = int(params["version"]) if "version" in params else None
                return self.send_file(service.clip(params["id"], int(params["index"]), version))
            if path == "/api/film-v2/file":
                version = int(params["version"]) if "version" in params else None
                return self.send_file(service.file(params["id"], version))
            return self.send_error(404)
        except Exception as exc:
            return self.send_json({"error": str(exc)}, 400)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            if path == "/api/upload":
                if not app.GPU_LOCK.acquire(blocking=False):
                    raise ValueError("目前正在製片，請完成後再上傳。")
                try:
                    name = urllib.parse.unquote(self.headers.get("X-Filename", ""))
                    return self.send_json(app.backend.add_asset(
                        app.backend.load_config(), name, self.read_body(), image_only=True))
                finally:
                    app.GPU_LOCK.release()
            if not path.startswith("/api/film-v2/"):
                return self.send_error(404)
            body = self.body_json()
            if path == "/api/film-v2/start":
                return self.send_json(service.start(body), 202)
            if path == "/api/film-v2/approve":
                return self.send_json(service.approve(body["id"], body.get("revision"),
                                                      body.get("draft")), 202)
            if path == "/api/film-v2/revise":
                return self.send_json(service.revise(body["id"], body.get("revision"),
                                                     body.get("instruction"), body.get("draft")))
            if path == "/api/film-v2/resume":
                return self.send_json(service.resume(body["id"]), 202)
            if path == "/api/film-v2/retake":
                return self.send_json(service.retake(body["id"], body["index"],
                                                     body.get("instruction", "")), 202)
            if path == "/api/film-v2/adopt":
                return self.send_json(service.adopt(body["id"], body["index"], body["version"]))
            if path == "/api/film-v2/stop":
                return self.send_json(service.stop(body["id"]))
            return self.send_error(404)
        except Exception as exc:
            return self.send_json({"error": str(exc)}, 400)


def main():
    app.RUNS = app.backend.DATA / "films_v2"
    app.RUNS.mkdir(parents=True, exist_ok=True)
    app.backend.LIBRARY.mkdir(parents=True, exist_ok=True)
    for path in app.RUNS.glob("*/status.json"):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
            if job.get("engine") != service.ENGINE:
                continue
            if job["status"] not in ("done", "error", "cancelled", "interrupted", "script_ready"):
                job.update(status="interrupted",
                           error="Colab 執行階段已重啟；既有劇本與完成片段保留。")
                app.write_state(job)
        except (OSError, ValueError, KeyError):
            continue
    print(f"BANANA FILM V2 on http://127.0.0.1:{app.backend.PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", app.backend.PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
