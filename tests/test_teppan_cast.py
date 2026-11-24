import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from banana_mv import film, film_kitchen, server as app, teppan_cast

SHARED = """■ 角色與圖片綁定

@圖片1＝小巫＝S1
@圖片2＝小狸＝S3
@圖片3＝幽冥食堂居酒屋場景

■ 主要角色聲音

S1 小巫：
溫柔清晰的年輕女性聲線。

S3 小狸：
沉穩俐落的年輕聲線。
偶爾用平靜語氣吐槽小浣（S5 偷吃時）。

■ 新增客人

S6＝白髮老人靈魂
外觀：無色半透明靈魂。

■ 影像與角色表演

高品質 3D 奇幻動畫。"""


class CastTextTests(unittest.TestCase):
    def test_commands_parse_only_at_the_start(self):
        self.assertEqual(teppan_cast.parse('取代@圖片2\n@圖片2＝小狐＝S9')[:2], ('replace', 2))
        self.assertEqual(teppan_cast.parse('移除＠圖片3')[:2], ('remove', 3))
        self.assertEqual(teppan_cast.parse('新增\n@圖片4＝小狐＝S9')[:2], ('add', None))
        self.assertIsNone(teppan_cast.parse('S1 走向食材櫃，取代原本的鍋子。'))

    def test_replace_swaps_binding_and_the_old_role_block_only(self):
        text, count, reply = teppan_cast.apply(SHARED, 'replace', 2, '@圖片2＝小狐＝S9\n活潑清脆的少女聲線。', 3, 8)
        self.assertEqual(count, 3)
        self.assertIn('@圖片2＝小狐＝S9', text)
        self.assertNotIn('小狸', text)
        self.assertIn('S9 小狐：\n活潑清脆的少女聲線。\n\n■ 新增客人', text)
        self.assertIn('S1 小巫：', text)            # 其他角色不動
        self.assertIn('S6＝白髮老人靈魂', text)
        self.assertIn('小狐（S9）', reply)

    def test_remove_drops_block_up_to_next_heading_and_renumbers(self):
        text, count, _ = teppan_cast.apply(SHARED, 'remove', 2, '', 3, 8)
        self.assertEqual(count, 2)
        self.assertNotIn('小狸', text)
        self.assertNotIn('吐槽', text)
        self.assertIn('@圖片2＝幽冥食堂居酒屋場景', text)
        self.assertIn('溫柔清晰的年輕女性聲線。\n\n■ 新增客人', text)

    def test_add_appends_after_last_picture_line_and_role_blocks(self):
        text, count, _ = teppan_cast.apply(SHARED, 'add', None, '@圖片4＝小狐＝S9\n活潑。', 3, 8)
        self.assertEqual(count, 4)
        self.assertIn('@圖片3＝幽冥食堂居酒屋場景\n@圖片4＝小狐＝S9', text)
        self.assertIn('外觀：無色半透明靈魂。\n\nS9 小狐：\n活潑。\n\n■ 影像與角色表演', text)
        with self.assertRaises(ValueError):
            teppan_cast.apply(SHARED, 'add', None, '@圖片3＝小狐＝S9', 3, 8)
        with self.assertRaises(ValueError):
            teppan_cast.apply(SHARED, 'add', None, '@圖片4＝小狐＝S9', 3, 3)

    def test_round_trip_between_display_and_internal(self):
        self.assertEqual(teppan_cast.to_display('<Picture 2>＝小狸'), '@圖片2＝小狸')
        self.assertEqual(teppan_cast.to_internal('@圖片2＝小狸'), '<Picture 2>＝小狸')


def kitchen_job(work, images):
    sources = []
    for index in range(images):
        (work / 'sources').mkdir(parents=True, exist_ok=True)
        (work / 'sources' / f'image_{index}.png').write_bytes(b'img%d' % index)
        sources.append(f'sources/image_{index}.png')
    shared = teppan_cast.to_internal(SHARED)
    segments = []
    for index in range(4):
        segments.append({'index': index, 'status': 'done' if index < 3 else 'waiting', 'seconds': 10, 'frames': 240,
                         'director_plan': {'event': f'<Picture 2> 第 {index + 1} 段'},
                         'fixed_reference_settings': shared})
    return {'id': 'job1', 'status': 'cancelled', 'request': {'mode': 'chain5', 'image_slots': ['a', 'b', 'c']},
            'kitchen': {'dishes': [{'attempts': [{'menu': 'm', 'seconds': 40, 'clips': [0, 1, 2, 3]}]}]},
            'sources': {'images': sources}, 'images_comfy': [f'c{i}.png' for i in range(images)],
            'shared_setup': shared, 'segments': segments}


