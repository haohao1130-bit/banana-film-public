"""Offline regressions for authored 30s Film SHOT handoff.

A real user case had a SHOT spanning two clips: the preceding clip got only
its camera note, and the next spoke a replay-style Chinese stage direction.
These tests use the same time structure; no GPU and no 9B are needed.
"""
import re
import unittest
from unittest.mock import patch

from banana_mv import film_continuity, film_manual, film_media, timed_slots


def story():
    return """角色設定
(S1) = <Picture 1> = 小語。
(S2) = <Picture 2> = 男主角。
人物外貌以參考圖為準。
16:9橫屏。
場景：公寓騎樓。

SHOT 01｜0.00–5.00秒
雙人中景。
男主角背著筆電包。
小語看著男主角，問：
(S1)「你真的要走？」
男主角抬頭回答：
(S2)「我必須走。」

SHOT 02｜5.00–10.00秒
小語眼眶泛紅。
她努力擠出笑容。
小語輕聲問：
(S1)「你不是答應了嗎？」
她的眼睛開始濕潤。
男主角回答：
(S2)「我知道。」
她望著雨後的街道。

SHOT 03｜10.00–15.00秒
男主角閉眼一瞬。
他吞嚥，沉默片刻。
小語抬起頭。
男主角低聲說：
(S2)「它快撐不住了。」
小語追問：
(S1)「誰？」

SHOT 04｜15.00–20.00秒
兩人對望。
男主角神情嚴肅。
男主角低聲補充：
(S2)「丹爐。」
小語嘴唇微張，一時間說不出話。
雨後車聲響起。

SHOT 05｜20.00–25.00秒
小語眼眶泛紅。
淚水滑落。
小語終於開口：
(S1)「那我呢？」
男主角伸手卻停住。
她深呼吸。

SHOT 06｜25.00–30.00秒
兩人沉默。
男主角試著道歉。
男主角說：
(S2)「下次帶妳去。」
小語回應：
(S1)「上次也是這樣說。」
鏡頭拉遠並切黑。

聲音與表演控制
全片使用自然台灣華語，原生同步對白。
電影攝影控制
SHOT 01：建立離別氣氛。
SHOT 02：小語特寫，捕捉委屈與含淚表情。
SHOT 03：男主角特寫，呈現悲壯的使命感。
SHOT 04：雙人中近景，呈現真相揭露。
SHOT 05：小語臉部特寫，呈現真正失望。
SHOT 06：兩人沉默後拉遠。
核心敘事
演員真誠演出。
"""


