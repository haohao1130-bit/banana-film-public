"""RTX5070 Windows entrypoint for the EXACT original Colab Banana Film Studio.

Serves banana_mv/web/film.html, film.js and film_review.js unchanged, plus an
additive build label. Production/API actions are inherited from the same
banana_mv.film_server.Handler used by Banana_Film_Studio.ipynb.
The separate Python-Owned V2 implementation is retained, not overwritten.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import urllib.parse
import uuid
from http.server import ThreadingHTTPServer

os.environ.setdefault("BANANA_DATA", r"F:\BANANA_FILM_5070_STUDIO\Media")
os.environ.setdefault("BANANA_PORT", "8193")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from banana_mv import film_server as colab, server as app
from banana_mv import comfy as comfy_client
from banana_mv.room_switch import same_origin_control
from film_v2.live_progress import LiveProgress

# Only this Film entrypoint overrides its shared storage. Keep the public
# backend's original DATA/library default for MV and legacy deployments.
if os.environ.get("BANANA_FILM_LIBRARY"):
    app.backend.LIBRARY = Path(os.environ["BANANA_FILM_LIBRARY"])

if app.backend.DATA.name.lower() == "media":
    os.environ.setdefault("BANANA_FINISHED_VIDEOS", str(app.backend.DATA.parent / "videos"))

ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "film_v2" / "web" / "build_5070.js"


def detect_build_version():
    """Git revision at process startup, not a guessed or hardcoded release."""
    def git(*args):
        try:
            result = subprocess.run(
                ["git", *args], cwd=ROOT, capture_output=True, text=True,
                check=True, timeout=3)
            return result.stdout.strip() or "unknown"
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return "unknown"
    if not (ROOT / ".git").exists():
        return {"branch": "unknown", "commit": "unknown"}
    return {"branch": git("symbolic-ref", "--quiet", "--short", "HEAD"),
            "commit": git("rev-parse", "--short=9", "HEAD")}


SERVER_BUILD = detect_build_version()
SERVER_INSTANCE = uuid.uuid4().hex


RESTART_LAUNCHER = os.environ.get("BANANA_FILM_RESTART_LAUNCHER")
LIVE_PROGRESS = LiveProgress()


class Handler(colab.Handler):
    """Colab production routes remain inherited verbatim."""

    def comfy_progress(self, job_id):
        snapshot = LIVE_PROGRESS.snapshot()
        prompt_id = snapshot.pop("prompt_id", None)
        if (snapshot["connection"] == "connected" and prompt_id
                and comfy_client.active_prompt(job_id, prompt_id)):
            return snapshot
        return None

    def do_POST(self):
        if self.path == '/api/5070/switch':
            from banana_mv.room_switch import switch
            return switch(self, 'mv', app.backend, app.GPU_LOCK)
        if self.path != "/api/film/restart":
            return super().do_POST()
        if not same_origin_control(self.headers, "film-restart"):
            return self.send_error(403)
        if not RESTART_LAUNCHER or not Path(RESTART_LAUNCHER).is_file():
            return self.send_error(503, "Restart launcher unavailable")
        if not app.GPU_LOCK.acquire(blocking=False):
            return self.send_error(409, "Film job is active")
        try:
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", RESTART_LAUNCHER, "-WaitForFilmPid", str(os.getpid()),
                 "-NoBrowser"],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        except OSError:
            app.GPU_LOCK.release()
            return self.send_error(500, "Could not start Film launcher")
        try:
            return self.send_json({"ok": True})
        finally:
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    def do_GET(self):
        if self.path == '/api/5070/switch':
            from banana_mv.room_switch import launcher
            return self.send_json({'available': bool(launcher('mv', app.backend.PORT)),
                                   'busy': app.GPU_LOCK.locked()})
        path = urllib.parse.urlparse(self.path).path
        # "/" 交給上層：蕉彌鐵板燒是首頁；蕉其林中餐廳在 /film。
        if path in ("/film", "/mv"):
            # The only HTML change is loading the local-only Git version badge.
            # Everything else is the exact Colab film.html.
            html = (app.WEB / "film.html").read_text(encoding="utf-8")
            marker = "</body>"
            assert html.count(marker) == 1
            html = html.replace(
                marker, '<script defer src="/film-5070-build.js?v=live-progress"></script>' + marker)
            data = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)
            return
        if path == "/film-5070-build.js":
            return self.send_file(BUILD_SCRIPT)
        if path == "/api/film/progress":
            snapshot = LIVE_PROGRESS.snapshot()
            snapshot["busy"] = app.GPU_LOCK.locked()
            snapshot.pop("prompt_id", None)
            return self.send_json(snapshot)
        if path == "/api/health":
            return self.send_json({
                "service": "banana-film",
                "engine": "colab_film",
                "variant": "rtx5070-fdrive",
                "port": app.backend.PORT,
                "data_root": str(app.backend.DATA.resolve()),
                "version": SERVER_BUILD,
                "instance": SERVER_INSTANCE,
                "busy": app.GPU_LOCK.locked(),
                "restart_available": bool(RESTART_LAUNCHER and Path(RESTART_LAUNCHER).is_file())
            })
        return super().do_GET()


def main():
    # Legacy installs keep DATA/films. The direct F-drive launcher passes
    # BANANA_FILM_PROJECTS to use F:\\BANANAFILM\\projects as the REAL folder.
    # No junction, relocation, merge, or deletion of existing projects.
    app.RUNS = app.backend.DATA / "films"
    if os.environ.get("BANANA_FILM_PROJECTS"):
        app.RUNS = Path(os.environ["BANANA_FILM_PROJECTS"])
    app.RUNS.mkdir(parents=True, exist_ok=True)
    app.backend.LIBRARY.mkdir(parents=True, exist_ok=True)
    for path in app.RUNS.glob("*/status.json"):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
            if job.get("request", {}).get("production") != "film":
                continue
            if job["status"] not in (
                    "done", "error", "cancelled", "interrupted", "script_ready"):
                job.update(
                    status="interrupted",
                    error="本機後端重啟，已完成片段保留，可續跑。")
                app.write_state(job)
        except (OSError, ValueError, KeyError):
            continue
    print(
        f"BANANA FILM / COLAB-PARITY on http://127.0.0.1:{app.backend.PORT}",
        flush=True)
    comfy_client.on_prompt_queued = LIVE_PROGRESS.queued
    LIVE_PROGRESS.start(app.backend.load_config()["comfy_url"], comfy_client.CLIENT_ID)
    with ThreadingHTTPServer(("127.0.0.1", app.backend.PORT), Handler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
