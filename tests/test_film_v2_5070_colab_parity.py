"""5070 Film entry parity with original Colab Banana_Film_Studio.ipynb.

No model or GPU required: checks inherited Colab routes and that the HTTP
response is the canonical UI (only one appended local build-number script).
"""
import http.client
import re
from http.server import ThreadingHTTPServer
from pathlib import Path
import threading
import unittest

from banana_mv import film_server as colab, server as mv
from film_v2 import local_classic_server as local

ROOT = Path(__file__).resolve().parents[1]


class Film5070ColabParityTests(unittest.TestCase):
    def test_original_colab_handler_is_used_for_every_production_action(self):
        self.assertTrue(issubclass(local.Handler, colab.Handler))
        # 5070 intentionally wraps POST only to handle its own restart route.
        # Every production action still delegates to the canonical handler.
        self.assertIn("return super().do_POST()", (ROOT / "film_v2/local_classic_server.py").read_text(encoding="utf-8"))
        source = "\\n".join(
            (ROOT / item).read_text(encoding="utf-8")
            for item in ("banana_mv/web/film.js", "banana_mv/web/film_review.js")
        )
        for required in (
                "api/film/plan", "api/film/",
                "api/mv/retake", "api/mv/condense",
                "api/mv/select-take", "api/mv/resume", "api/mv/projects"):
            self.assertIn(required, source)

    def test_real_f_drive_library_and_projects_are_read_directly(self):
        runtime = (ROOT / "film_v2/local_classic_server.py").read_text(encoding="utf-8")
        services = (ROOT / "banana_mv/services.py").read_text(encoding="utf-8")
        self.assertIn('if os.environ.get("BANANA_FILM_LIBRARY"):', runtime)
        self.assertIn('app.backend.LIBRARY = Path(os.environ["BANANA_FILM_LIBRARY"])', runtime)
        self.assertIn('app.RUNS = Path(os.environ["BANANA_FILM_PROJECTS"])', runtime)
        # 沒設 BANANA_FILM_LIBRARY 時，共用預設仍是 DATA/'library'。
        self.assertIn("else DATA/'library'", services, "shared MV service default must stay unchanged")

    def test_colab_html_is_authoritative_not_simplified_v2(self):
        canonical = (ROOT / "banana_mv/web/film.html").read_text(encoding="utf-8")
        local_source = (ROOT / "film_v2/local_classic_server.py").read_text(
            encoding="utf-8")
        launcher = (ROOT / "tools/start_film_v2_5070.ps1").read_text(
            encoding="utf-8")
        self.assertIn('app.WEB / "film.html"', local_source)
        self.assertIn('film_v2.local_classic_server', launcher)
        self.assertIn('app.RUNS = app.backend.DATA / "films"', local_source)
        self.assertIn("films_v2", launcher)
        self.assertIn("film_review.js", canonical)
        self.assertRegex(canonical, r'src="kitchen\.js(?:\?v=[^"]*)?"')  # 允許快取版本號
        self.assertIn("BananaKitchen", (ROOT / "banana_mv/web/film.js").read_text(encoding="utf-8"))
        self.assertIn("film.js", canonical)
        self.assertIn("projector", canonical)
        self.assertIn('id="script-review"', canonical)
        self.assertIn('id="references"', canonical)
        self.assertNotIn("film_v2/web/index.html", local_source)

    def test_real_http_routes_serve_original_colab_ui_and_version(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), local.Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            def request(path):
                conn = http.client.HTTPConnection(
                    "127.0.0.1", server.server_address[1], timeout=4)
                try:
                    conn.request("GET", path)
                    response = conn.getresponse()
                    return response.status, response.read().decode("utf-8")
                finally:
                    conn.close()

            code, html = request("/")
            self.assertEqual(code, 200)
            canonical = (mv.WEB / "film.html").read_text(encoding="utf-8")
            # 原版 UI 一字不改，只在 </body> 前多插一行本機版本號腳本（允許快取版本號）。
            injected = re.findall(r'<script defer src="/film-5070-build\.js(?:\?v=[^"]*)?"></script>', html)
            self.assertEqual(len(injected), 1)
            self.assertEqual(html.replace(injected[0], ""), canonical)
            for path, local_name in (
                    ("/film.js", "film.js"),
                    ("/film_review.js", "film_review.js"),
                    ("/kitchen.js", "kitchen.js")):
                code, content = request(path)
                self.assertEqual(code, 200)
                self.assertEqual(
                    content, (mv.WEB / local_name).read_text(encoding="utf-8"))
            code, health = request("/api/health")
            self.assertEqual(code, 200)
            self.assertIn('"engine": "colab_film"', health)
            self.assertIn('"variant": "rtx5070-fdrive"', health)
            self.assertIn('"version"', health)
            code, _ = request("/film-5070-build.js")
            self.assertEqual(code, 200)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=4)


if __name__ == "__main__":
    unittest.main()
