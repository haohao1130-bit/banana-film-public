"""Offline contract tests for the independent full-film VNext pipeline.

No GPU is involved. These tests do not assert 9B camera aesthetics or H3 output
quality; they prove two-call planning, sealed prompts, and zero render-time LLM.
"""
import json
from pathlib import Path
import tempfile
import unittest

from banana_mv.film_vnext import (
    FilmVNext, ProductionError, compile_clip, load_ready, render_ready,
    validate_cameras, validate_script,
)


def sample_script(n=18, *, dialogue=False):
    clips = []
    for i in range(n):
        beats = [
            {"id": f"E{i:02d}A", "at_ms": 0,
             "action": f"第{i}段開頭：小語向左移動，蕉大師準備防禦。"},
            {"id": f"E{i:02d}B", "at_ms": 5000,
             "action": (f"第{i}段結尾：雙方持續交手。" if i < n - 1
                        else "最終段：雙方依照委託結束交手。")},
        ]
        if dialogue and i == 0:
            beats[0].update(speaker=1, dialogue="開始吧！")
        clips.append({
            "index": i, "duration_ms": 10000,
            "opening_state": f"第{i}段起始的既定站位。",
            "outgoing_state": ("雙方仍在交手中。" if i < n - 1 else "全片最終結局已完成。"),
            "beats": beats,
        })
    return {
        "title": "大乘蕉宗・晨課詠春",
        "subjects": [
            {"id": 1, "name": "小語", "picture": 1,
             "appearance": "白色巫女服", "voice": 1},
            {"id": 2, "name": "蕉大師", "picture": 2,
             "appearance": "橘色袈裟", "voice": 2},
        ],
        "clips": clips,
    }


def camera_output(n=18):
    return json.dumps({"clips": [{
        "index": i,
        "shots": [
            {"at_ms": 0, "size": "wide", "angle": "low",
             "motion": "track", "framing": "balanced", "lighting": "side"},
            {"at_ms": 5000, "size": "close", "angle": "side",
             "motion": "follow", "framing": "headroom", "lighting": "natural"},
        ],
    } for i in range(n)]}, ensure_ascii=False)


