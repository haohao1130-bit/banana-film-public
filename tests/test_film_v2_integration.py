"""Offline V2 integration tests: no model download, no network, no GPU."""
import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

os.environ.setdefault("BANANA_DATA", str(Path(tempfile.gettempdir()) / "banana-film-v2-unit-data"))

from film_v2 import service
from film_v2.directors import _normalize_camera, source_to_picture
from film_v2.production import compile_film, FilmPlanError


def screenplay():
    return {
        "title": "夜班", "shared_setup": "A is adult courier <Picture 1>, B is adult manager.",
        "initial_state": {
            "characters": {"A": {"location": "desk"}, "B": {"location": "hall"}},
            "props": {"letter": {"holder": "desk"}}
        },
        "beats": [
            {"id": "b1", "action": "A picks up the sealed letter", "actors": ["A"],
             "seconds_hint": 6,
             "changes": {"props": {"letter": {"holder": "A"}}}},
            {"id": "b2", "action": "A turns to the hall", "actors": ["A"],
             "seconds_hint": 6, "cut_after": True},
            {"id": "b3", "action": "B comes into the room", "actors": ["B"],
             "seconds_hint": 6,
             "changes": {"characters": {"B": {"location": "room"}}}}
        ]
    }


def req():
    return {"prompt": "A 把信封交給 B。", "image_slots": [None] * 9,
            "max_seconds": 30, "segment_seconds": 15, "mode": "chain5",
            "sound_mode": "ambient", "auto_director": True,
            "script_review": True}


class V2IntegrationTests(unittest.TestCase):
    def test_new_v2_request_has_separate_engine_and_hard_ceiling(self):
        validated = service._request(req())
        self.assertEqual(validated["film_engine"], service.ENGINE)
        self.assertEqual(validated["production"], "film")
        self.assertEqual(validated["max_seconds"], 30.)
        self.assertEqual(validated["segment_seconds"], 15.)
        self.assertEqual(validated["mode"], "chain5")
        with self.assertRaises(ValueError):
            service._request(dict(req(), max_seconds=181))

    def test_fixed_reference_positions_do_not_shift(self):
        ids = [None, "id-second", None, "id-fourth"] + [None] * 5
        self.assertEqual(source_to_picture("@圖片2 看著 @圖片4", ids),
                         "<Picture 1> 看著 <Picture 2>")
        with self.assertRaises(FilmPlanError):
            source_to_picture("@圖片1", ids)

    def test_compiler_plan_and_http_draft_share_event_ids(self):
        plan = compile_film(screenplay(), max_seconds=30)
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            job = {"id": "123456789abc", "request": {"project_name": ""},
                   "segments": [], "seed": 1}
            with patch.object(service.app, "job_dir", return_value=work), \
                 patch.object(service.app, "write_state"):
                service._apply_plan(job, screenplay(), plan)
                self.assertEqual(job["segments"][0]["event_ids"], ["b1", "b2"])
                self.assertEqual(job["segments"][1]["event_ids"], ["b3"])
                self.assertEqual(job["segments"][1]["state_at_open"]["props"]["letter"]["holder"], "A")
                self.assertEqual(json.loads((work / "v2_plan.json").read_text())["engine"], "python_owned_film_v2")
                self.assertEqual(job["script_draft"]["title"], "夜班")

    def test_six_section_native_camera_validation(self):
        text = ("subject_definitions:\n<Subject 1>: adult courier <Picture 1>\n"
                "summary:\nA courier inspects a letter.\n"
                "retention_analysis:\nPreserve Picture 1.\n"
                "detailed_description:\n[Shot 1] A courier lifts a letter.\n"
                "[Shot 2] At 00:02.000, A courier observes the envelope.\n"
                "overall_soundscape:\nRoom tone and paper sounds.\n"
                "non_diegetic_music:\nNone.\n")
        self.assertIn("[Shot 1]", _normalize_camera(text, 1, 6, "ambient"))
        with self.assertRaises(FilmPlanError):
            _normalize_camera(text.replace("Room tone", "<Audio 1>"), 1, 6, "ambient")
        with self.assertRaises(FilmPlanError):
            _normalize_camera(text.replace("<Picture 1>", "<Picture 2>"), 1, 6, "ambient")
        with self.assertRaises(FilmPlanError):
            _normalize_camera(text.replace("00:02.000", "00:10.000"), 1, 6, "ambient")

    def test_render_graph_uses_native_audio_and_never_calls_legacy_planner(self):
        document = screenplay()
        plan = compile_film(document, max_seconds=30)
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            (work / "sources").mkdir()
            job = {
                "id": "123456789abc", "engine": service.ENGINE, "seed": 1,
                "request": dict(service._request(req()), mode="independent"),
                "size": (854, 480), "images_comfy": [], "segments": [],
                "duration": plan["duration_seconds"], "sources": {"images": []},
                "status": "running"
            }
            with patch.object(service.app, "job_dir", return_value=work), \
                 patch.object(service.app, "write_state"):
                service._apply_plan(job, document, plan)
            class FakeBackend:
                @staticmethod
                def queue_prompt(cfg, graph):
                    self_graph.append(graph)
                    return "pid"
            self_graph = []
            def fake_download(cfg, entry, dest):
                Path(dest).write_bytes(b"video placeholder")
            def fake_trim(src, dest, frames, prefix_frames=0):
                Path(dest).write_bytes(b"native AV placeholder")
            with patch.object(service.app, "job_dir", return_value=work), \
                 patch.object(service.app, "build_workflow",
                              return_value={"7": {"class_type": "MiniMaxH3ReferenceToVideo",
                                                 "inputs": {}},
                                            "16": {"inputs": {}}}), \
                 patch.object(service.app, "graph_options", return_value={"native_audio": True}), \
                 patch.object(service.app, "preflight"), \
                 patch.object(service.app, "wait_generation", return_value={"outputs": {}}), \
                 patch.object(service.app, "video_info", return_value={"filename": "fake.mp4"}), \
                 patch.object(service.app, "valid_part", return_value=True), \
                 patch.object(service.backend, "queue_prompt", side_effect=FakeBackend.queue_prompt), \
                 patch.object(service.backend, "comfy_download", side_effect=fake_download), \
                 patch.object(service, "trim_native", side_effect=fake_trim), \
                 patch.object(service, "require_audio"), \
                 patch.object(service, "write_camera", return_value="valid prompt"), \
                 patch.object(service.app, "write_state"):
                service._render_one(job, {"comfy_input_dir": temp}, [],
                                    plan, 0, 1, None)
            self.assertEqual(len(self_graph), 1)
            self.assertEqual(self_graph[0]["7"]["class_type"], "MiniMaxH3ReferenceToVideo")
            self.assertEqual(job["segments"][0]["status"], "done")
            self.assertTrue((work / "00_part_v1.mp4").exists())

    def test_full_service_never_imports_legacy_film_planner(self):
        import inspect
        code = inspect.getsource(service)
        self.assertNotIn("from banana_mv import film", code)
        self.assertNotIn("banana_mv.film.py", code)
        self.assertIn("film_v2", code)


if __name__ == "__main__":
    unittest.main()
