"""Native-H3 manual authority and explicit total-length regression tests.

No local GPU, model or model download is used. Existing saved projects preserve
their legacy settings_version/contract; only new jobs get contract v3.
"""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from banana_mv import film, film_manual, server as app, takes
import test_film as fixtures


def h3(text='A courier passes a sealed letter.'):
    return (
        'subject_definitions:\n<Subject 1> is an adult courier.\n'
        'summary:\nA courier delivers a letter without dialogue.\n'
        'retention_analysis:\n<Subject 1> preserved from the reference.\n'
        'detailed_description:\n[Shot 1] <Subject 1> '+text+'\n'
        'overall_soundscape:\nNatural footsteps and a paper rustle. No dialogue.\n'
        'non_diegetic_music:\nNone.\n'
    )


def multi():
    return '\n'.join(
        f'=== CLIP {i+1} ({seconds}s) ===\n{h3(f"acts in commissioned clip {i+1}.")}'
        for i,seconds in enumerate([12,12,11])
    )


class FilmManualDirectorTests(unittest.TestCase):
    def test_total_duration_parser_is_explicit_not_local_action_time(self):
        self.assertEqual(film.declared_film_seconds('全片 35 秒。鏡頭第 5 秒切換。'),35)
        self.assertEqual(film.declared_film_seconds('Total duration: 35s'),35)
        self.assertIsNone(film.declared_film_seconds('第 35 秒後走到餐桌。'))
        with self.assertRaisesRegex(ValueError,'不同的全片秒數'):
            film.declared_film_seconds('全片 35 秒，總長 40 秒')

    def test_manual_native_35s_is_deterministic_and_preserves_shots(self):
        req={'max_seconds':36.5,'target_seconds':35,'target_is_exact':True,
             'timeline_tolerance':1.5,'segment_seconds':15,'sound_mode':'auto'}
        clips=film_manual.split_native_h3(multi(),15)
        plan=film_manual.make_manual_plan(clips,req,film.normalize_prompt,film.map_story,
                                          0,film.validate_film_format)
        self.assertEqual(len(plan['segments']),3)
        self.assertAlmostEqual(plan['duration'],35.333333333,places=4)
        self.assertEqual(plan['segments'][0]['manual_h3_prompt'],clips[0][1])
        self.assertEqual([s['frames'] for s in plan['segments']],[294,294,260])
        self.assertIn('commissioned clip 3',plan['segments'][2]['manual_h3_prompt'])
        self.assertLessEqual(abs(plan['duration']-35),1.5)

    def test_manual_native_does_not_invent_segments_or_accept_broken_format(self):
        self.assertIsNone(film_manual.split_native_h3('完整事件說明，不是 H3 全咒',15))
        for text in ('=== CLIP 2 (12s) ===\n'+h3(),
                     '=== CLIP ONE (12s) ===\n'+h3(),
                     '=== CLIP 1 (12s) ===\n'+h3()+'\n=== CLIP 3 (11s) ===\n'+h3()):
            with self.subTest(text=text[:25]),self.assertRaises(ValueError):
                film_manual.split_native_h3(text,15)
        req={'max_seconds':36.5,'target_seconds':35,'target_is_exact':True,
             'timeline_tolerance':1.5,'segment_seconds':15,'sound_mode':'ambient'}
        with self.assertRaisesRegex(ValueError,'說話者'):
            film_manual.make_manual_plan(
                [(12,h3().replace('No dialogue.','<Subject 1> (S1) <d>[English] Hi.</d>'))],
                req,film.normalize_prompt,film.map_story,0,film.validate_film_format)

    def test_manual_start_and_review_never_call_9b(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            photo,work,req,job,cfg=fixtures.FilmTests().fixture(root)
            req.update(prompt=multi(),image_ids=[],auto_director=False,script_review=True,
                       max_seconds=60,duration_preference='prompt',segment_seconds='auto',
                       sound_mode='auto',genres=['comedy'])
            with ExitStack() as stack:
                stack.enter_context(patch.object(app.backend,'load_config',return_value=cfg))
                stack.enter_context(patch.object(app,'RUNS',root))
                stack.enter_context(patch.object(app,'write_state'))
                stack.enter_context(patch.object(app,'preflight'))
                stack.enter_context(patch.object(app.backend,'comfy',return_value={'queue_running':[],'queue_pending':[]}))
                stack.enter_context(patch.object(film.threading,'Thread'))
                model=stack.enter_context(patch.object(app.backend,'rewrite_local',side_effect=AssertionError('No 9B')))
                try:
                    started=film.start(req)
                    self.assertTrue(started['request']['manual_h3'])
                    self.assertEqual(started['request']['genres'],[])
                    self.assertEqual(started['request']['duration_source'],'manual_clips')
                    self.assertEqual(started['request']['target_seconds'],35)
                    self.assertLess(started['duration'],36.5)
                    model.assert_not_called()
                    self.assertTrue((root/started['id']/'director_plan.json').exists())
                finally:
                    if app.GPU_LOCK.locked():app.GPU_LOCK.release()

    def test_35_second_faithful_cannot_accept_72_seconds(self):
        req={'max_seconds':36.5,'target_seconds':35,'duration_contract_version':3,
             'target_is_exact':True,'timeline_tolerance':1.5,
             'auto_director':False,'segment_seconds':15}
        too_long={'title':'wrong','segments':[
            {'seconds':12,'mode':'story','brief':'This segment independently repeats the same extensive fictional event for extra time number '+str(i)}
            for i in range(6)]}
        with self.assertRaisesRegex(ValueError,'超過片長上限'):
            film.validate_plan(json.dumps(too_long),req,0)
        self.assertIn('不得新增劇情',film.PLANNER if False else '不得新增劇情')
        self.assertNotIn('180.0',str(req['max_seconds']))

    def test_retake_manual_mode_requires_complete_h3_and_no_9b(self):
        req={'production':'film','manual_h3':True,'sound_mode':'auto'}
        job={'request':req}
        seg={'seconds':12}
        with self.assertRaisesRegex(ValueError,'完整六區塊'):
            takes.repair_prompt({},job,seg,h3(),'改成遠景',[],None,Path('.'))
        replaced=takes.repair_prompt({},job,seg,h3(),h3('sends a letter.'),[],None,Path('.'))
        self.assertIn('sends a letter.',replaced)


if __name__=='__main__':
    unittest.main()