class KitchenCastTests(unittest.TestCase):
    def run_edit(self, job, work, body, action):
        library = work / 'library'
        library.mkdir(exist_ok=True)
        (library / 'fox.png').write_bytes(b'fox')
        saved = []
        with patch.object(app, 'read_state', return_value=job), \
                patch.object(app, 'write_state', side_effect=lambda j: saved.append(True)), \
                patch.object(app, 'job_dir', return_value=work), \
                patch.object(app.backend, 'LIBRARY', library), \
                patch.object(app.backend, 'asset', return_value={'file': 'fox.png'}), \
                patch.object(app.backend, 'project_config', return_value={}), \
                patch.object(app.backend, 'upload_comfy_image', side_effect=lambda cfg, name, data, kind: name), \
                patch('banana_mv.takes.describe', side_effect=lambda j: j):
            result = film_kitchen.edit_cast(dict(body, id='job1'), action)
        self.assertTrue(saved)
        return result

    def test_replace_keeps_done_clips_on_their_old_pictures(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            job = kitchen_job(work, 3)
            old = list(job['sources']['images'])
            self.run_edit(job, work, {'command': '取代@圖片2\n@圖片2＝小狐＝S9\n活潑。', 'image': 'fox'}, 'cast')
            self.assertNotEqual(job['sources']['images'][1], old[1])
            self.assertEqual((work / job['sources']['images'][1]).read_bytes(), b'fox')
            self.assertEqual(job['segments'][0]['reference_sources'], old)
            self.assertNotIn('reference_sources', job['segments'][3])
            self.assertIn('<Picture 2>＝小狐＝S9', job['segments'][3]['fixed_reference_settings'])
            self.assertIn('小狸', job['segments'][0]['fixed_reference_settings'])
            self.assertTrue(job['segments'][3]['refresh_prompt'])
            self.assertIn('@圖片2＝小狐＝S9', job['request']['kitchen_shared_setup'])
            self.assertIsNone(job['request']['image_slots'])
            self.assertEqual(job['kitchen']['cast_log'][0]['picture'], 2)
            with patch.object(app, 'job_dir', return_value=work):
                originals = film.segment_originals(job, job['segments'][0], [])
            self.assertEqual([p.read_bytes() for p in originals], [b'img0', b'img1', b'img2'])

    def test_remove_renumbers_pictures_in_unshot_briefs(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            job = kitchen_job(work, 3)
            job['segments'][3]['director_plan']['event'] = '<Picture 3> 店內，<Picture 1> 招呼。'
            self.run_edit(job, work, {'command': '移除@圖片2'}, 'cast')
            self.assertEqual(len(job['sources']['images']), 2)
            self.assertEqual(job['segments'][3]['director_plan']['event'], '<Picture 2> 店內，<Picture 1> 招呼。')
            self.assertNotIn('小狸', job['shared_setup'])

    def test_manual_shared_edit_rejects_missing_pictures(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            job = kitchen_job(work, 3)
            with self.assertRaises(ValueError):
                self.run_edit(job, work, {'shared': '@圖片5＝誰＝S9'}, 'shared')
            self.run_edit(job, work, {'shared': '@圖片1＝小巫＝S1\n新的規則。'}, 'shared')
            self.assertEqual(job['segments'][3]['fixed_reference_settings'], '<Picture 1>＝小巫＝S1\n新的規則。')


class ContinueTests(unittest.TestCase):
    def test_continue_commits_retake_and_redoes_later_clips(self):
        job = kitchen_job(Path(tempfile.mkdtemp()), 3)
        job['pending_takes'] = {'1': 'abcdefabcdef', '2': '123456123456'}
        job['segments'][2]['takes'] = [{'id': 'original'}]
        with patch.object(app, 'read_state', return_value=job), patch.object(app, 'write_state'), \
                patch.object(app, 'resume', return_value='resumed') as resume:
            self.assertEqual(film_kitchen.continue_from({'id': 'job1', 'index': 1}), 'resumed')
        resume.assert_called_once_with('job1')
        self.assertEqual(job['segments'][1]['selected_take'], 'abcdefabcdef')
        self.assertEqual(job['pending_takes'], {})
        self.assertEqual(job['segments'][2]['status'], 'waiting')
        self.assertTrue(job['segments'][2]['redo'] and job['segments'][2]['refresh_prompt'])
        self.assertNotIn('takes', job['segments'][2])
        self.assertEqual(job['segments'][0]['status'], 'done')

    def test_continue_on_a_finished_dish_without_later_clips_just_commits(self):
        job = kitchen_job(Path(tempfile.mkdtemp()), 3)
        job['segments'][3]['status'] = 'done'
        job['status'] = 'kitchen_ready'
        job['pending_takes'] = {'3': 'abcdefabcdef'}
        with patch.object(app, 'read_state', return_value=job), patch.object(app, 'write_state'), \
                patch.object(app, 'resume') as resume:
            film_kitchen.continue_from({'id': 'job1', 'index': 3})
        resume.assert_not_called()
        self.assertEqual(job['segments'][3]['selected_take'], 'abcdefabcdef')
        self.assertEqual(job['status'], 'kitchen_ready')


if __name__ == '__main__':
    unittest.main()
