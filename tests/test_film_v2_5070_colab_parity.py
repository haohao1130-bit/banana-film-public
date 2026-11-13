"""5070 Film entry parity with original Colab Banana_Film_Studio.ipynb.

No model or GPU required: checks inherited Colab routes and that the HTTP
response is the canonical UI (only one appended local build-number script).
"""
import http.client
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
        self.assertIs(local.Handler.do_POST, colab.Handler.do_POST)
        source = "
".join(
            (ROOT / item).read_text(encoding="utf-8")
            for item in ("banana_mv/web/film.js", "banana_mv/web/film_review.js")
        )
        for required in (
                "api/film/plan", "api/film/render", "api/film/revise",
                "api/mv/retake", "api/mv/condense",
                "api/mv/select-take", "api/mv/resume", "api/mv/projects"):
            self.assertIn(required, source)

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
            self.assertEqual(
                html, canonical.replace(
                    "</body>",
                    '<script defer src="/film-5070-build.js"></script></body>'))
            for path, local_name in (
                    ("/film.js", "film.js"),
                    ("/film_review.js", "film_review.js")):
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
