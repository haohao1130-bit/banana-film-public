"""一鍵短片「純手動 H3」入口：設定是上限、秒數照使用者寫的精確交付。"""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from banana_mv import film, server as app

H3 = ('subject_definitions:\n蕉彌：戴廚師帽的香蕉。\n\nsummary:\n蕉彌炒菜。\n\nretention_analysis:\n開場熱油。\n\n'
      'detailed_description:\n[Shot 1] 中景，蕉彌翻鍋鏟。\n\noverall_soundscape:\n鐵板滋滋聲，沒有人聲。\n\n'
      'non_diegetic_music:\n無。')


def clips(*seconds):
    return '\n'.join(f'=== CLIP {i} ({s}s) ===\n{H3}' for i, s in enumerate(seconds, 1))


def start(story, mode='chain5', **extra):
    req = dict(prompt=story, auto_director=False, script_review=True, sound_mode='auto', mode=mode,
               visual_style='真人電影', intensity='normal', aspect='16:9', seed=1, sampling_steps=6,
               duration_preference='prompt', max_seconds=300, segment_seconds='auto')
    req.update(extra)
    with tempfile.TemporaryDirectory() as tmp, \
            patch.object(app.backend, 'project_config', return_value={'guides': {'ref': '/x'}, 'rewriter': {'model': 'x'}}), \
            patch.object(app, 'preflight'), patch.object(app.backend, 'comfy', return_value={}), \
            patch.object(app, 'write_state'), patch.object(app, 'RUNS', Path(tmp)), \
            patch.object(threading, 'Thread'), patch.object(film, 'inputs', return_value=([], None, None)):
        try:
            return film.start(req)
        finally:
            if app.GPU_LOCK.locked():
                app.GPU_LOCK.release()


def seconds(job):
    return [round(s['seconds'], 3) for s in job['segments']]


class ManualEntryTests(unittest.TestCase):
    def test_single_prompt_with_default_settings_is_one_clip(self):
        self.assertEqual(seconds(start(H3)), [15.0])
        self.assertEqual(seconds(start(H3, segment_seconds=10)), [10.0])

    def test_duration_header_line_is_allowed(self):
        self.assertEqual(seconds(start('全片 10 秒\n' + H3)), [10.0])
        self.assertEqual(seconds(start('全片 20 秒\n' + clips(10, 10))), [10.0, 10.0])

    def test_selector_is_a_ceiling_not_exact(self):
        job = start(clips(10, 10), duration_preference='selector', max_seconds=30)
        self.assertEqual(seconds(job), [10.0, 10.0])
        with self.assertRaisesRegex(ValueError, '超過'):
            start(clips(10, 10), duration_preference='selector', max_seconds=15)

    def test_authored_clip_seconds_are_delivered_exactly(self):
        self.assertEqual(seconds(start(clips(6, 6))), [6.0, 6.0])
        self.assertEqual(seconds(start(clips(12, 12, 12))), [12.0, 12.0, 12.0])

    def test_single_prompt_longer_than_one_clip_explains_why(self):
        with self.assertRaisesRegex(ValueError, '單段 H3 全咒最多 10 秒'):
            start(H3, duration_preference='selector', max_seconds=15, segment_seconds=10)


if __name__ == '__main__':
    unittest.main()
