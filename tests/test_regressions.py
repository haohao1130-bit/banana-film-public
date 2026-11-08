"""Synthetic bug fixtures exercise validators and the actual planning call chain.

These are model-contract regressions, not real GPU/9B quality measurements.
"""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from PIL import Image

from banana_mv.scene_state import (SceneStateError, initial_state, ensure_scene_state,
                                   normalize_garments)
from banana_mv.story_plan import allocation_errors, ensure_plan

FIXTURES=Path(__file__).parent/'fixtures'/'regressions'


def fixture(name):
    return json.loads((FIXTURES/(name+'.json')).read_text(encoding='utf-8'))


def timeline(n=8):
    return [{'index':i,'start':i*10,'seconds':10,'segment_count':n,'song_seconds':n*10}
            for i in range(n)]


class GarmentRegression(unittest.TestCase):
    def setUp(self):
        self.raw=fixture('scene_state_garments_mapping')['model_output']

    def test_dictionary_categories_rekey_to_explicit_ids_without_changing_state(self):
        before=deepcopy(self.raw)
        state,_=initial_state(self.raw,timeline(),1)
        garments=state['character_states']['S1']['garments']
        self.assertEqual(set(garments),{'shirt_1','shoes_1'})
        self.assertEqual(garments['shirt_1'],self.raw['initial_state']['character_states']['S1']['garments']['top'])
        self.assertEqual(self.raw,before)
        self.assertEqual(normalize_garments(garments,'S1'),garments)

    def test_full_initializer_accepts_fixture_with_one_model_call(self):
        model=Mock(return_value=json.dumps(self.raw))
        with tempfile.TemporaryDirectory() as tmp:
            image=Path(tmp)/'ref.png';Image.new('RGB',(8,8)).save(image)
            ledger=ensure_scene_state({}, {'prompt':'A performer enters a studio','rewrite_retries':3},
                                      timeline(),[image],tmp,model)
            self.assertEqual(model.call_count,1)
            self.assertIn('shirt_1',ledger['initial_state']['character_states']['S1']['garments'])
            self.assertTrue((Path(tmp)/'scene_state.json').is_file())

    def test_invalid_status_has_precise_path_and_is_not_guessed(self):
        self.raw['initial_state']['character_states']['S1']['garments']['top']['current_status']='wearing-ish'
        with self.assertRaises(SceneStateError) as caught:
            initial_state(self.raw,timeline(),1)
        self.assertEqual(caught.exception.errors[0]['path'],
                         '$.initial_state.character_states.S1.garments.top.current_status')

    def test_missing_id_or_duplicate_id_still_rejected(self):
        for kind in ('missing','duplicate'):
            raw=deepcopy(self.raw)
            clothes=raw['initial_state']['character_states']['S1']['garments']
            if kind=='missing':del clothes['top']['garment_id']
            else:clothes['footwear']['garment_id']='shirt_1'
            with self.subTest(kind=kind),self.assertRaises(SceneStateError):
                initial_state(raw,timeline(),1)

    def test_identical_invalid_output_stops_after_one_repair_and_retains_debug(self):
        self.raw['initial_state']['character_states']['S1']['garments']['top']['current_status']='invalid'
        model=Mock(return_value=json.dumps(self.raw))
        with tempfile.TemporaryDirectory() as tmp:
            image=Path(tmp)/'ref.png';Image.new('RGB',(8,8)).save(image)
            with self.assertRaisesRegex(SceneStateError,'無進展'):
                ensure_scene_state({}, {'prompt':'studio','rewrite_retries':3},timeline(),[image],tmp,model)
            self.assertEqual(model.call_count,2)
            self.assertFalse((Path(tmp)/'scene_state.json').exists())
            debug=json.loads((Path(tmp)/'scene_state_init_debug.json').read_text())
            self.assertTrue(debug['attempts'][-1]['repeated_failure'])

    def test_repair_can_fix_real_error_within_budget(self):
        invalid=deepcopy(self.raw)
        invalid['initial_state']['character_states']['S1']['garments']['top']['current_status']='invalid'
        model=Mock(side_effect=[json.dumps(invalid),json.dumps(self.raw)])
        with tempfile.TemporaryDirectory() as tmp:
            image=Path(tmp)/'ref.png';Image.new('RGB',(8,8)).save(image)
            ledger=ensure_scene_state({}, {'prompt':'studio','rewrite_retries':3},timeline(),[image],tmp,model)
            self.assertEqual(model.call_count,2)
            self.assertEqual(ledger['initial_state']['character_states']['S1']['garments']['shirt_1']['current_status'],'worn')


