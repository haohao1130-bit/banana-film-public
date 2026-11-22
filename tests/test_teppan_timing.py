"""蕉彌鐵板燒：秒數由 Python 決定，9B 填錯秒數也不會卡住。"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from banana_mv import film, film_kitchen, server as app
from banana_mv.teppan_timing import (
    MIN_CLIP, clip_windows, estimate_menu, fit_segments, native_h3_clips,
)

H3 = ('subject_definitions:\n<Picture 1> = 蕉彌，戴廚師帽的香蕉。\n\n'
      'summary:\n蕉彌在鐵板前翻炒牛排。\n\n'
      'retention_analysis:\n開場直接看到熱油冒煙。\n\n'
      'detailed_description:\n[Shot 1] 中景，<Picture 1> 蕉彌翻動鍋鏟，牛排滋滋作響。\n\n'
      'overall_soundscape:\n鐵板滋滋聲與抽油煙機低鳴，沒有人聲。\n\n'
      'non_diegetic_music:\n無。')

LONG_BRIEF = ('<Picture 1> 是蕉彌，站在鐵板前把蒜片撒上鐵板，熱油立刻冒出白煙。'
              '蕉彌用鍋鏟把蒜片推成一排，轉頭看向客人。'
              '蕉彌把牛排放上鐵板，牛排發出滋滋聲，油花四濺。'
              '蕉彌俐落地翻面，舉起鍋鏟對客人比出大拇指。')


def authored_act_menu():
    def clock(seconds):
        return f'{seconds // 60:02d}:{seconds % 60:02d}'

    divider = '━' * 20
    lines = ['BANANAMV｜異世界食堂番外篇', '《投胎前的最後一頓晚餐》',
             '總長04:00｜24段｜每段10秒']
    for i in range(24):
        lines.extend([divider, f'ACT {i+1:02d}｜{clock(i*10)}–{clock((i+1)*10)}',
                      f'第 {i+1} 幕', divider, 'SHOT 1', 'S1停下手中工作，望向來客。',
                      'SHOT 2', 'S6（低聲）：', '「我們想在投胎之前，吃頓晚飯。」'])
    lines.extend([divider, 'END', divider])
    return '\r\n'.join(lines)


class ClipWindowTests(unittest.TestCase):
    def test_every_window_is_legal_and_never_over_ten(self):
        for total in [6, 9.5, 10, 10.4, 12, 15, 20, 21, 25, 33.3, 60, 299]:
            windows = clip_windows(total)
            self.assertTrue(all(MIN_CLIP - 1e-9 <= w <= 10 + 1e-9 for w in windows), (total, windows))
            self.assertLessEqual(sum(windows), max(total, MIN_CLIP) + 1 / 24 + 1e-6)

    def test_examples(self):
        self.assertEqual(clip_windows(10), [10.0])
        self.assertEqual(clip_windows(20), [10.0, 10.0])
        self.assertEqual(clip_windows(21), [10.0, 10.0])          # 1 秒尾巴捨去
        self.assertEqual(clip_windows(26), [10.0, 10.0, 6.0])
        self.assertEqual(clip_windows(13), [6.5, 6.5])            # 3 秒尾巴不夠，平分


class EstimateTests(unittest.TestCase):
    def test_windows_act_menu_uses_all_24_authored_ranges(self):
        result = estimate_menu(authored_act_menu())
        self.assertEqual((result['seconds'], result['source']), (240.0, 'timecode'))
        self.assertEqual(result['windows'], [10.0] * 24)

    def test_dialogue_and_actions_raise_estimate(self):
        short = estimate_menu('蕉彌翻炒牛排。')
        long = estimate_menu('蕉彌翻炒牛排。蕉大師走進店裡坐下。蕉彌抬頭。'
                             '蕉大師說「今天的牛排要七分熟，蒜片多一點，再來一碗白飯和味噌湯。」'
                             '蕉彌回答「好的老闆，馬上來！」蕉彌把牛排放上鐵板。')
        self.assertEqual(short['seconds'], 6.0)
        self.assertGreater(long['seconds'], short['seconds'])
        self.assertEqual(long['clips'], len(long['windows']))
        self.assertEqual(long['render_seconds'], 90 * long['clips'])

    def test_declared_length_wins(self):
        self.assertEqual(estimate_menu('長度：30秒。蕉彌翻炒。')['windows'], [10.0, 10.0, 10.0])
        self.assertEqual(estimate_menu('片長 1 分鐘，蕉彌開店。')['seconds'], 60.0)

    def test_contiguous_act_timecodes_set_total(self):
        menu = ('第一幕｜迎客（00:00–00:30）\n'
                'MINIMAX H3 專用提示詞｜場景1（00:00–00:30）\n'
                '第二幕｜入席（00:30–01:00）\n'
                '第三幕｜揮手（01:00–00:30）\n'
                'MINIMAX H3 專用提示詞｜場景3（01:00–01:30）')
        result = estimate_menu(menu)
        self.assertEqual(result['source'], 'timecode')
        self.assertEqual(result['windows'], [10.0] * 9)
        self.assertEqual(estimate_menu(menu + '\n總長正好180秒。')['windows'], [10.0] * 18)

    def test_native_h3_detected(self):
        result = estimate_menu('=== CLIP 1 (10s) ===\n' + H3 + '\n=== CLIP 2 (8s) ===\n' + H3)
        self.assertTrue(result['native_h3'])
        self.assertEqual(result['windows'], [10.0, 8.0])


class NativeDetectionTests(unittest.TestCase):
    def test_rough_cue_is_not_native(self):
        self.assertIsNone(native_h3_clips('蕉彌在鐵板前炒菜，蕉大師來點單。', 10))

    def test_single_native_prompt_uses_dish_seconds_capped(self):
        self.assertEqual(native_h3_clips(H3, 6), [(6.0, H3)])
        self.assertEqual(native_h3_clips(H3, 30)[0][0], 10.0)
        self.assertEqual(native_h3_clips('```h3\n' + H3 + '\n```', 10), [(10.0, H3)])

    def test_clip_markers_with_rough_bodies_stay_with_9b(self):
        self.assertIsNone(native_h3_clips('=== CLIP 1 (10s) ===\n蕉彌炒菜。', 10))

    def test_over_cap_native_clip_errors_instead_of_hanging(self):
        with self.assertRaises(ValueError):
            native_h3_clips('=== CLIP 1 (12s) ===\n' + H3, 10)


class FitSegmentsTests(unittest.TestCase):
    def test_9b_seconds_are_ignored(self):
        rows = [{'seconds': 12, 'mode': 'story', 'brief': 'A' * 30},
                {'seconds': 11.7, 'mode': 'action', 'brief': 'B' * 30}]
        segments, windows = fit_segments(rows, [10.0, 10.0])
        self.assertEqual([s['seconds'] for s in segments], [10.0, 10.0])
        self.assertEqual(windows, [10.0, 10.0])

    def test_too_many_segments_are_merged(self):
        rows = [{'brief': c * 30} for c in 'ABC']
        segments, _ = fit_segments(rows, [10.0, 10.0])
        self.assertEqual(len(segments), 2)
        self.assertIn('A' * 30, segments[0]['brief'])

    def test_too_few_segments_are_split_at_sentence_end(self):
        segments, windows = fit_segments([{'seconds': 25, 'brief': LONG_BRIEF}], [10.0, 10.0])
        self.assertEqual(len(segments), 2)
        self.assertEqual(windows, [10.0, 10.0])
        self.assertTrue(segments[0]['brief'].endswith('。'))

    def test_unsplittable_shrinks_windows_instead_of_retrying(self):
        segments, windows = fit_segments([{'brief': '蕉彌翻炒牛排並且一直翻炒沒有停下來直到天亮為止'}],
                                         [10.0, 10.0, 6.0])
        self.assertEqual(len(segments), 1)
        self.assertEqual(windows, [10.0])


class KitchenPlanTests(unittest.TestCase):
    def fixture(self, root, seconds):
        photo = root / 'photo.png'
        Image.new('RGB', (16, 16)).save(photo)
        guide = root / 'guide.md'
        guide.write_text('NATIVE_GUIDE')
        work = root / 'aabbccddeeff'
        work.mkdir()
        req = {'production': 'film', 'prompt': '蕉彌煎牛排。', 'kitchen_mode': True,
               'max_seconds': seconds + 1.5, 'target_seconds': seconds, 'segment_seconds': 10.0,
               'duration_contract_version': 3, 'duration_source': 'selector', 'target_is_exact': True,
               'timeline_tolerance': 1.5, 'ten_second_delivery_v2': True, 'segment_policy': 'capped',
               'planning_contract_version': 2, 'fixed_reference_version': 1, 'auto_director': True,
               'visual_style': '真人電影', 'sound_mode': 'ambient', 'mode': 'chain', 'intensity': 'normal',
               'rewrite_retries': 3, 'genres': []}
        job = {'id': work.name, 'request': req, 'title': 't', 'segments': [], 'duration': 0}
        cfg = {'guides': {'ref': str(guide)}, 'rewriter': {'model': '9b', 'thinking': True,
                                                         'max_length': 16384}}
        return photo, work, job, cfg

    def test_9b_writing_twelve_seconds_is_accepted_first_try(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo, work, job, cfg = self.fixture(Path(tmp), 20)
            reply = {'title': '鐵板', 'shared_setup': '<Picture 1> = 蕉彌',
                     'segments': [{'seconds': 12, 'mode': 'story', 'brief': LONG_BRIEF}]}
            with patch.object(app.backend, 'rewrite_local', return_value=json.dumps(reply)) as model:
                plan = film.plan_film(cfg, job, [photo], work=work)
            self.assertEqual(model.call_count, 1)
            self.assertEqual([s['seconds'] for s in plan['segments']], [10.0, 10.0])
            self.assertIn('[10.0, 10.0]', model.call_args.args[1])

    def test_retry_is_bounded_and_drops_thinking(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo, work, job, cfg = self.fixture(Path(tmp), 10)
            good = {'title': '鐵板', 'shared_setup': '<Picture 1> = 蕉彌',
                    'segments': [{'seconds': 11, 'mode': 'story', 'brief': LONG_BRIEF}]}
            with patch.object(app.backend, 'rewrite_local',
                              side_effect=['not json', json.dumps(good)]) as model:
                plan = film.plan_film(cfg, job, [photo], work=work)
            self.assertEqual(plan['segments'][0]['seconds'], 10.0)
            self.assertTrue(model.call_args_list[0].args[0]['rewriter']['thinking'])
            self.assertFalse(model.call_args_list[1].args[0]['rewriter']['thinking'])
            with patch.object(app.backend, 'rewrite_local', return_value='not json') as model:
                shutil.rmtree(work)
                work.mkdir()
                with self.assertRaises(ValueError):
                    film.plan_film(cfg, job, [photo], work=work)
            self.assertEqual(model.call_count, 3)   # 最多 1 + 2 次，不會無限卡住

    def test_native_h3_menu_skips_9b(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo, work, job, cfg = self.fixture(Path(tmp), 10)
            job['request'].update(prompt=H3, kitchen_shared_setup='')
            job['kitchen'] = {'dishes': [{'attempts': [film_kitchen.new_attempt(H3, 10)]}]}
            with patch.object(app, 'job_dir', return_value=work), \
                    patch.object(app.backend, 'rewrite_local') as model:
                film_kitchen.prepare(job, cfg, [photo])
            model.assert_not_called()
            self.assertEqual(len(job['segments']), 1)
            self.assertIn('subject_definitions:', job['segments'][0]['manual_h3_prompt'])
            self.assertTrue(film_kitchen.latest(job)['native_h3'])

    def test_auto_seconds_resolves_from_menu(self):
        seconds, estimated = film_kitchen.resolve_seconds('長度：20秒。蕉彌煎牛排。', 'auto')
        self.assertEqual((seconds, estimated), (20.0, True))
        self.assertEqual(film_kitchen.resolve_seconds('x', 30), (30, False))

    def test_authored_act_menu_with_separate_setup_bypasses_whole_story_planning(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo, work, job, cfg = self.fixture(Path(tmp), 240)
            menu = authored_act_menu()
            shared = '<Picture 1> = 小巫 = S1\n<Picture 2> = 白髮老人 = S6\n<Picture 3> = 小貓 = S5'
            job['request']['kitchen_shared_setup'] = shared
            job['request']['fixed_reference_version'] = 1
            job['kitchen'] = {'dishes': [{'attempts': [film_kitchen.new_attempt(menu, 240)]}]}
            with patch.object(app, 'job_dir', return_value=work), patch.object(film, 'plan_film') as planner:
                film_kitchen.prepare(job, cfg, [photo, photo, photo])
            planner.assert_not_called()
            self.assertEqual(job['duration'], 240.0)
            self.assertEqual(job['shared_setup'], shared)
            self.assertEqual([s['seconds'] for s in job['segments']], [10.0] * 24)
            self.assertEqual(job['segments'][0]['absent_cast_pictures'], [3])
            first = job['segments'][0]['director_plan']['event']
            last = job['segments'][-1]['director_plan']['event']
            self.assertIn('「我們想在投胎之前，吃頓晚飯。」', first)
            self.assertNotIn('ACT 02', first)
            self.assertNotIn('━', last)
            self.assertNotIn('END', last)


if __name__ == '__main__':
    unittest.main()
