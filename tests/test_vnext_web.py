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
            content_type = response.getheader("Content-Type", "")
            return response.status, json.loads(content) if "application/json" in content_type else content
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

    def test_first_three_reference_slots_are_contiguous(self):
        pid = self.create()
        folder = web.project(pid)
        for slot in (1, 2, 3):
            (folder / f"reference_{slot:02d}.png").write_bytes(b"fixture")
        paths = web.images(folder)
        self.assertEqual([p.name for p in paths],
                         ["reference_01.png", "reference_02.png", "reference_03.png"])

    def test_three_pngs_upload_by_actual_http_then_prepare(self):
        pid = self.create()
        png = io.BytesIO()
        Image.new("RGB", (32, 32), "yellow").save(png, format="PNG")
        for slot in (1, 2, 3):
            code, receipt = self.ask(
                "POST", f"/api/upload?id={pid}&slot={slot}",
                png.getvalue(), {"Content-Type": "application/octet-stream"})
            self.assertEqual(code, 201)
            self.assertEqual(receipt["slot"], slot)
        code, project = self.ask("GET", f"/api/project?id={pid}")
        self.assertEqual(code, 200)
        self.assertEqual(project["picture_slots"], [1, 2, 3])
        self.assertEqual([p.name for p in web.images(web.project(pid))],
                         [f"reference_{n:02d}.png" for n in (1, 2, 3)])
        with patch.object(web, "spawn") as spawn:
            code, result = self.ask("POST", f"/api/prepare?id={pid}", {})
        self.assertEqual(code, 202)
        self.assertEqual(result["status"], "preparing")
        spawn.assert_called_once()

    def test_missing_middle_reference_slot_is_rejected(self):
        pid = self.create()
        folder = web.project(pid)
        for slot in (1, 3):
            (folder / f"reference_{slot:02d}.png").write_bytes(b"fixture")
        with self.assertRaisesRegex(ValueError, "格號需連續"):
            web.images(folder)

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

    def test_continuation_accepts_native_ref2va_node(self):
        graph={
            "7":{"class_type":"MiniMaxH3ReferenceToVideo","inputs":{"length":226}},
            "3":{"class_type":"VAELoader","inputs":{}},
            "9":{"class_type":"BasicGuider","inputs":{"conditioning":["7",0]}},
        }
        names=[f"image_{i}.png" for i in range(5)]
        add_audio_t8_motion_guide(graph,names,226)
        self.assertEqual(graph["7"]["inputs"]["length"],243)
        self.assertEqual(graph["9"]["inputs"]["conditioning"],["motion_guide",0])
        self.assertEqual(graph["motion_guide"]["inputs"]["image"],["motion_batch_4",0])
        self.assertEqual(graph["motion_guide"]["inputs"]["positive"],["7",0])
        self.assertEqual(graph["motion_guide"]["inputs"]["latent"],["7",1])
        self.assertEqual(graph["motion_guide"]["inputs"]["vae"],["3",0])

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
