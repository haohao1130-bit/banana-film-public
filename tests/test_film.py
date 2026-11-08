"""Offline film integration; no claim of real 9B/H3 generation quality."""
from contextlib import ExitStack
import copy
import ast
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
from PIL import Image
from banana_mv import film, server as app, takes
from banana_mv.core import build_workflow, probe, assemble
from banana_mv.film_media import trim_native, require_audio


def draft():
    return {'title':'一封信','segments':[
        {'seconds':6,'mode':'story','brief':'<Picture 1> is the adult courier at the table. She slides one sealed letter across the table and ends with her hand resting on its edge.'},
        {'seconds':6,'mode':'story','brief':'<Picture 1> is the same adult courier at the same table; her hand is already resting on the sealed letter. She withdraws her hand, looks up and holds the quiet ending.'}]}


class FilmTests(unittest.TestCase):
    def test_target_duration_rejects_nine_seconds_and_retries_upstream_with_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo,work,req,job,cfg=self.fixture(Path(tmp))
            req.update(auto_director=True,duration_policy='target')
            short={'title':'short','segments':[dict(draft()['segments'][0],seconds=10)]}
            expanded={'title':'expanded','segments':[
                {'seconds':10,'mode':'story','brief':f'<Picture 1> courier: causal event {i}; action and reaction change the situation before the next event.'}
                for i in range(3)]}
            with patch.object(app,'job_dir',return_value=work),patch.object(app.backend,'rewrite_local',side_effect=[json.dumps(short),json.dumps(expanded)]) as model:
                plan=film.plan_film(cfg,job,[photo])
                self.assertAlmostEqual(plan['duration'],28.25)
                self.assertEqual(model.call_count,2)
                source=json.loads(model.call_args_list[0].args[2][0][1])
                self.assertEqual(source['target_seconds'],30)
                self.assertEqual(source['minimum_duration_seconds'],21)
                feedback=str(model.call_args_list[1].args[2])
                self.assertIn('Previous rejected draft',feedback)
                self.assertIn('9.417',feedback)
                self.assertIn('Do not just increase seconds',feedback)
                self.assertEqual(film.plan_film(cfg,job,[photo]),plan)
                self.assertEqual(model.call_count,2)

    def test_too_short_target_exhaustion_never_reaches_h3(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo,work,req,job,cfg=self.fixture(Path(tmp))
            req.update(auto_director=True,duration_policy='target',script_review=True)
            with patch.object(app,'job_dir',return_value=work),patch.object(app,'write_state'),patch.object(app.backend,'rewrite_local',return_value=json.dumps(draft())) as model,patch.object(app.backend,'queue_prompt') as h3:
                app.GPU_LOCK.acquire();film.worker(job,cfg,[photo])
                self.assertEqual(job['status'],'error');self.assertIn('故事規劃過短',job['error'])
                self.assertEqual(model.call_count,2);h3.assert_not_called()
                self.assertFalse((work/'director_plan.json').exists())
                self.assertFalse(app.GPU_LOCK.locked())

    def test_duration_contract_is_feasible_on_all_supported_targets_and_clip_caps(self):
        for target in (6,15,30,60,120,180):
            for cap in (6,10,15):
                req={'max_seconds':target,'segment_seconds':min(cap,target),'auto_director':True,'duration_policy':'target'}
                contract=film.duration_contract(req)
                self.assertEqual(contract['minimum_duration_seconds'],math.ceil(target*24*.7)/24)
                # Independently enumerate every reachable frame sum.
                clip_frames=list(range(124,round(req['segment_seconds']*24)+1,17))
                reachable={0};possible=set()
                for _ in range(34):
                    reachable={a+b for a in reachable for b in clip_frames if a+b<=target*24}
                    possible.update(reachable)
                self.assertTrue(any(f/24>=contract['minimum_duration_seconds'] for f in possible))
        self.assertEqual(film.duration_contract({'auto_director':False,'duration_policy':'target'}),{})
        self.assertEqual(film.duration_contract({'auto_director':True}),{})

    def test_seventy_percent_gate_accepts_boundary_and_rejects_below_it(self):
        req={'max_seconds':30,'segment_seconds':10,'auto_director':True,'duration_policy':'target'}
        film.validate_planned_duration({'duration':21},req)
        with self.assertRaises(ValueError):
            film.validate_planned_duration({'duration':21-1/24},req)

    def test_manual_target_draft_can_be_short_and_reviewed_cache_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo,work,req,job,cfg=self.fixture(Path(tmp))
            req.update(auto_director=True,duration_policy='target',script_review=True)
            plan=film.validate_plan(json.dumps(draft()),req,1)
            job.update(**plan,status='script_ready',script_revision='manual')
            (work/'director_plan.json').write_text(json.dumps({'input_sha256':'old'}))
            with patch.object(app,'job_dir',return_value=work),patch.object(app,'read_state',return_value=job),patch.object(app,'write_state'),patch.object(app.backend,'load_config',return_value=cfg),patch.object(app.backend,'queue_prompt') as h3:
                saved=film.save_script(job['id'],draft(),'manual')
                self.assertEqual(saved['duration'],11.75);h3.assert_not_called()
                self.assertTrue(json.loads((work/'director_plan.json').read_text())['user_reviewed'])

    def test_film_http_entry_and_notebook_use_isolated_ui_repo_data_and_port(self):
        import os
        with patch.dict(os.environ):
            from banana_mv.film_server import Handler
        handler=object.__new__(Handler);handler.send_file=Mock();handler.send_json=Mock()
        handler.path='/';handler.do_GET()
        self.assertEqual(handler.send_file.call_args.args[0].name,'film.html')
        handler.path='/api/health';handler.do_GET()
        self.assertEqual(handler.send_json.call_args.args[0]['service'],'banana-film')
        handler.path='/api/film/start';handler.body_json=Mock(return_value={'prompt':'story'})
        with patch.object(film,'start',return_value={'id':'abc'}) as start:
            handler.do_POST();start.assert_called_once_with({'prompt':'story'})
        handler.path='/api/mv/start';handler.do_POST()
        self.assertEqual(handler.send_json.call_args.args[1],400)
        root=Path(__file__).parents[1];nb=json.loads((root/'Banana_Film_Studio.ipynb').read_text())
        text='\n'.join(''.join(c['source']) for c in nb['cells'])
        self.assertIn('https://github.com/haohao1130-bit/banana-film-public.git',text)
        self.assertIn('MyDrive/BananaFilmStudio/films/',text)
        for c in nb['cells']:
            if c['cell_type']=='code':ast.parse(''.join(c['source']))

    def fixture(self,root):
        photo=root/'photo.png';Image.new('RGB',(16,16)).save(photo)
        guide=root/'guide.md';guide.write_text('NATIVE_GUIDE')
        inp=root/'input';inp.mkdir();work=root/'aabbccddeeff';work.mkdir()
        req={'production':'film','prompt':'FULL_STORY_SECRET future ending',
             'max_seconds':30,'segment_seconds':10,'visual_style':'真人電影','sound_mode':'ambient',
             'mode':'independent','intensity':'extreme','rewrite_retries':1,'sampling_steps':8,
             'kitchen_attention':False,'sparse_attention':False,'motion_lora':False}
        job={'id':work.name,'request':req,'title':'test','segments':[],'duration':0,'seed':5,
             'created':1,'status':'planning_story','size':[64,64],'output_size':[64,64],
             'images_comfy':['photo.png'],'sources':{'images':['photo.png']},'timeline_source':'film_plan'}
        shutil.copyfile(photo,work/'photo.png')
        cfg={'guides':{'ref':str(guide)},'comfy_input_dir':str(inp),'rewriter':{'model':'9b'}}
        return photo,work,req,job,cfg

    def test_fixed_slots_do_not_renumber_and_editor_uses_logical_labels(self):
        req={'image_slots':[None,None,'asset']+[None]*6,'max_seconds':30,'segment_seconds':10}
        self.assertEqual(film.map_story(req,'@圖片3 waves',1),'<Picture 1> waves')
        with self.assertRaises(ValueError):film.map_story(req,'@圖片1 waves',1)
        data=draft();plan=film.validate_plan(json.dumps(data),req,1)
        editor=film.review_draft({'request':req,**plan})
        self.assertIn('@圖片3',editor['segments'][0]['brief'])
        self.assertEqual(film.validate_plan(json.dumps(editor),req,1),plan)

    def test_review_gate_never_calls_h3_and_revise_uses_current_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo,work,req,job,cfg=self.fixture(Path(tmp));req.update(script_review=True,genres=['comedy'])
            with ExitStack() as stack:
                stack.enter_context(patch.object(app,'job_dir',return_value=work))
                stack.enter_context(patch.object(app,'write_state'))
                stack.enter_context(patch.object(app,'read_state',side_effect=lambda _:copy.deepcopy(job)))
                stack.enter_context(patch.object(app.backend,'load_config',return_value=cfg))
                queue=stack.enter_context(patch.object(app.backend,'queue_prompt'))
                writer=stack.enter_context(patch.object(film,'write_prompt'))
                model=stack.enter_context(patch.object(app.backend,'rewrite_local',return_value=json.dumps(draft())))
                app.GPU_LOCK.acquire();film.worker(job,cfg,[photo])
                self.assertEqual(job['status'],'script_ready');queue.assert_not_called();writer.assert_not_called()
                old_revision=job['script_revision'];edited=copy.deepcopy(job['script_draft'])
                edited['segments'][0]['brief']+=' MANUAL_EDIT_KEEP_THIS'
                result=film.revise_script(job['id'],edited,old_revision,'只修改第二段')
                task=json.loads(model.call_args.args[2][0][1])
                self.assertIn('MANUAL_EDIT_KEEP_THIS',task['current_script']['segments'][0]['brief'])
                self.assertEqual(result['script_history'][0]['script'],edited)
                self.assertEqual(result['status'],'script_ready');queue.assert_not_called();writer.assert_not_called()
                self.assertFalse(app.GPU_LOCK.locked())
                with self.assertRaises(ValueError):film.save_script(job['id'],edited,'stale')
                thread=stack.enter_context(patch.object(film.threading,'Thread'))
                stack.enter_context(patch.object(app.backend,'comfy',return_value={}))
                stack.enter_context(patch.object(app,'preflight'))
                saved=film.save_script(job['id'],edited,old_revision)
                self.assertEqual(saved['status'],'script_ready');thread.assert_not_called();queue.assert_not_called()
                approved=film.save_script(job['id'],edited,old_revision,render=True)
                self.assertTrue(approved['script_approved']);self.assertEqual(approved['status'],'running')
                thread.return_value.start.assert_called_once();queue.assert_not_called()
            if app.GPU_LOCK.locked():app.GPU_LOCK.release()

    def test_failed_revision_keeps_persisted_script_and_does_not_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo,work,req,job,cfg=self.fixture(Path(tmp))
            req.update(script_review=True,genres=[])
            plan=film.validate_plan(json.dumps(draft()),req,1)
            job.update(**plan,status='script_ready',script_revision='original')
            job['script_draft']=film.review_draft(job)
            before=copy.deepcopy(job)
            with patch.object(app,'read_state',side_effect=lambda _:copy.deepcopy(job)),patch.object(app,'job_dir',return_value=work),patch.object(app,'write_state') as save,patch.object(app.backend,'load_config',return_value=cfg),patch.object(app.backend,'rewrite_local',return_value='not JSON'),patch.object(app.backend,'queue_prompt') as queue:
                with self.assertRaises(ValueError):film.revise_script(job['id'],job['script_draft'],'original','調整開頭')
                self.assertEqual(job,before);save.assert_not_called();queue.assert_not_called()
                self.assertFalse(app.GPU_LOCK.locked())

    def test_native_graph_decodes_joint_audio_without_source_lock_or_audio_loader(self):
        g=build_workflow(['a.png','b.png'],None,64,64,158,'prompt',5,'tail.png',native_audio=True)
        self.assertNotIn('6',g)
        self.assertEqual(g['7']['class_type'],'MiniMaxH3ReferenceToVideo')
        self.assertNotIn('audio_mode',g['7']['inputs'])
        self.assertEqual(g['7']['inputs']['ref_images.ref_image_0'],['17',0])
        self.assertEqual(g['7']['inputs']['ref_images.ref_image_1'],['5',0])
        self.assertEqual(g['7']['inputs']['ref_images.ref_image_2'],['ref_1',0])
        self.assertEqual(g['audio_decode']['inputs']['samples'],g['14']['inputs']['samples'])
        self.assertEqual(g['15']['inputs']['audio'],['audio_decode',0])
        old=build_workflow('a.png','song.wav',64,64,158,'prompt',5)
        self.assertEqual(old['7']['inputs']['audio_mode'],'lock_source')
        empty=build_workflow([],None,64,64,158,'A rainy port.',5,native_audio=True)
        self.assertNotIn('5',empty)
        self.assertFalse(any(n['class_type']=='LoadImage' for n in empty.values()))

    def test_planner_chooses_shorter_total_and_rejects_overlong_invalid_or_duplicate_plan(self):
        req={'max_seconds':30,'segment_seconds':10}
        plan=film.validate_plan(json.dumps(draft()),req,1)
        self.assertEqual(plan['duration'],11.75)
        self.assertEqual(plan['segments'][1]['start'],5.875)
        self.assertEqual(plan['segments'][0]['model_frames'],141)
        self.assertEqual(plan['segments'][0]['frames'],plan['segments'][0]['model_frames'])
        for bad in [dict(draft(),segments=[None]),dict(draft(),segments=[draft()['segments'][0]]*3)]:
            with self.assertRaises(ValueError):film.validate_plan(json.dumps(bad),req,1)
        with self.assertRaises(ValueError):film.validate_plan(json.dumps(draft()),{'max_seconds':10,'segment_seconds':10},1)
        d=draft();d['segments'][0]['seconds']=float('nan')
        with self.assertRaises(ValueError):film.validate_plan(json.dumps(d),req,1)
        with self.assertRaises(ValueError):film.normalize_prompt('<Audio 1>: fully_copy',1)
        with self.assertRaises(ValueError):film.normalize_prompt('<Picture 2> waves',1)

    def test_allocator_saved_once_writer_only_sees_local_script_and_shifts_tail_picture(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo,work,req,job,cfg=self.fixture(Path(tmp))
            with patch.object(app,'job_dir',return_value=work),patch.object(app.backend,'rewrite_local',return_value=json.dumps(draft())) as model:
                first=film.plan_film(cfg,job,[photo]);second=film.plan_film(cfg,job,[photo])
                self.assertEqual(first,second);self.assertEqual(model.call_count,1)
                self.assertIn('FULL_STORY_SECRET',model.call_args.args[2][0][1])
            job['segments']=first['segments'];seg=job['segments'][1]
            with patch.object(app,'job_dir',return_value=work),patch.object(app.backend,'rewrite_local',return_value='[Shot 1] <Picture 2> looks up.\noverall_soundscape: Quiet room.') as model:
                prompt=film.write_prompt(cfg,job,seg,[photo],photo)
                text=model.call_args.args[2][0][1];task=json.loads(text)
                self.assertNotIn('FULL_STORY_SECRET',text)
                self.assertNotIn('slides one sealed',text)
                self.assertIn('<Picture 2>',task['current_clip_commission'])
                self.assertIn('not a locked first frame',task['continuity_reference'])
                self.assertIn('sound_mode',task);self.assertNotIn('<Audio',prompt)

    def test_worker_generates_and_assembles_native_audio_then_resume_reuses_parts(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo,work,req,job,cfg=self.fixture(Path(tmp));calls=[]
            def render(cfg,graph):calls.append(graph);return 'pid'+str(len(calls))
            def save_raw(cfg,item,target):target.write_bytes(b'raw-av')
            def trim(source,target,frames):target.write_bytes(b'trimmed-av')
            def assembly(parts,song,target,seconds,size):
                self.assertIsNone(song);self.assertEqual(seconds,11.75);target.write_bytes(b'complete-av')
            app.GPU_LOCK.acquire()
            with ExitStack() as stack:
                stack.enter_context(patch.object(app,'job_dir',return_value=work))
                stack.enter_context(patch.object(app,'write_state'))
                stack.enter_context(patch.object(app,'preflight'))
                stack.enter_context(patch.object(app,'valid_part',side_effect=lambda p,*_:p.exists()))
                stack.enter_context(patch.object(app.backend,'rewrite_local',side_effect=[json.dumps(draft()),'[Shot 1] <Picture 1> slides letter.','[Shot 1] <Picture 1> withdraws hand.']))
                stack.enter_context(patch.object(app.backend,'queue_prompt',side_effect=render))
                stack.enter_context(patch.object(app,'wait_generation',return_value={'outputs':{}}))
                stack.enter_context(patch.object(app,'video_info',return_value={}))
                stack.enter_context(patch.object(app.backend,'comfy_download',side_effect=save_raw))
                stack.enter_context(patch.object(film,'trim_native',side_effect=trim))
                stack.enter_context(patch.object(film,'require_audio'))
                stack.enter_context(patch.object(app,'assemble',side_effect=assembly))
                stack.enter_context(patch.object(app,'export_finished_video'))
                film.worker(job,cfg,[photo])
                self.assertEqual(job['status'],'done',job.get('error'))
                self.assertEqual(job['current_master'],1)
                self.assertTrue((work/'final_v001.mp4').exists())
                self.assertEqual(len(calls),2)
                self.assertTrue(all(g['7']['class_type']=='MiniMaxH3ReferenceToVideo' for g in calls))
                app.GPU_LOCK.acquire();film.worker(job,cfg,[photo])
                self.assertEqual(job['status'],'done');self.assertEqual(len(calls),2)
                self.assertEqual(job['current_master'],2)
            self.assertFalse(app.GPU_LOCK.locked())

    def test_native_retake_does_not_slice_song_and_keeps_generated_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo,work,req,job,cfg=self.fixture(Path(tmp));plan=film.validate_plan(json.dumps(draft()),req,1)
            job.update(segments=plan['segments'],duration=12,status='retaking',retake={'status':'running','completed':0})
            for s in job['segments']:s.update(status='done',prompt='[Shot 1] <Picture 1> waits.')
            for i in range(2):(work/f'{i:02d}_part.mp4').write_bytes(b'old')
            take={'id':'112233aabbcc','version':2,'seed':9,'status':'waiting'}
            job['segments'][0].update(takes=[{'id':'original','version':1,'status':'ready','seed':8},take],selected_take='original')
            def trim(src,dst,frames):dst.write_bytes(b'new-av')
            with ExitStack() as stack:
                stack.enter_context(patch.object(app,'job_dir',return_value=work));stack.enter_context(patch.object(app,'write_state'))
                audio=stack.enter_context(patch.object(app,'audio_window'))
                stack.enter_context(patch.object(app,'preflight'))
                stack.enter_context(patch.object(app.backend,'queue_prompt',return_value='pid'))
                stack.enter_context(patch.object(app,'wait_generation',return_value={}))
                stack.enter_context(patch.object(app,'video_info',return_value={}))
                stack.enter_context(patch.object(app.backend,'comfy_download',side_effect=lambda c,i,p:p.write_bytes(b'raw')))
                stack.enter_context(patch('banana_mv.film_media.trim_native',side_effect=trim))
                stack.enter_context(patch.object(app,'valid_part',return_value=True))
                adopted=stack.enter_context(patch.object(takes,'apply_takes',return_value=True))
                app.GPU_LOCK.acquire();takes.retake_worker(job,cfg,None,None,[(0,take)],'done',[photo])
                self.assertEqual(job['status'],'done');audio.assert_not_called()
                adopted.assert_not_called()
                self.assertEqual(takes.take_file(job,0,take['id'],'part.mp4').read_bytes(),b'new-av')

    def test_film_entry_validation_never_requires_a_song(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo,work,req,job,cfg=self.fixture(Path(tmp))
            bad=[dict(req,max_seconds=181),dict(req,max_seconds=float('inf')),dict(req,prompt=''),dict(req,segment_seconds=20)]
            for r in bad:
                with patch.object(app.backend,'load_config',return_value=cfg),self.assertRaises(ValueError):film.start(r)
            with ExitStack() as stack:
                stack.enter_context(patch.object(app.backend,'load_config',return_value=cfg))
                stack.enter_context(patch.object(app.backend,'asset',return_value={'kind':'image','file':photo.name,'comfy_name':'photo.png'}))
                stack.enter_context(patch.object(app.backend,'LIBRARY',photo.parent))
                stack.enter_context(patch.object(app,'RUNS',photo.parent))
                stack.enter_context(patch.object(app,'preflight'))
                stack.enter_context(patch.object(app,'write_state'))
                stack.enter_context(patch.object(app.backend,'comfy',return_value={'queue_running':[],'queue_pending':[]}))
                stack.enter_context(patch.object(film.threading,'Thread'))
                started=film.start(dict(req,image_ids=['asset'],seed=0))
                self.assertEqual(started['seed'],0);self.assertEqual(started['segments'],[])
                self.assertEqual(started['request']['duration_policy'],'target')
                self.assertNotIn('song',started['sources']);self.assertNotIn('song_id',started['request'])
            if app.GPU_LOCK.locked():app.GPU_LOCK.release()

    def test_story_only_start_accepts_no_images_and_never_loads_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo,work,req,job,cfg=self.fixture(Path(tmp))
            with ExitStack() as stack:
                stack.enter_context(patch.object(app.backend,'load_config',return_value=cfg))
                asset=stack.enter_context(patch.object(app.backend,'asset'))
                stack.enter_context(patch.object(app,'RUNS',photo.parent))
                preflight=stack.enter_context(patch.object(app,'preflight'))
                stack.enter_context(patch.object(app,'write_state'))
                stack.enter_context(patch.object(app.backend,'comfy',return_value={'queue_running':[],'queue_pending':[]}))
                stack.enter_context(patch.object(film.threading,'Thread'))
                started=film.start(dict(req,image_ids=[]))
                self.assertEqual(started['sources']['images'],[]);asset.assert_not_called()
                graph=preflight.call_args.args[1]
                self.assertFalse(any(n['class_type'] in ('LoadImage','LoadAudio') for n in graph.values()))
            if app.GPU_LOCK.locked():app.GPU_LOCK.release()


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'ffmpeg required')
class NativeMediaTests(unittest.TestCase):
    def test_real_selected_version_assembly_keeps_native_audio_and_mixes_correct_clips(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp)
            job={'id':'abcdef123456','seed':1,'status':'done','size':[64,64],'output_size':[64,64],
                 'duration':2,'request':{'production':'film'},'segments':[]}
            for i in range(2):
                job['segments'].append({'index':i,'status':'done','frames':24,'seconds':1,
                    'selected_take':'original','takes':[{'id':'original','version':1,'status':'ready','seed':1}]})
                subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=red:s=64x64:r=24:d=1',
                    '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=1',
                    '-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(work/f'{i:02d}_part_v1.mp4')],check=True)
            tid='abcdefabcdef';job['segments'][0]['takes'].append({'id':tid,'version':2,'status':'ready','seed':2})
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=64x64:r=24:d=1',
                '-f','lavfi','-i','sine=frequency=880:sample_rate=48000:duration=1',
                '-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(work/'00_part_v2.mp4')],check=True)
            with patch.object(app,'job_dir',return_value=work),patch.object(app,'export_finished_video'):
                takes.apply_takes(job,{0:tid},None)
            require_audio(work/'final.mp4')
            for second,channel in [(0.5,2),(1.5,0)]:
                pixel=subprocess.check_output(['ffmpeg','-v','error','-ss',str(second),'-i',str(work/'final.mp4'),
                    '-frames:v','1','-vf','scale=1:1','-pix_fmt','rgb24','-f','rawvideo','-'])
                self.assertGreater(pixel[channel],200)
            self.assertEqual(job['final_versions'][-1]['takes'],{'0':tid,'1':'original'})
            self.assertTrue((work/'00_part_v1.mp4').is_file())

    def test_real_av_trim_and_join_retain_audio_without_external_song(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=root/'raw.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=64x64:r=24:d=1.2',
                            '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=1.2',
                            '-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(raw)],check=True)
            part=root/'part.mp4';trim_native(raw,part,24)
            self.assertEqual(int(probe(part)['streams'][0]['nb_frames']),24);require_audio(part)
            final=root/'final.mp4';assemble([part,part],None,final,2,(64,64))
            info=probe(final);self.assertTrue(any(s['codec_type']=='audio' for s in info['streams']))
            self.assertAlmostEqual(float(info['format']['duration']),2,delta=.06)
            pcm=subprocess.check_output(['ffmpeg','-v','error','-i',str(final),'-map','0:a:0','-f','s16le','-ac','1','pipe:1'])
            self.assertGreater(len(set(pcm)),50) # real retained tone, not substituted silence


if __name__=='__main__':unittest.main()

