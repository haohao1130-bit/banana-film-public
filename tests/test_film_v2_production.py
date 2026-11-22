"""Regression contract for the isolated Python film production core."""
import copy
import json
import unittest

from film_v2.production import FilmPlanError, compile_film, shot_commission


def story():
    return {
        "title": "夜班的信",
        "shared_setup": "A 是快遞員；B 是夜班管理員。房間只有一扇門與一張桌子。",
        "initial_state": {
            "characters": {
                "A": {"location": "table", "position": "standing", "held_props": []},
                "B": {"location": "hallway", "position": "standing", "held_props": []},
            },
            "props": {"letter": {"holder": "table", "status": "sealed"}},
        },
        "beats": [
            {
                "id": "b1", "actors": ["A"], "seconds_hint": 6,
                "action": "A 把信封從桌上拿起來。",
                "changes": {"characters": {"A": {"held_props": ["letter"]}},
                            "props": {"letter": {"holder": "A"}}},
            },
            {
                "id": "b2", "actors": ["A"], "seconds_hint": 6,
                "action": "A 帶著信走到門邊，停下來回頭。",
                "changes": {"characters": {"A": {"location": "door"}}},
                "cut_after": True,
            },
            {
                "id": "b3", "actors": ["B"], "seconds_hint": 6,
                "action": "B 聽見聲響，從走廊走進房間。",
                "changes": {"characters": {"B": {"location": "room"}}},
            },
        ],
    }


class PythonOwnedFilmV2Tests(unittest.TestCase):
    def test_python_owns_boundaries_and_preserves_explicit_state(self):
        plan = compile_film(story())
        self.assertEqual(plan["engine"], "python_owned_film_v2")
        self.assertEqual([c["event_ids"] for c in plan["clips"]], [["b1", "b2"], ["b3"]])
        self.assertEqual(plan["clips"][0]["state_at_open"]["props"]["letter"]["holder"], "table")
        self.assertEqual(plan["clips"][0]["state_at_close"]["props"]["letter"]["holder"], "A")
        self.assertEqual(plan["clips"][1]["state_at_open"]["characters"]["A"]["location"], "door")
        self.assertEqual(plan["clips"][0]["boundary"], "intermediate")
        self.assertEqual(plan["clips"][1]["boundary"], "final")
        self.assertTrue(all((c["frames"] - 5) % 17 == 0 for c in plan["clips"]))
        self.assertTrue(all(c["start_frame"] == sum(x["frames"] for x in plan["clips"][:i])
                            for i, c in enumerate(plan["clips"])))

    def test_9b_camera_only_sees_local_events_not_future_story(self):
        plan = compile_film(story())
        first = shot_commission(plan, 0)
        second = shot_commission(plan, 1)
        self.assertIn("拿起來", json.dumps(first, ensure_ascii=False))
        self.assertNotIn("B 聽見聲響", json.dumps(first, ensure_ascii=False))
        self.assertNotIn("b3", json.dumps(first, ensure_ascii=False))
        self.assertEqual(second["already_completed_event_id"], "b2")
        self.assertEqual(second["events"][0]["id"], "b3")
        self.assertNotIn("source_sha256", first)

    def test_no_llm_or_video_runtime_dependency_and_repeatable_result(self):
        doc = story()
        original = copy.deepcopy(doc)
        first = compile_film(doc)
        self.assertEqual(first, compile_film(doc))
        self.assertEqual(doc, original)
        shot_commission(first, 0)["known_opening_state"]["props"]["letter"]["holder"] = "corrupt"
        self.assertEqual(first["clips"][0]["state_at_open"]["props"]["letter"]["holder"], "table")

    def test_cannot_split_a_long_atomic_beat_to_fit_h3(self):
        doc = story()
        doc["beats"] = [dict(doc["beats"][0], seconds_hint=16)]
        with self.assertRaisesRegex(FilmPlanError, "無法組成合法"):
            compile_film(doc)

    def test_explicit_scene_break_cannot_create_illegal_tiny_clip(self):
        doc = story()
        doc["beats"][0]["seconds_hint"] = 1
        doc["beats"][0]["cut_after"] = True
        with self.assertRaises(FilmPlanError):
            compile_film(doc)

    def test_invalid_identity_patch_and_unknown_actor_fail_closed(self):
        doc = story()
        doc["beats"][1]["changes"] = {"characters": {"C": {"location": "door"}}}
        with self.assertRaisesRegex(FilmPlanError, "未知角色"):
            compile_film(doc)
        doc = story()
        doc["beats"][1]["changes"] = {"characters": {"A": {"role": "villain"}}}
        with self.assertRaisesRegex(FilmPlanError, "保留欄位"):
            compile_film(doc)
        doc = story()
        doc["beats"][0]["actors"] = ["Z"]
        with self.assertRaisesRegex(FilmPlanError, "未登記角色"):
            compile_film(doc)

    def test_dialogue_is_owned_by_one_beat_and_keeps_speaker(self):
        doc = story()
        doc["beats"][0]["dialogue"] = [
            {"speaker": "A", "text": "這封信為什麼會自己動？", "language": "zh-TW"}
        ]
        plan = compile_film(doc)
        self.assertEqual(shot_commission(plan, 0)["events"][0]["dialogue"][0]["speaker"], "A")
        self.assertEqual(shot_commission(plan, 0)["events"][0]["dialogue"][0]["text"],
                         "這封信為什麼會自己動？")

    def test_duplicate_events_are_rejected(self):
        doc = story()
        doc["beats"][1]["id"] = "b1"
        with self.assertRaisesRegex(FilmPlanError, "重複事件 ID"):
            compile_film(doc)

    def test_hard_ceiling_does_not_silently_compress_events(self):
        with self.assertRaisesRegex(FilmPlanError, "總長超過"):
            compile_film(story(), max_seconds=12, max_clip_seconds=6)
        with self.assertRaises(FilmPlanError):
            compile_film(story(), max_clip_seconds=4)

    def test_six_second_mode_still_uses_legal_grid(self):
        doc = story()
        for beat in doc["beats"]:
            beat["cut_after"] = True
        plan = compile_film(doc, max_clip_seconds=6)
        self.assertEqual(len(plan["clips"]), 3)
        self.assertTrue(all(c["seconds"] <= 6 for c in plan["clips"]))


if __name__ == "__main__":
    unittest.main()