class FilmShotHandoffTests(unittest.TestCase):
    def generated(self):
        # The original reproduction produced 4 legal clips for a 30s commission.
        return film_manual.distribute_manual_prompt([(10, story())], 30, 10)

    def test_30s_shot_notes_never_form_unperformed_h3_shot(self):
        clips=self.generated()
        self.assertEqual(len(clips), 4)
        self.assertAlmostEqual(sum(sec for sec,_ in clips),29.875,places=3)
        for i,(seconds,prompt) in enumerate(clips):
            with self.subTest(clip=i):
                self.assertIn('detailed_description:',prompt)
                self.assertIn('Only text enclosed in <d> is spoken',prompt)
                self.assertNotIn('ALREADY ESTABLISHED',prompt)
                self.assertNotIn('PYTHON-OWNED SOURCE INTERVAL',prompt)
                self.assertNotIn('Already established before this clip',prompt)
                details=prompt.split('detailed_description:\n',1)[1].split('\n\noverall_soundscape:',1)[0]
                for shot in re.split(r'(?=\[Shot \d+\])',details):
                    if not shot.strip(): continue
                    performed=shot.split('Constraints for THIS chapter only')[0]
                    self.assertTrue(len(performed.splitlines())>=2,performed)
                    self.assertNotIn('continue without replay',performed)
                    self.assertTrue(re.search(r'(?:[\u4e00-\u9fff]|<d>)',performed),performed)
        # SHOT 02 is split across first two windows, but both parts contain a
        # genuine performed action rather than just the camera constraint.
        chunks=[text for _,text in clips if '小語特寫，捕捉委屈' in text]
        self.assertEqual(len(chunks),2)
        for chunk in chunks:
            self.assertIn('detailed_description:',chunk)
            self.assertTrue(any(token in chunk for token in ('小語眼眶泛紅','她的眼睛開始濕潤','你不是答應了嗎','我知道')))

    def test_authored_dialogue_kept_once_and_not_voiced_as_history(self):
        clips=self.generated()
        joined='\n'.join(text for _,text in clips)
        for utterance in (
            '你真的要走？','我必須走。','你不是答應了嗎？','我知道。',
            '它快撐不住了。','誰？','丹爐。','那我呢？',
            '下次帶妳去。','上次也是這樣說。'
        ):
            self.assertEqual(joined.count(f'<d>[Chinese] {utterance}</d>'),1,utterance)
        self.assertNotIn('ALREADY ESTABLISHED; continue without replay:',joined)

    def test_previous_chinese_stage_direction_is_not_repeated_in_new_shot(self):
        frag=("USER-SPECIFIED FILM TIME — active time inside THIS clip is 0.000–5.000s.\n"
              "ALREADY ESTABLISHED; continue without replay: 小語嘴唇微張，一時間說不出話。\n"
              "鏡頭拍攝小語慢慢抬頭。\n"
              "(S1)「可是……」\n"
              "Constraints for THIS chapter only (not extra events):\n"
              "- 小語特寫。")
        # The compiler must sanitize old stored allocator text as well.
        result=film_manual.compile_storyboard_slot('角色：小語。',frag,8,8)
        detail=result.split('detailed_description:\n',1)[1].split('overall_soundscape:',1)[0]
        self.assertIn('<d>[Chinese] 可是……</d>',detail)
        self.assertNotIn('一時間說不出話',detail)
        self.assertIn('小語特寫',detail)
        with self.assertRaisesRegex(ValueError,'沒有當段演出'):
            film_manual.compile_storyboard_slot('角色：小語。',
                "USER-SPECIFIED FILM TIME — active time inside THIS clip is 0.000–8.000s.\n"
                "ALREADY ESTABLISHED; continue without replay: 小語嘴唇微張。\n"
                "Constraints for THIS chapter only (not extra events):\n"
                "- 小語特寫。",8,8)

    def test_manual_plan_no_music_template_history_and_legal_timing(self):
        clips=self.generated()
        req={'max_seconds':31.5,'target_seconds':30,'target_is_exact':True,
             'timeline_tolerance':1.5,'segment_seconds':10,'sound_mode':'auto',
             'python_manual_handoff':True}
        plan=film_manual.make_manual_plan(clips,req,lambda text,n:text,
                                          lambda req,text,n:text,2,
                                          lambda text,duration,sound:text)
        self.assertLessEqual(abs(plan['duration']-30),1.5)
        self.assertTrue(all('continuity_context' not in row for row in plan['segments']))
        self.assertTrue(all('Follow the authored music cues' not in row.get('continuity_context','')
                            for row in plan['segments']))

    def test_chain5_vs_single_tail_and_audio_video_trim_alignment(self):
        job={'request':{'production':'film','mode':'chain5'}}
        seg={'index':1}
        self.assertEqual(film_continuity.motion_prefix(job,seg),5)
        job['request']['mode']='chain'
        self.assertEqual(film_continuity.motion_prefix(job,seg),0)
        graph={'7':{'class_type':'MiniMaxH3ReferenceToVideo','inputs':{'length':175}},
               '9':{'inputs':{'conditioning':['7',0]}}}
        film_continuity.add_motion_guide(graph,[f'frame_{i}.png' for i in range(5)],175)
        self.assertIn('motion_guide',graph)
        self.assertEqual(sum(k.startswith('motion_frame_') for k in graph),5)
        self.assertEqual(graph['motion_guide']['inputs']['frame_idx'],0)
        with patch.object(film_media,'require_audio'), \
             patch.object(film_media,'command') as cmd, \
             patch.object(film_media,'probe',return_value={'streams':[{'codec_type':'video','nb_frames':175}]}):
            film_media.trim_native('source.mp4','part.mp4',175,prefix_frames=5)
        args=cmd.call_args.args[0]
        self.assertIn('trim=start_frame=5:end_frame=180',args[args.index('-vf')+1])
        self.assertIn('atrim=start=0.208333333',args[args.index('-af')+1])
        self.assertIn('end=7.500000000',args[args.index('-af')+1])
        # Software trimming is aligned, but cannot alone prove that the H3
        # model leaves the first 0.208 seconds free of spoken phonemes.


if __name__=='__main__':
    unittest.main()
