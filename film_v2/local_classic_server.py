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
import urllib.parse
import uuid
from http.server import ThreadingHTTPServer

os.environ.setdefault("BANANA_DATA", r"F:\BANANA_FILM_5070_STUDIO\Media")
os.environ.setdefault("BANANA_PORT", "8195")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from banana_mv import film_server as colab, server as app

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


class Handler(colab.Handler):
    """Colab production routes remain inherited verbatim."""

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/film", "/mv"):
            # The only HTML change is loading the local-only Git version badge.
            # Everything else is the exact Colab film.html.
            html = (app.WEB / "film.html").read_text(encoding="utf-8")
            marker = "</body>"
            assert html.count(marker) == 1
            html = html.replace(
                marker, '<script defer src="/film-5070-build.js"></script>' + marker)
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
        if path == "/api/health":
            return self.send_json({
                "service": "banana-film",
                "engine": "colab_film",
                "variant": "rtx5070-fdrive",
                "port": app.backend.PORT,
                "data_root": str(app.backend.DATA.resolve()),
                "version": SERVER_BUILD,
                "instance": SERVER_INSTANCE,
                "busy": app.GPU_LOCK.locked()
            })
        return super().do_GET()


def main():
    # This is exactly Colab Film's project directory, just on the F: data root.
    # Keep older Python-Owned V2 project data in Media/films_v2 untouched.
    app.RUNS = app.backend.DATA / "films"
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
    ThreadingHTTPServer(("127.0.0.1", app.backend.PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
