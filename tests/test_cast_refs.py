import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from banana_mv import cast_refs

SHARED = """■ 角色與圖片綁定
<Picture 1>＝小巫＝S1
<Picture 2>＝幽冥食堂居酒屋場景

■ 新增客人

S6＝白髮老人靈魂
溫和沙啞的老年男性聲線。
穿著樸素舊式衣服，身體呈現淡淡半透明感。

S8＝小女孩靈魂
自然清亮的兒童聲線。

其他客人為背景靈魂群眾。"""

PROMPT = """subject_definitions:
<Subject 1> is the hostess 小巫 from <Picture 1>.
<Subject 2> is the weary elder soul 白髮老人 in plain threadbare clothes.
<Subject 3> is the little girl soul 小女孩 with a faint translucent outline.

summary:
They meet at the door.

retention_analysis:
<Subject 1>: fully_preserved.

detailed_description:
[Shot 1] <Subject 1> opens the door; <Subject 2> and <Subject 3> wait outside.
[Shot 2] At 00:04.000, the shot cuts to a frontal close-up of <Subject 2>, who bows.
[Shot 3] At 00:07.000, a two-shot of <Subject 1> and <Subject 3>.

overall_soundscape:
Night street.

non_diegetic_music:
None."""


def job_for(tmp, mode='chain', images=2):
    return {'id': 'abc', 'request': {'mode': mode, 'auto_cast_frames': True},
            'images_comfy': [f'img{i}.png' for i in range(images)],
            'sources': {'images': [f'sources/image_{i}.png' for i in range(images)]},
            'shared_setup': SHARED,
            'segments': [
                {'index': 0, 'status': 'done', 'seconds': 10.0, 'director_plan': {'event': 'S1 S6 S8 進門'},
                 'fixed_reference_settings': SHARED, 'absent_cast_pictures': []},
                {'index': 1, 'status': 'waiting', 'seconds': 10.0, 'director_plan': {'event': 'S6 坐下吃串燒'},
                 'fixed_reference_settings': SHARED, 'absent_cast_pictures': [1]},
            ]}


def fake_app(root):
    backend = SimpleNamespace(
        safe_child=lambda base, rel: Path(base) / rel,
        upload_comfy_image=Mock(side_effect=lambda cfg, name, data, mime: name))
    return SimpleNamespace(job_dir=lambda _: Path(root), backend=backend)


def fake_ffmpeg(args):
    Path(args[-1]).write_bytes(b'png-' + args[args.index('-ss') + 1].encode())


