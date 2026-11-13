"""Native five-frame guide wiring and real RGB/audio overlap delivery, no GPU."""
import copy
from contextlib import ExitStack
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
from banana_mv import film, server as app, takes
from banana_mv.core import build_workflow, probe, assemble
from banana_mv.film_media import trim_native
from banana_mv.film_continuity import motion_prefix,render_frames,prepare_motion_tail,add_motion_guide
import test_film as film_tests


class MotionGraphTests(unittest.TestCase):
    def test_five_frame_guide_preserves_all_nine_reference_ordinals(self):
        graph=build_workflow([f'actor{i}.png' for i in range(9)],None,64,64,226,'prompt',1,native_audio=True)
        refs={k:v for k,v in graph['7']['inputs'].items() if k.startswith('ref_images.')}
        add_motion_guide(graph,[f'tail{i}.png' for i in range(5)],226)
        self.assertEqual(graph['7']['inputs']['length'],243)
        self.assertEqual(refs,{k:v for k,v in graph['7']['inputs'].items() if k.startswith('ref_images.')})
        self.assertEqual(graph['motion_guide']['inputs']['positive'],['7',0])
        self.assertEqual(graph['motion_guide']['inputs']['latent'],['7',1])
        self.assertEqual(graph['motion_guide']['inputs']['frame_idx'],0)
        self.assertEqual(graph['9']['inputs']['conditioning'],['motion_guide',0])
        self.assertNotIn('17',graph)
        for i in range(5):self.assertEqual(graph[f'motion_frame_{i}']['inputs']['image'],f'tail{i}.png')
        self.assertEqual(graph['motion_batch_4']['inputs']['image2'],['motion_frame_4',0])

    def test_prefix_only_for_later_native_motion_clips_and_legal_render_grid(self):
        job={'request':{'production':'film','mode':'chain5'}}
        self.assertEqual(motion_prefix(job,{'index':0}),0)
        self.assertEqual(motion_prefix(job,{'index':1}),5)
        job['request']['mode']='chain'
        self.assertEqual(motion_prefix(job,{'index':1}),0)
        for frames in (124,141,226,345):
            self.assertGreaterEqual(render_frames(frames),frames+5)
            self.assertEqual(render_frames(frames)%17,5)
            self.assertLessEqual(render_frames(frames),362)

    def test_local_writer_keeps_bindings_unshifted_in_motion_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo,work,req,job,cfg=film_tests.FilmTests().fixture(Path(tmp));req['mode']='chain5'
            plan=film.validate_plan(json.dumps(dict(film_tests.draft(),shared_setup='<Picture 1> = courier.')),req,1);job.update(plan)
            with patch.object(app,'job_dir',return_value=work),patch.object(app.backend,'rewrite_local',return_value='[Shot 1] <Picture 1> withdraws her hand.') as model:
                film.write_prompt(cfg,job,job['segments'][1],[photo])
            task=json.loads(model.call_args.args[2][0][1])
            self.assertIn('<Picture 1>',task['fixed_reference_settings'])
            self.assertNotIn('<Picture 2>',json.dumps(task))
            self.assertIn('five',task['motion_context'])
            self.assertNotIn('FULL_STORY_SECRET',json.dumps(task))

    def test_worker_renders_extra_context_and_trims_only_later_clips(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo,work,req,job,cfg=film_tests.FilmTests().fixture(Path(tmp));req['mode']='chain5'
            job.update(film.validate_plan(json.dumps(film_tests.draft()),req,1));graphs=[];trims=[]
            def queue(cfg,g):graphs.append(copy.deepcopy(g));return str(len(graphs))
            def trim(src,dst,frames,**kw):trims.append(kw.get('prefix_frames',0));dst.write_bytes(b'part')
            with ExitStack() as stack:
                stack.enter_context(patch.object(app,'job_dir',return_value=work));stack.enter_context(patch.object(app,'write_state'))
                stack.enter_context(patch.object(app,'preflight'));stack.enter_context(patch.object(app,'valid_part',return_value=True))
                stack.enter_context(patch.object(app.backend,'rewrite_local',return_value='[Shot 1] <Picture 1> acts.'))
                stack.enter_context(patch.object(app.backend,'queue_prompt',side_effect=queue))
                stack.enter_context(patch.object(app,'wait_generation',return_value={}))
                stack.enter_context(patch.object(app,'video_info',return_value={}))
                stack.enter_context(patch.object(app.backend,'comfy_download',side_effect=lambda c,e,p:p.write_bytes(b'raw')))
                prepare=stack.enter_context(patch('banana_mv.film_continuity.upload_motion_tail',return_value=([f'tail{i}.png' for i in range(5)],{'source_sha256':'source'})))
                stack.enter_context(patch.object(film,'trim_native',side_effect=trim))
                stack.enter_context(patch.object(film,'require_audio'))
                stack.enter_context(patch.object(app,'assemble',side_effect=lambda parts,song,dst,*_:dst.write_bytes(b'final')))
                stack.enter_context(patch.object(app,'export_finished_video'))
                app.GPU_LOCK.acquire();film.worker(job,cfg,[photo])
            self.assertEqual(job['status'],'done',job.get('error'))
            self.assertEqual(trims,[0,5]);self.assertNotIn('motion_guide',graphs[0]);self.assertIn('motion_guide',graphs[1])
            self.assertEqual(prepare.call_args.args[1].name,'00_part_v1.mp4')
            self.assertEqual(graphs[1]['7']['inputs']['length'],render_frames(job['segments'][1]['frames']))

    def test_adjacent_retakes_use_the_new_previous_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo,work,req,job,cfg=film_tests.FilmTests().fixture(Path(tmp));req['mode']='chain5'
            job.update(film.validate_plan(json.dumps(film_tests.draft()),req,1),status='retaking',retake={'completed':0})
            batch=[];graphs=[];trims=[]
            for i,seg in enumerate(job['segments']):
                take={'id':str(i+1)*12,'version':2,'seed':10+i,'status':'waiting'}
                seg.update(status='done',selected_take='original',prompt='[Shot 1] <Picture 1> acts.',
                    takes=[{'id':'original','version':1,'seed':i,'status':'ready'},take])
                (work/f'{i:02d}_part_v1.mp4').write_bytes(b'old');batch.append((i,take))
            def trim(src,dst,frames,**kw):trims.append(kw.get('prefix_frames',0));dst.write_bytes(b'new')
            with ExitStack() as stack:
                stack.enter_context(patch.object(app,'job_dir',return_value=work));stack.enter_context(patch.object(app,'write_state'))
                stack.enter_context(patch.object(app,'preflight'));stack.enter_context(patch.object(app,'valid_part',return_value=True))
                stack.enter_context(patch.object(app.backend,'queue_prompt',side_effect=lambda c,g:graphs.append(copy.deepcopy(g)) or 'pid'))
                stack.enter_context(patch.object(app,'wait_generation',return_value={}))
                stack.enter_context(patch.object(app,'video_info',return_value={}))
                stack.enter_context(patch.object(app.backend,'comfy_download',side_effect=lambda c,e,p:p.write_bytes(b'raw')))
                prepare=stack.enter_context(patch('banana_mv.film_continuity.upload_motion_tail',return_value=([f'tail{i}.png' for i in range(5)],{'source_sha256':'new-source'})))
                stack.enter_context(patch('banana_mv.film_media.trim_native',side_effect=trim))
                app.GPU_LOCK.acquire();takes.retake_worker(job,cfg,None,None,batch,'done',[photo])
            self.assertEqual(job['retake']['status'],'done',job['retake'].get('error'))
            self.assertEqual(prepare.call_args.args[1].name,'00_part_v2.mp4')
            self.assertEqual(batch[1][1]['previous_take'],batch[0][1]['id'])
            self.assertEqual(trims,[0,5]);self.assertIn('motion_guide',graphs[1])
            self.assertEqual(job['segments'][0]['selected_take'],'original')

    def test_resume_invalidates_later_motion_clips_after_missing_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo,work,req,job,cfg=film_tests.FilmTests().fixture(Path(tmp));req['mode']='chain5'
            job.update(film.validate_plan(json.dumps(film_tests.draft()),req,1),status='interrupted')
            for i,seg in enumerate(job['segments']):seg.update(status='done',prompt_id=f'old-{i}')
            with ExitStack() as stack:
                stack.enter_context(patch.object(app,'read_state',return_value=job));stack.enter_context(patch.object(app,'write_state'))
                stack.enter_context(patch.object(app.backend,'load_config',return_value=cfg))
                stack.enter_context(patch.object(app.backend,'comfy',return_value={'queue_running':[],'queue_pending':[]}))
                stack.enter_context(patch.object(app,'project_inputs',return_value=([photo],None,None)))
                stack.enter_context(patch.object(app,'adopted_part',side_effect=lambda j,s:work/f'{s["index"]}.mp4'))
                stack.enter_context(patch.object(app,'valid_part',side_effect=lambda p,*_:p.name=='1.mp4'))
                stack.enter_context(patch('banana_mv.film_media.require_audio'))
                stack.enter_context(patch.object(app,'preflight'));stack.enter_context(patch.object(app.threading,'Thread'))
                try:app.resume(job['id'])
                finally:
                    if app.GPU_LOCK.locked():app.GPU_LOCK.release()
            self.assertEqual([s['status'] for s in job['segments']],['waiting','waiting'])
            self.assertNotIn('prompt_id',job['segments'][1]);self.assertTrue(job['segments'][1]['refresh_prompt'])


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'ffmpeg required')
class MotionMediaTests(unittest.TestCase):
    def make_video(self,root):
        for i in range(34):Image.new('RGB',(64,64),'red' if i<5 else 'blue' if i<29 else 'green').save(root/f'{i:02d}.png')
        raw=root/'raw.mp4'
        tone='aevalsrc=if(lt(t\\,0.208333333)\\,0.3*sin(2*PI*440*t)\\,0.3*sin(2*PI*880*t)):s=48000:d=1.416666667'
        subprocess.run(['ffmpeg','-v','error','-framerate','24','-i',str(root/'%02d.png'),'-f','lavfi','-i',tone,
                        '-frames:v','34','-c:v','libx264','-threads','1','-crf','0','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(raw)],check=True)
        return raw

    def test_real_prefix_trim_retains_exact_length_rgb_and_new_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=self.make_video(root);part=root/'part.mp4'
            trim_native(raw,part,24,prefix_frames=5)
            info=probe(part);video=next(s for s in info['streams'] if s['codec_type']=='video')
            self.assertEqual(int(video['nb_frames']),24)
            for second in (0,.95):
                pixel=subprocess.check_output(['ffmpeg','-v','error','-ss',str(second),'-i',str(part),'-frames:v','1','-vf','scale=1:1','-pix_fmt','rgb24','-f','rawvideo','-'])
                self.assertGreater(pixel[2],200);self.assertLess(pixel[0],15)
            pcm=np.frombuffer(subprocess.check_output(['ffmpeg','-v','error','-i',str(part),'-map','0:a:0','-ar','48000','-ac','1','-f','f32le','-']),dtype=np.float32)
            fft=np.abs(np.fft.rfft(pcm[2000:12000]));frequency=np.fft.rfftfreq(10000,1/48000)[fft.argmax()]
            self.assertAlmostEqual(frequency,880,delta=10)
            final=root/'final.mp4';assemble([part,part],None,final,2,(64,64))
            self.assertAlmostEqual(float(probe(final)['format']['duration']),2,delta=.06)

    def test_real_tail_uses_delivered_final_five_frames_not_raw_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=self.make_video(root);part=root/'part.mp4';trim_native(raw,part,24,prefix_frames=5)
            names,receipt=prepare_motion_tail(part,root/'context',root/'input','motion')
            self.assertEqual(receipt['source_frame_interval'],[19,24]);self.assertEqual(len(names),5)
            for name in names:
                pixel=Image.open(root/'input'/name).getpixel((32,32));self.assertGreater(pixel[2],200);self.assertLess(pixel[0],15)
            self.assertTrue(raw.is_file());self.assertTrue(part.is_file())

    def test_real_tail_keeps_five_distinct_frames_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for i in range(12):Image.new('RGB',(64,64),(i*15,0,255-i*15)).save(root/f'{i:02d}.png')
            video=root/'delivered.mp4'
            subprocess.run(['ffmpeg','-v','error','-framerate','24','-i',str(root/'%02d.png'),'-frames:v','12','-c:v','libx264','-threads','1','-crf','0','-pix_fmt','yuv420p',str(video)],check=True)
            names,receipt=prepare_motion_tail(video,root/'context',root/'input','ordered')
            self.assertEqual(receipt['source_frame_interval'],[7,12])
            reds=[Image.open(root/'input'/name).getpixel((32,32))[0] for name in names]
            self.assertEqual(reds,sorted(reds));self.assertEqual(len(set(reds)),5)
            self.assertAlmostEqual(reds[0],105,delta=4);self.assertAlmostEqual(reds[-1],165,delta=4)


if __name__=='__main__':unittest.main()