class VNextContractTests(unittest.TestCase):
    def test_full_three_minutes_once_then_compile_every_clip(self):
        src = sample_script()
        calls = []

        def rewrite(role, task):
            calls.append((role, task))
            return json.dumps(src, ensure_ascii=False) if role == "WHOLE_FILM_SCREENWRITER" else camera_output()

        with tempfile.TemporaryDirectory() as tmp:
            engine = FilmVNext(rewrite)
            result = engine.prepare(tmp, "全片武打故事", picture_count=2)
            self.assertLessEqual(result["duration_ms"], 180000)
            self.assertEqual(result["requested_duration_ms"], 180000)
            self.assertGreater(result["duration_ms"], 179000)
            self.assertLess(result["duration_ms"], 180000)
            self.assertEqual(result["clip_count"], 18)
            self.assertEqual([r for r, _ in calls],
                             ["WHOLE_FILM_SCREENWRITER", "WHOLE_FILM_CAMERA_ONLY"])
            self.assertNotIn("結束交手", Path(tmp, "00_prompt.txt").read_text(encoding="utf-8"))
            self.assertIn("最終段：雙方依照委託結束交手。",
                          Path(tmp, "17_prompt.txt").read_text(encoding="utf-8"))
            self.assertEqual(len(list(Path(tmp).glob("*_prompt.txt"))), 18)
            self.assertEqual(len(load_ready(tmp)[1]), 18)
            self.assertFalse(result["camera_fallback"])
            aligned = json.loads(Path(tmp, "screenplay.json").read_text(encoding="utf-8"))
            self.assertEqual(set(c["render_frames"] for c in aligned["clips"]), {226, 243})
            self.assertEqual(sum(c["render_frames"] for c in aligned["clips"]), 4306)

    def test_malicious_camera_plot_is_not_executed(self):
        src = validate_script(sample_script(2), picture_count=2)
        camera = json.loads(camera_output(2))
        camera["clips"][0]["shots"][0]["action"] = "two actors bow and end the film"
        shots, fallback = validate_cameras(camera, src)
        self.assertTrue(fallback)
        result = compile_clip(src, 0, shots[0])
        self.assertNotIn("bow", result)
        self.assertIn("雙方持續交手。", result)

    def test_incomplete_camera_plan_uses_photographic_fallback(self):
        src = validate_script(sample_script(18), picture_count=2)
        plans, fallback = validate_cameras('{"clips":[', src)
        self.assertTrue(fallback)
        self.assertEqual(len(plans), 18)
        self.assertTrue(all(len(x) >= 1 for x in plans))

    def test_dialogue_only_adds_real_speakers(self):
        src = validate_script(sample_script(2, dialogue=True), picture_count=2)
        plans, _ = validate_cameras(camera_output(2), src)
        first = compile_clip(src, 0, plans[0])
        second = compile_clip(src, 1, plans[1])
        self.assertIn("<d>[Chinese] 開始吧！</d>", first)
        self.assertIn("(S1)", first)
        self.assertNotIn("(S1)", second)
        self.assertNotIn("(S2)", second)

    def test_invalid_causal_structure_prevents_preproduction(self):
        raw = sample_script(2)
        raw["clips"][1]["beats"][0]["id"] = raw["clips"][0]["beats"][0]["id"]
        with self.assertRaises(ProductionError):
            validate_script(raw, picture_count=2)
        raw = sample_script(2)
        raw["clips"][1]["beats"][0]["at_ms"] = 12000
        with self.assertRaises(ProductionError):
            validate_script(raw, picture_count=2)

    def test_sealed_prompts_reject_post_plan_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = FilmVNext(lambda role, _: (
                json.dumps(sample_script(2), ensure_ascii=False)
                if role == "WHOLE_FILM_SCREENWRITER" else camera_output(2)))
            engine.prepare(tmp, "短片", picture_count=2)
            path = Path(tmp, "01_prompt.txt")
            path.write_text(path.read_text(encoding="utf-8") +
                            "\nUNAUTHORIZED NEW STORY OUTCOME", encoding="utf-8")
            with self.assertRaises(ProductionError):
                load_ready(tmp)

    def test_screenplay_tampering_is_blocked_before_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            FilmVNext(lambda role, _: (
                json.dumps(sample_script(2), ensure_ascii=False)
                if role == "WHOLE_FILM_SCREENWRITER" else camera_output(2)
            )).prepare(tmp, "兩段劇情", picture_count=2)
            path = Path(tmp, "screenplay.json")
            text = path.read_text(encoding="utf-8")
            path.write_text(text.replace("雙方持續交手", "擅自停戰"), encoding="utf-8")
            with self.assertRaises(ProductionError):
                load_ready(tmp)

    def test_legacy_film_code_is_not_imported_for_compilation(self):
        import sys
        import banana_mv.film_vnext.pipeline as p
        self.assertEqual(p.FilmVNext.__module__, "banana_mv.film_vnext.pipeline")
        self.assertNotIn("from banana_mv.film import", Path(p.__file__).read_text(encoding="utf-8"))

    def test_render_resume_never_rewrites_or_rerenders_completed(self):
        calls = {"model": 0, "render": []}

        def rewrite(role, _):
            calls["model"] += 1
            return (json.dumps(sample_script(3), ensure_ascii=False)
                    if role == "WHOLE_FILM_SCREENWRITER" else camera_output(3))

        with tempfile.TemporaryDirectory() as tmp:
            FilmVNext(rewrite).prepare(tmp, "三段故事", picture_count=2)
            self.assertEqual(calls["model"], 2)
            fail_once = {"enabled": True}

            def renderer(index, prompt, clip):
                calls["render"].append(index)
                if index == 1 and fail_once["enabled"]:
                    fail_once["enabled"] = False
                    raise RuntimeError("simulated H3 interruption")
                path = Path(tmp, f"{index:02d}.mp4")
                path.write_bytes(b"mock movie")
                return path

            with self.assertRaises(RuntimeError):
                render_ready(tmp, renderer)
            result = render_ready(tmp, renderer)
            self.assertEqual(len(result), 3)
            self.assertEqual(calls["render"], [0, 1, 1, 2])
            self.assertEqual(calls["model"], 2)


if __name__ == "__main__":
    unittest.main()
