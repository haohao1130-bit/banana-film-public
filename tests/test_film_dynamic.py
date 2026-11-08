"""Dynamic generation windows and generic 85% AUTO duration contract."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from banana_mv import film, server as app
import test_film as fixtures


class DynamicFilmTests(unittest.TestCase):
    def test_auto_selector_uses_dynamic_15s_ceiling_and_keeps_manual_caps(self):
        for requested,expected,policy in [('auto',15,'dynamic'),(6,6,'capped'),(10,10,'capped'),(15,15,'capped')]:
            with tempfile.TemporaryDirectory() as tmp:
                photo,work,req,job,cfg=fixtures.FilmTests().fixture(Path(tmp))
                with ExitStack() as stack:
                    stack.enter_context(patch.object(app.backend,'load_config',return_value=cfg))
                    stack.enter_context(patch.object(app,'RUNS',photo.parent))
                    stack.enter_context(patch.object(app,'write_state'))
                    stack.enter_context(patch.object(app,'preflight'))
                    stack.enter_context(patch.object(app.backend,'comfy',return_value={'queue_running':[],'queue_pending':[]}))
                    stack.enter_context(patch.object(film.threading,'Thread'))
                    try:
                        started=film.start(dict(req,segment_seconds=requested,image_ids=[]))
                        self.assertEqual(started['request']['segment_seconds'],expected)
                        self.assertEqual(started['request']['segment_policy'],policy)
                        self.assertEqual(started['request']['planning_contract_version'],2)
                    finally:
                        if app.GPU_LOCK.locked():app.GPU_LOCK.release()

    def test_new_and_legacy_auto_have_no_minimum_duration(self):
        for policy in ('target','flexible'):
            req={'max_seconds':180,'segment_seconds':15,'auto_director':True,
                 'duration_policy':policy,'planning_contract_version':2}
            self.assertEqual(film.duration_contract(req),{})
            self.assertIsNone(film.validate_planned_duration({'duration':115.75},req))
            self.assertIsNone(film.validate_planned_duration({'duration':10},req))

    def test_10_second_failure_reports_actual_value_and_repairs_every_overlong_segment(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo,work,req,job,cfg=fixtures.FilmTests().fixture(Path(tmp))
            req.update(planning_contract_version=2,segment_policy='capped')
            bad=fixtures.draft();bad['segments'][0]['seconds']=12;bad['segments'][1]['seconds']=11
            good=fixtures.draft()
            with patch.object(app,'job_dir',return_value=work),patch.object(app.backend,'rewrite_local',side_effect=[json.dumps(bad),json.dumps(good)]) as model:
                plan=film.plan_film(cfg,job,[photo])
            self.assertEqual(len(plan['segments']),2)
            source=json.loads(model.call_args_list[0].args[2][0][1])
            self.assertEqual(source['max_clip_seconds'],10)
            self.assertLessEqual(max(source['legal_clip_seconds']),10)
            repair=json.loads(model.call_args_list[1].args[2][-1][1].split('only. ',1)[1])
            self.assertEqual(repair['invalid_segments'],[{'segment':1,'seconds':12},{'segment':2,'seconds':11}])
            self.assertIn('第 1 段排了 12 秒',repair['error'])
            self.assertIn('不要只縮短秒數',repair['instruction'])

    def test_dynamic_plan_keeps_variable_lengths_and_genre_without_extra_story_call(self):
        for genre in ('comedy','romance','horror','drama'):
            with tempfile.TemporaryDirectory() as tmp:
                photo,work,req,job,cfg=fixtures.FilmTests().fixture(Path(tmp))
                req.update(auto_director=True,duration_policy='target',planning_contract_version=2,
                           segment_policy='dynamic',segment_seconds=15,genres=[genre])
                raw=fixtures.draft();raw['segments'][0]['seconds']=14;raw['segments'][1]['seconds']=13
                with patch.object(app,'job_dir',return_value=work),patch.object(app.backend,'rewrite_local',return_value=json.dumps(raw)) as model:
                    plan=film.plan_film(cfg,job,[photo])
                    self.assertEqual(film.plan_film(cfg,job,[photo]),plan)
                self.assertEqual(model.call_count,1)
                self.assertNotEqual(plan['segments'][0]['seconds'],plan['segments'][1]['seconds'])
                source=json.loads(model.call_args.args[2][0][1])
                self.assertEqual(source['segment_policy'],'dynamic')
                self.assertEqual(source['genres'],[film.GENRES[genre]])
                self.assertIn('every genre',film.PLANNER)

    def test_local_writers_distinguish_intermediate_window_from_film_ending(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo,work,req,job,cfg=fixtures.FilmTests().fixture(Path(tmp))
            job.update(film.validate_plan(json.dumps(fixtures.draft()),req,1))
            with patch.object(app,'job_dir',return_value=work),patch.object(app.backend,'rewrite_local',return_value='[Shot 1] <Picture 1> acts.') as model:
                for seg in job['segments']:film.write_prompt(cfg,job,seg,[photo])
            tasks=[json.loads(c.args[2][0][1]) for c in model.call_args_list]
            self.assertEqual(tasks[0]['clip_boundary']['position'],'intermediate')
            self.assertEqual(tasks[1]['clip_boundary']['position'],'final')
            self.assertNotIn('FULL_STORY_SECRET',json.dumps(tasks))
            self.assertIn('The delivery boundary is',film.WRITER)
            self.assertIn('NEVER\nreassign a character',film.WRITER)
            self.assertIn('current_clip_commission',film.WRITER)
            self.assertIn('cinematography only:',tasks[0]['adaptation'])
            self.assertIn('events, actors, dialogue and outgoing state are immutable',tasks[0]['adaptation'])
            self.assertNotIn('commercial MV',model.call_args.args[1])

    def test_new_film_cinematic_setting_does_not_boost_motion_loras(self):
        req={'production':'film','intensity':'extreme','motion_lora':True,'film_motion_version':2}
        self.assertEqual(app.graph_options(req,10,{'director_mode':'action'})['intensity'],'high')
        req.pop('film_motion_version')
        self.assertEqual(app.graph_options(req,10,{'director_mode':'action'})['intensity'],'extreme')

    def test_reference_tag_spelling_is_normalized_before_fixed_cast_validation(self):
        req={'max_seconds':30,'segment_seconds':15,'fixed_reference_version':1}
        raw=fixtures.draft();raw['shared_setup']='<Picture1> = courier; <image 2> = station.'
        raw['segments'][0]['brief']=raw['segments'][0]['brief'].replace('<Picture 1>','<PICTURE1>')
        plan=film.validate_plan(json.dumps(raw),req,2)
        self.assertIn('<Picture 1>',plan['shared_setup'])
        self.assertIn('<Picture 2>',plan['shared_setup'])
        self.assertIn('<Picture 1>',plan['segments'][0]['director_plan']['event'])
        raw['shared_setup']='<Picture1> = courier.'
        with self.assertRaisesRegex(ValueError,'圖片綁定：2'):
            film.validate_plan(json.dumps(raw),req,2)

    def test_genuine_missing_reference_binding_gets_specific_repair_feedback(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo,work,req,job,cfg=fixtures.FilmTests().fixture(Path(tmp))
            req['fixed_reference_version']=1
            bad=fixtures.draft();bad['shared_setup']='The adult courier is at the station.'
            good=fixtures.draft();good['shared_setup']='<Picture 1> = the adult courier.'
            with patch.object(app,'job_dir',return_value=work),patch.object(app.backend,'rewrite_local',side_effect=[json.dumps(bad),json.dumps(good)]) as model:
                film.plan_film(cfg,job,[photo])
            repair=json.loads(model.call_args_list[1].args[2][-1][1].split('only. ',1)[1])
            self.assertEqual(repair['missing_reference_bindings'],['<Picture 1>'])


    def test_native_film_shot_times_follow_h3_guide(self):
        valid='[Shot 1] The camera frames the actors.\n[Shot 2] At 00:03.500, the view cuts to a reaction.'
        self.assertEqual(film.validate_film_format(valid,8,'ambient'),valid)
        for bad in [
            '[Shot 1] Setup.\n[Shot 2] At 00:09.000, late shot.',
            '[Shot 1] Setup.\n[Shot 2] At 00:03.500, cut.\n[Shot 3] At 00:02.500, backward.',
            '[Shot 1] Setup.\n[Shot 2] An untimed cut.',
            '[Shot 1] At 00:00.000, not the official opening form.',
            '[Shot 1] Setup.\n[Shot 3] At 00:02.500, skipped index.'
        ]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                film.validate_film_format(bad,8,'ambient')

    def test_native_film_speaker_ids_are_vocal_not_shot_local(self):
        silent='[Shot 1] <Subject 2> watches <Subject 3> act.'
        self.assertEqual(film.validate_film_format(silent,8,'ambient'),silent)
        dialogue='[Shot 1] <Subject 2> (S1) says <d>[English] Hello.</d>'
        self.assertEqual(film.validate_film_format(dialogue,8,'dialogue'),dialogue)
        wrong=[
            ('[Shot 1] <Subject 2> (S1) watches silently.', 'dialogue'),
            ('[Shot 1] <Subject 2> (S1) says <d>[English] Hello.</d>','ambient'),
            ('[Shot 1] <Subject 2> (S1) says <d>[English] Hi.</d> '
             '<Subject 3> (S1) says <d>[English] Hey.</d>', 'dialogue')
        ]
        for bad,mode in wrong:
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                film.validate_film_format(bad,8,mode)


if __name__=='__main__':unittest.main()