class CastRefsTests(unittest.TestCase):
    def test_unbound_cast_reads_new_roles_without_pictures(self):
        cast = cast_refs.unbound_cast(SHARED)
        self.assertEqual([(c['role'], c['name']) for c in cast], [('S6', '白髮老人靈魂'), ('S8', '小女孩靈魂')])
        self.assertIn('半透明', cast[0]['description'])
        self.assertEqual(cast_refs.unbound_cast(SHARED + '\n<Picture 3>＝白髮老人靈魂＝S6（外觀參考）')[0]['role'], 'S8')

    def test_best_shot_prefers_a_solo_close_up_and_matches_short_names(self):
        elder, girl = cast_refs.unbound_cast(SHARED)
        self.assertAlmostEqual(cast_refs.best_shot(PROMPT, elder, 10.0), 5.35)   # Shot 2：00:04–00:07 單人特寫
        self.assertAlmostEqual(cast_refs.best_shot(PROMPT, girl, 10.0), 8.35)    # Shot 3：只跟一個人同框
        self.assertIsNone(cast_refs.best_shot(PROMPT, {'role': 'S7', 'name': '年輕男子靈魂', 'description': ''}, 10.0))

    def test_free_slots_reserve_the_tail_frame_in_chain_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(cast_refs.free_slots(job_for(tmp, 'chain', 6)), 2)
            self.assertEqual(cast_refs.free_slots(job_for(tmp, 'chain5', 6)), 3)
            self.assertEqual(cast_refs.free_slots(job_for(tmp, 'chain', 8)), 0)

    def test_grab_adds_pictures_after_existing_ones_and_updates_later_clips(self):
        with tempfile.TemporaryDirectory() as tmp:
            job, app, originals = job_for(tmp), fake_app(tmp), [Path(tmp) / 'a.png', Path(tmp) / 'b.png']
            seg = job['segments'][0]
            added = cast_refs.grab_from_clip(app, {}, job, seg, Path(tmp) / 'part.mp4', PROMPT, originals, fake_ffmpeg)
            self.assertEqual(added, [3, 4])
            self.assertEqual(job['images_comfy'][2:], ['banana_film_abc_2.png', 'banana_film_abc_3.png'])
            self.assertEqual(len(originals), 4)
            self.assertIn('<Picture 3>＝白髮老人靈魂＝S6（外觀參考：第 1 段畫面', job['shared_setup'])
            self.assertEqual(cast_refs.unbound_cast(job['shared_setup']), [])
            later = job['segments'][1]
            self.assertIn('<Picture 3>', later['fixed_reference_settings'])
            self.assertTrue(later['refresh_prompt'])
            self.assertNotIn(3, later['absent_cast_pictures'])        # S6 有出場：新圖要給
            self.assertIn(4, later['absent_cast_pictures'])           # S8 沒出場：新圖不給
            self.assertNotIn('<Picture 3>', job['segments'][0]['fixed_reference_settings'])  # 拍好的段不動
            self.assertEqual([r['role'] for r in job['cast_refs']], ['S6', 'S8'])
            self.assertEqual(Path(tmp, job['sources']['images'][2]).read_bytes(), b'png-5.350')

    def test_grab_respects_switch_and_picture_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = job_for(tmp, 'chain', 7)
            job['request']['auto_cast_frames'] = False
            app = fake_app(tmp)
            self.assertEqual(cast_refs.grab_from_clip(app, {}, job, job['segments'][0], 'p', PROMPT, [], fake_ffmpeg), [])
            job['request']['auto_cast_frames'] = True
            self.assertEqual(cast_refs.grab_from_clip(app, {}, job, job['segments'][0], 'p', PROMPT, [], fake_ffmpeg), [8])

    def test_fitting_renders_one_short_portrait_per_new_role_in_this_dish(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = job_for(tmp, 'chain5')
            job['segments'][0]['status'] = 'waiting'          # 這道菜還沒開拍
            job['request'].update(cast_fitting=True, sampling_steps=6)
            job.update(size=[480, 864], seed=1)
            app = fake_app(tmp)
            graphs = []
            app.build_workflow = Mock(side_effect=lambda images, audio, w, h, frames, prompt, *a, **k:
                                      graphs.append((images, frames, prompt)) or {'16': {'inputs': {}}})
            app.graph_options = Mock(return_value={})
            app.preflight = Mock()
            app.write_state = Mock()
            app.wait_generation = Mock(return_value={})
            app.video_info = Mock(return_value={})
            app.backend.queue_prompt = Mock(return_value='pid')
            app.backend.comfy_download = Mock(side_effect=lambda cfg, info, path: Path(path).write_bytes(b'mp4'))
            added = cast_refs.fitting(app, {}, job, [], fake_ffmpeg)
            self.assertEqual(added, [3, 4])
            self.assertEqual([g[:2] for g in graphs], [([], 124), ([], 124)])
            self.assertIn('白髮老人靈魂 (S6)', graphs[0][2])
            self.assertEqual([r['source'] for r in job['cast_refs']], ['fitting', 'fitting'])
            self.assertEqual(cast_refs.fitting(app, {}, job, [], fake_ffmpeg), [])   # 都有圖了：續做或下一道不重拍
            self.assertEqual(len(graphs), 2)


if __name__ == '__main__':
    unittest.main()