class AllocationRegression(unittest.TestCase):
    def setUp(self):
        self.case=fixture('director_plan_repetition_and_missing_finale')
        self.sources=deepcopy(self.case['source_events'])
        # The selected ending is an intention supplied to the allocator, not a
        # keyword detector. Alternative source events remain optional.
        next(r for r in self.sources if r['id']=='finale')['narrative_role']='closure'
        next(r for r in self.sources if r['id']=='parallel_performance')['repeatable']=True
        self.req={'director':'auto','director_version':2,'optimizer_version':1,
                  'director_authority':True,'rewrite':True,'story_plan':True,
                  'prompt':'Intercut a separate concert and a contest. Preserve their distinct locations.',
                  'rewrite_retries':3}

    def good(self):
        by_id={r['id']:r for r in self.sources}
        ids=['intro','first_attack','comedy_beat','parallel_performance',
             'countdown','victory','finale','parallel_performance']
        rows=[]
        for i,eid in enumerate(ids):
            rows.append({'event':by_id[eid]['event']+(' A closing concert close-up.' if i==7 else ''),
                'mode':by_id[eid]['mode'],'source_ids':[eid], 'completed_source_ids':[eid]})
        # The belt setup and payoff are condensed together, not forced to consume
        # separate slots. Optional developments are legitimately omitted.
        rows[6]['source_ids']=['belt_gag','finale']
        rows[6]['completed_source_ids']=['belt_gag','finale']
        rows[6]['event']=by_id['belt_gag']['event']+' '+by_id['finale']['event']
        return {'closing_source_ids':['finale'],'segments':rows}

    def test_fixture_flags_repetition_and_missing_closure(self):
        errors=allocation_errors(self.sources,self.case['segments'],['finale'])
        self.assertTrue(any('replays completed' in e for e in errors))
        self.assertTrue(any('closure' in e for e in errors))

    def test_actual_planner_repairs_degenerate_eight_segment_output_and_caches(self):
        bad=deepcopy(self.case)
        for row in bad['segments']:
            refs=[r['id'] for r in self.sources if r['event']==row['event']]
            row.update(source_ids=refs,completed_source_ids=refs)
        bad['closing_source_ids']=['finale']
        model=Mock(side_effect=[json.dumps({'events':self.sources}),json.dumps(bad),json.dumps(self.good())])
        with tempfile.TemporaryDirectory() as tmp:
            plan=ensure_plan({},self.req,timeline(),[],tmp,model)
            rows=plan['segments']
            self.assertEqual(len(rows),8)
            self.assertEqual(allocation_errors(self.sources,rows,['finale']),[])
            self.assertIn('belt_gag',rows[6]['source_ids'])
            self.assertEqual(rows[7]['mode'],'performance') # aftermath after resolution
            self.assertNotIn('finale',rows[7]['source_ids'])
            self.assertEqual(model.call_count,3)
            full_task=model.call_args_list[1].args[2][-1][1]
            self.assertIn('parallel_performance',full_task)
            self.assertIn('finale',full_task)
            self.assertIn('segments[',model.call_args_list[2].args[2][-1][1])
            no_model=Mock(side_effect=AssertionError('saved plan must be reused'))
            cached=ensure_plan({},self.req,timeline(),[],tmp,no_model)
            self.assertEqual(cached,plan)
            self.assertEqual(no_model.call_count,0)

    def test_unchanged_bad_plan_fails_instead_of_silently_accepting(self):
        bad=self.good();bad['segments'][6]=deepcopy(bad['segments'][4])
        model=Mock(side_effect=[json.dumps({'events':self.sources})]+[json.dumps(bad)]*4)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'全曲分段無法'):
                ensure_plan({},self.req,timeline(),[],tmp,model)
            self.assertEqual(model.call_count,3) # extraction + allocation + one repair
            self.assertFalse((Path(tmp)/'director_plan.json').exists())
            self.assertTrue((Path(tmp)/'allocation_attempt_01.json').is_file())

    def test_unfinished_action_and_repeatable_performance_can_continue(self):
        rows=self.good()['segments']
        rows[1]['completed_source_ids']=[]
        rows[2].update(source_ids=['first_attack'],completed_source_ids=['first_attack'],
                       event='The same exchange continues with a different response and counter.')
        self.assertEqual(allocation_errors(self.sources,rows,['finale']),[])

    def test_relabeling_same_complete_text_does_not_hide_replay(self):
        rows=self.good()['segments']
        rows[5]['event']=rows[4]['event']
        self.assertTrue(any('repeats the complete description' in e
                            for e in allocation_errors(self.sources,rows,['finale'])))


if __name__=='__main__':unittest.main()

