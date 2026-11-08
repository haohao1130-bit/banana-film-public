"""Fixed identity handoff survives planning, review, continuity and retakes."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from banana_mv import film, server as app
import test_film as film_tests
from test_film import draft


class FixedReferenceTests(unittest.TestCase):
    def fixture(self, root):
        photo,work,req,job,cfg=film_tests.FilmTests().fixture(root)
        req['fixed_reference_version']=1
        return photo,work,req,job,cfg

    def plan(self):
        d=draft()
        d['shared_setup']='<Picture 1> = 林先生, the courier. Fixed location: shrine plaza. Supporting adult attendant wears a green coat; no reference picture assigned.'
        return d

    def test_required_setup_is_validated_and_sparse_slot_numbers_are_bound(self):
        req={'max_seconds':30,'segment_seconds':10,'fixed_reference_version':1,'image_slots':['one',None,'three']}
        d=self.plan();d['shared_setup']='@圖片1 = 老師; @圖片3 = 學生. Fixed location: shrine.'
        d['segments'][0]['brief']='@圖片3 places the broom beside a pillar and greets @圖片1. Both actors remain facing each other.'
        plan=film.validate_plan(json.dumps(d),req,2)
        self.assertIn('<Picture 2> = 學生',plan['shared_setup'])
        self.assertEqual(plan['segments'][1]['fixed_reference_settings'],plan['shared_setup'])
        for shared in ('', '<Picture 1> = 老師.', '<Picture 1> = 老師; <Picture 3> = 學生.'):
            d['shared_setup']=shared
            with self.assertRaises(ValueError):film.validate_plan(json.dumps(d),req,2)

    def test_cached_plan_and_local_writer_keep_fixed_settings_without_whole_story(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo,work,req,job,cfg=self.fixture(Path(tmp))
            with patch.object(app,'job_dir',return_value=work),patch.object(app.backend,'rewrite_local',return_value=json.dumps(self.plan())) as model:
                first=film.plan_film(cfg,job,[photo]);second=film.plan_film(cfg,job,[photo])
                self.assertEqual(first,second);self.assertEqual(model.call_count,1)
            job.update(first)
            with patch.object(app,'job_dir',return_value=work),patch.object(app.backend,'rewrite_local',return_value='[Shot 1] <Picture 1> withdraws her hand.') as model:
                film.write_prompt(cfg,job,job['segments'][1],[photo])
            task=json.loads(model.call_args.args[2][0][1])
            self.assertEqual(task['fixed_reference_settings'],first['shared_setup'])
            self.assertNotIn('FULL_STORY_SECRET',json.dumps(task))
            self.assertNotIn('slides one sealed',json.dumps(task))

    def test_tail_offsets_fixed_bindings_and_retake_keeps_identity_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo,work,req,job,cfg=self.fixture(Path(tmp));plan=film.validate_plan(json.dumps(self.plan()),req,1);job.update(plan)
            with patch.object(app,'job_dir',return_value=work),patch.object(app.backend,'rewrite_local',return_value='[Shot 1] <Picture 2> withdraws her hand.') as model:
                film.write_prompt(cfg,job,job['segments'][1],[photo],photo,correction='Change light only',base='original prompt',dest=work)
            task=json.loads(model.call_args.args[2][0][1])
            self.assertIn('<Picture 2> = 林先生',task['fixed_reference_settings'])
            self.assertNotIn('<Picture 1>',task['fixed_reference_settings'])
            self.assertIn('<Picture 1>',task['continuity_reference'])
            self.assertIn('<Picture 2>',task['current_clip_commission'])
            self.assertEqual(task['local_correction'],'Change light only')

    def test_manual_save_preserves_shared_setup_not_present_in_visible_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo,work,req,job,cfg=self.fixture(Path(tmp));plan=film.validate_plan(json.dumps(self.plan()),req,1)
            job.update(plan,status='script_ready',script_revision='revision')
            visible=film.review_draft(job);self.assertNotIn('shared_setup',visible)
            (work/'director_plan.json').write_text(json.dumps(dict(plan,input_sha256='original')))
            with patch.object(app,'read_state',return_value=job),patch.object(app,'job_dir',return_value=work),patch.object(app,'write_state'),patch.object(app.backend,'load_config',return_value=cfg):
                saved=film.save_script(job['id'],visible,'revision')
            self.assertEqual(saved['shared_setup'],plan['shared_setup'])
            self.assertEqual(saved['segments'][0]['fixed_reference_settings'],plan['shared_setup'])
            self.assertEqual(json.loads((work/'director_plan.json').read_text())['shared_setup'],plan['shared_setup'])

    def test_revision_receives_and_preserves_fixed_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo,work,req,job,cfg=self.fixture(Path(tmp));plan=film.validate_plan(json.dumps(self.plan()),req,1)
            job.update(plan,status='script_ready',script_revision='revision')
            visible=film.review_draft(job)
            (work/'director_plan.json').write_text(json.dumps(dict(plan,input_sha256='original')))
            with patch.object(app,'read_state',return_value=job),patch.object(app,'job_dir',return_value=work),patch.object(app,'write_state'),patch.object(app.backend,'load_config',return_value=cfg),patch.object(film,'inputs',return_value=([photo],None,None)),patch.object(app.backend,'rewrite_local',return_value=json.dumps(self.plan())) as model:
                saved=film.revise_script(job['id'],visible,'revision','Make the opening faster')
            task=json.loads(model.call_args.args[2][0][1])
            self.assertEqual(task['fixed_reference_settings'],plan['shared_setup'])
            self.assertEqual(saved['shared_setup'],plan['shared_setup'])


if __name__=='__main__':unittest.main()
