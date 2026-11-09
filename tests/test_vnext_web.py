"""Offline integration checks for independent VNext web UI and API."""
import http.client
import io
import json
from pathlib import Path
from http.server import ThreadingHTTPServer
import tempfile
import threading
import unittest
from unittest.mock import patch
from PIL import Image

from banana_mv import vnext_server as web
from banana_mv.film_vnext.motion import add_audio_t8_motion_guide


class VNextWebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        patcher = patch.object(web, "ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        (self.root / "projects").mkdir()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    def ask(self, method, path, data=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_port, timeout=10)
        try:
            payload = json.dumps(data).encode("utf-8") if isinstance(data,dict) else data
            headers = dict(headers or {})
            if isinstance(data,dict):
                headers["Content-Type"] = "application/json"
            conn.request(method, path, body=payload, headers=headers)
            response = conn.getresponse()
            content = response.read()
            return response.status, json.loads(content) if path.startswith("/api/") and not content.startswith(b"<!doctype") else content
        finally:
            conn.close()

    def create(self):
        status, data = self.ask("POST","/api/create",{
            "story": "小語與蕉大師切磋，動作連貫，不擅自收尾。",
            "max_seconds": 30, "chain5": True, "width": 720, "height": 1280,
        })
        self.assertEqual(status, 201)
        return data["id"]

    def test_frontend_and_health(self):
        status, body = self.ask("GET","/")
        self.assertEqual(status, 200)
        self.assertIn(b"vnext.js", body)
        status, data = self.ask("GET","/api/health")
        self.assertEqual(data["service"],"banana-film-vnext")

    def test_project_creation_and_picture_upload(self):
        pid = self.create()
        status, data = self.ask("GET","/api/project?id="+pid)
        self.assertEqual(data["status"],"draft")
        raw = io.BytesIO()
        Image.new("RGB",(32,32),"orange").save(raw,format="PNG")
        status, result = self.ask("POST",f"/api/upload?id={pid}&slot=1",
                                  raw.getvalue(),{"Content-Type":"application/octet-stream"})
        self.assertEqual(status,201)
        self.assertEqual(result["slot"],1)
        status, data = self.ask("GET",f"/api/project?id={pid}")
        self.assertEqual(data["picture_slots"],[1])
        self.assertEqual(self.ask("GET",f"/api/image?id={pid}&slot=1")[0],200)

    def test_no_render_before_sealed_plan(self):
        pid=self.create()
        status, data=self.ask("POST",f"/api/render?id={pid}",{})
        self.assertEqual(status,400)
        self.assertIn("error",data)

    def test_safe_ids_and_file_limits(self):
        status, data=self.ask("GET","/api/project?id=../../etc/passwd")
        self.assertEqual(status,400)
        self.assertIn("error",data)
        status, data=self.ask("POST","/api/create",{"story":"x","width":1})
        self.assertEqual(status,400)

    def test_continuation_accepts_native_audio_t8_node(self):
        graph={
            "7":{"class_type":"MiniMaxH3AudioConditioningT8","inputs":{"length":226}},
            "9":{"class_type":"BasicGuider","inputs":{"conditioning":["7",0]}},
        }
        names=[f"image_{i}.png" for i in range(5)]
        add_audio_t8_motion_guide(graph,names,226)
        self.assertEqual(graph["7"]["inputs"]["length"],243)
        self.assertEqual(graph["9"]["inputs"]["conditioning"],["motion_guide",0])
        self.assertEqual(graph["motion_guide"]["inputs"]["image"],["motion_batch_4",0])

    def test_frontend_assets_have_live_event_and_video_controls(self):
        js=(web.WEB/"vnext.js").read_text(encoding="utf-8")
        html=(web.WEB/"vnext.html").read_text(encoding="utf-8")
        for marker in ("/api/create","/api/upload","/api/prepare","/api/plan",
                       "/api/render","/api/clip","/api/film","/api/projects"):
            self.assertIn(marker,js)
        for ident in ("story","references","shot-list","film-player",
                      "confirm-render","prepare","render","projects"):
            self.assertIn(f'id="{ident}"',html)


if __name__=="__main__":
    unittest.main()
