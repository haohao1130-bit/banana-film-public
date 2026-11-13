"""Offline regressions for authored 30s Film SHOT handoff.

A real user case had a SHOT spanning two clips: the preceding clip got only
its camera note, and the next spoke a replay-style Chinese stage direction.
These tests use the same time structure; no GPU and no 9B are needed.
"""
import re
import unittest
from unittest.mock import patch

from banana_mv import film, film_continuity, film_manual, film_media, timed_slots


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

    def test_prompt_duration_parses_natural_brief_and_full_shot_timeline(self):
        # Film 5070 manual mode must not say "cannot detect seconds" for
        # an ordinary 40-second director instruction or a full SHOT schedule.
        self.assertEqual(film.declared_film_seconds(
            '生成一支40秒、超寫實電影質感、原生台灣華語的雙人劇情短片。'),40)
        self.assertEqual(film.declared_film_seconds(
            '請製作一部 40 秒的電影。全片40秒。'),40)
        self.assertEqual(film.declared_film_seconds(
            '全片 40 秒。第 5 秒切鏡，男主角沉默半秒。'),40)
        self.assertEqual(film.declared_film_seconds(
            '\n'.join(f'SHOT {i+1:02d}｜{i*5:.2f}–{(i+1)*5:.2f}秒'
                      for i in range(8))),40)
        # Isolated action timestamps and incomplete/gapped SHOT scripts are
        # NOT a declaration of total runtime.
        self.assertIsNone(film.declared_film_seconds('第 40 秒切至街道。'))
        self.assertIsNone(film.declared_film_seconds(
            'SHOT 01｜0.00–5.00秒\nSHOT 02｜10.00–15.00秒'))
        with self.assertRaisesRegex(ValueError,'不同的全片秒數'):
            film.declared_film_seconds('全片 35 秒。製作一支 40 秒影片。')

    def test_sixty_second_shared_setup_is_a_full_order_for_every_clip(self):
        # Classic MV contract: settings are read once, not distributed as
        # chapter-1 actions. Every H3 segment must see the identical cast,
        # picture bindings, world and voice rules.
        fixed=(
            '共通設定\n'
            '<Picture 1> = 女主角，黑色高馬尾。\n'
            '<Picture 2> = 男主角，穿深藍色外套。\n'
            '固定場景：台灣海邊的雨後街道。\n'
            '全片聲線：女主角使用台灣華語；男主角聲音低沉。\n'
            '服裝連續性：已完成的變化不重演。\n'
        )
        scenes='\n'.join(f'第{i+1}段：\n角色在場景內完成第{i+1}次獨立行動。'
                         for i in range(10))
        source=fixed+'\n故事內容\n'+scenes
        clips=film_manual.distribute_manual_prompt([(15,source)],60,15)
        self.assertGreater(len(clips),1)
        self.assertAlmostEqual(sum(seconds for seconds,_ in clips),60)
        for _,prompt in clips:
            self.assertTrue(prompt.startswith(film_manual._FILM_FIXED_BLOCK_START))
            self.assertIn(fixed.strip(),prompt)
            self.assertIn(film_manual._FILM_LOCAL_BLOCK_START,prompt)
        for i in range(10):
            self.assertEqual(sum(prompt.count(f'第{i+1}次獨立行動')
                                 for _,prompt in clips),1)
        req={'max_seconds':61.5,'target_seconds':60,'target_is_exact':True,
             'timeline_tolerance':1.5,'segment_seconds':15,'sound_mode':'auto'}
        plan=film_manual.make_manual_plan(
            clips,req,film.normalize_prompt,film.map_story,2,film.validate_manual_sound)
        self.assertIn('服裝連續性：已完成的變化不重演。',plan['shared_setup'])
        self.assertEqual(len(plan['segments']),len(clips))
        for seg in plan['segments']:
            self.assertEqual(seg['fixed_reference_settings'],plan['shared_setup'])
            self.assertIn('<Picture 1> = 女主角',seg['manual_h3_prompt'])
            self.assertIn('<Picture 2> = 男主角',seg['manual_h3_prompt'])

    def test_sixty_second_authored_shots_repeat_global_world_not_story_outcome(self):
        fixed=(
            '大乘蕉宗｜情境練習\n'
            '故事概念：男主角要解決一個祕密，最後真相尚未公開。\n'
            '共通設定\n'
            '(S1) = <Picture 1> = 成年女性，台灣華語。\n'
            '(S2) = <Picture 2> = 成年男性，低沉聲線。\n'
            '全場景：濕潤的台灣街道，冷色光線。\n'
            '不得任意替換角色及場景。\n'
            '分鏡時間軸\n'
        )
        shots='\n'.join(
            f'SHOT {i+1:02d}｜{i*5:.2f}–{(i+1)*5:.2f}秒\n'
            f'主角走到第{i+1}個指定位置，觀察雨後的街景。'
            for i in range(12))
        clips=film_manual.distribute_manual_prompt([(10,fixed+shots)],60,10)
        self.assertGreaterEqual(len(clips),6)
        for _,prompt in clips:
            self.assertTrue(prompt.startswith('subject_definitions:'))
            self.assertIn('不得任意替換角色及場景',prompt)
            self.assertIn('全場景：濕潤的台灣街道',prompt)
            self.assertIn('<Picture 1>',prompt)
            self.assertNotIn('最後真相尚未公開',prompt)
        for i in range(12):
            self.assertEqual(sum(prompt.count(f'第{i+1}個指定位置')
                                 for _,prompt in clips),1)

    def test_plain_story_without_shared_heading_is_not_promoted_to_global(self):
        source='\n'.join(f'演員完成事件{i+1}，接著向前走。' for i in range(8))
        clips=film_manual.distribute_manual_prompt([(15,source)],60,15)
        self.assertTrue(all('FIXED_REFERENCE_SETTINGS' not in prompt
                            for _,prompt in clips))
        self.assertEqual(sum(prompt.count('事件8') for _,prompt in clips),1)

    def test_interrupted_spoken_thought_survives_the_shot_02_boundary(self):
        # Repro for 5070 fb62b2239: two <d> utterances from the SAME SHOT
        # were split into separate generated clips at a silent inhale.
        from banana_mv.film_manual import _join_unfinished_dialogue
        actions=[
            '她努力擠出微笑，卻失敗了。',
            '(S1)「可是……你答應過我……」',
            '短暫吸氣，聲音開始哽咽。',
            '(S1)「這次……一定會帶我去玩水的。」',
            '男主角回答：',
            '(S2)「我知道……」'
        ]
        units=_join_unfinished_dialogue(actions)
        assert len(units)==4
        self.assertIn('短暫吸氣，聲音開始哽咽。',units[1])
        self.assertIn('可是……你答應過我……',units[1])
        self.assertIn('這次……一定會帶我去玩水的。',units[1])
        # Preserve two exact dialogue tags and the breath; don't merge their
        # spoken content into one rewritten sentence or move the male reply.
        self.assertNotIn('我知道……',units[1])
        scenes=[]
        for i in range(8):
            start=i*5
            beats=(actions if i==1 else [
                f'演員在第{i+1}顆鏡頭完成一個自然反應。',
                f'(S2)「第{i+1}段說完再轉場。」',
                f'鏡頭保持原始動作連續。'])
            scenes.append(f'SHOT {i+1:02d}｜{start:.2f}–{start+5:.2f}秒\n'+'\n'.join(beats))
        source='角色設定\n(S1) = <Picture 1> = 女主角。\n(S2) = <Picture 2> = 男主角。\n\n'+'\n\n'.join(scenes)
        clips=film_manual.distribute_manual_prompt([(10,source)],40,10)
        self.assertEqual(len(clips),5)
        self.assertTrue(all(7<=seconds<=10 for seconds,_ in clips))
        self.assertAlmostEqual(sum(seconds for seconds,_ in clips),40,delta=1.5)
        prompts=[prompt for _,prompt in clips]
        indices=[i for i,prompt in enumerate(prompts)
                 if '可是……你答應過我……' in prompt or '這次……一定會帶我去玩水的。' in prompt]
        self.assertEqual(len(indices),1,indices)
        self.assertEqual(prompts[indices[0]].count('<d>[Chinese] 可是……你答應過我……</d>'),1)
        self.assertEqual(prompts[indices[0]].count('<d>[Chinese] 這次……一定會帶我去玩水的。</d>'),1)
        self.assertIn('短暫吸氣，聲音開始哽咽。',prompts[indices[0]])

    def test_dense_realistic_shot_moves_whole_dialogue_into_next_clip(self):
        # The older fb62b2239 plan put all seven spoken lines of SHOT04/05
        # in one 9.417-second H3 clip; the final syllable vanished in render.
        shots=[]
        for shot in range(8):
            lines=[f'SHOT {shot+1:02d}｜{shot*5:.2f}–{(shot+1)*5:.2f}秒',
                   f'鏡頭第{shot+1}段繼續原本人物動作。']
            if shot==3:
                lines.extend([
                    '(S1)「你說……那個電腦？」',
                    '男主角緩慢搖頭。',
                    '(S2)「那不是普通的電腦。」',
                    '短暫停頓。',
                    '(S2)「那是我這兩個禮拜的心血。」'])
            elif shot==4:
                lines.extend([
                    '(S1)「那我呢……？」',
                    '她停頓，深深吸氣。',
                    '(S1)「你已經修了兩個禮拜了……」',
                    '男主角從畫外輕聲搶入：',
                    '(S2)「小語，妳聽我說……」',
                    '小語立刻接話，聲音短暫重疊：',
                    '(S1)「我只是想去玩水啊……」'])
            else:
                lines.extend([f'(S1)「第{shot+1}段完整講完。」',
                              f'(S2)「第{shot+1}段回答完畢。」'])
            shots.append('\n'.join(lines))
        source='角色設定\n(S1) = <Picture 1> = 小語。\n(S2) = <Picture 2> = 男主角。\n\n'+'\n\n'.join(shots)
        clips=film_manual.distribute_manual_prompt([(10,source)],40,10)
        self.assertLessEqual(len(clips),7)
        self.assertGreaterEqual(len(clips),5)
        self.assertAlmostEqual(sum(duration for duration,_ in clips),40.0,delta=1.5)
        for i,(duration,prompt) in enumerate(clips):
            self.assertLess(duration,10.0)
            lines=re.findall(r'\(S\d+\) <d>\[Chinese\] [^<]+</d>',prompt)
            budget=film_manual._dialogue_budget_seconds('\n'.join(lines))
            room=duration-film_manual.FILM_DIALOGUE_TAIL_SECONDS
            room-=film_manual.FILM_CHAIN5_OPENING_SECONDS if i else 0.18
            self.assertLessEqual(budget,room+0.001,
                                 f'Clip {i} has more speech than protected time')
        spoken=[re.findall(r'\(S\d+\) <d>\[Chinese\] [^<]+</d>',prompt)
                for _,prompt in clips]
        all_spoken='\n'.join('\n'.join(lines) for lines in spoken)
        self.assertEqual(all_spoken.count('我只是想去玩水啊……'),1)
        self.assertEqual(all_spoken.count('你已經修了兩個禮拜了……'),1)
        self.assertEqual(all_spoken.count('那是我這兩個禮拜的心血。'),1)
        self.assertFalse(any(
            '你說……那個電腦？' in prompt and
            '我只是想去玩水啊……' in prompt
            for _,prompt in clips),
            'The overloaded old 9.417s third clip must be redistributed')

    def test_count_is_dynamic_when_six_full_speech_events_will_not_fit_five_clips(self):
        # Every completed speech act is too long to pair with the next one
        # inside one 9.417-second clip (after visual/audio safety margins).
        # Six shorter native H3 clips should be tried instead of a hard error.
        long_line='我要把現在的問題全部解決完畢，才可以放心地回家休息。'
        shots=[]
        for i in range(8):
            lines=[f'SHOT {i+1:02d}｜{i*5:.2f}–{(i+1)*5:.2f}秒',
                   '人物沿著街道緩慢向前行走。']
            if i < 6:
                lines.append(f'(S1)「第{i+1}段{long_line}」')
            else:
                lines.append('兩人相互看著，保持原本的情緒與動作。')
            shots.append('\n'.join(lines))
        story='角色設定\n(S1) = <Picture 1> = 主角。\n\n'+'\n\n'.join(shots)
        clips=film_manual.distribute_manual_prompt([(10,story)],40,10)
        self.assertGreaterEqual(len(clips),6)
        self.assertTrue(all(5 <= seconds <= 10 for seconds,_ in clips))
        self.assertAlmostEqual(sum(seconds for seconds,_ in clips),40.0,delta=1.5)
        full='\n'.join(prompt for _,prompt in clips)
        for i in range(6):
            self.assertEqual(full.count(f'第{i+1}段{long_line}'),1)

    def test_40s_dialogue_packing_keeps_full_lines_and_chain5_start_safe(self):
        # Regression: the 2026-11-13 40s film had 8 authored 5s SHOTs
        # but Python assigned five hard 8s windows and broke the dialogue.
        shots=[]
        for i in range(8):
            start=i*5
            lines=[f'SHOT {i+1:02d}｜{start:.2f}–{start+5:.2f}秒',
                   f'角色表演與鏡頭轉換第{i+1}段。']
            if i==6:
                lines += ['(S1)「所以……」','短暫停頓。',
                          '(S1)「到底還要修多久？」',
                          '(S2)「我只剩最後一個 BUG。」']
            else:
                lines += [f'角色(S1)輕聲說：',f'(S1)「第{i+1}段完整台詞，請把它說完。」',
                          f'角色(S2)沉重回答：',f'(S2)「第{i+1}段我已經回答。」']
            shots.append('\n'.join(lines))
        story='角色設定\n小語與男主角在雨後街道對話。\n\n'+'\n\n'.join(shots)
        clips=film_manual.distribute_manual_prompt([(10,story)],40,10)
        self.assertEqual(len(clips),5)
        self.assertEqual(round(sum(seconds*24 for seconds,_ in clips)),960)
        self.assertTrue(all(7 <= seconds <= 10 for seconds,_ in clips))
        self.assertTrue(all(round(seconds*24)%17==5 for seconds,_ in clips))
        joined='\n'.join(prompt for _,prompt in clips)
        for i in range(8):
            self.assertEqual(joined.count(f'第{i+1}段完整台詞，請把它說完。'),0 if i==6 else 1)
        self.assertEqual(joined.count('所以……'),1)
        self.assertEqual(joined.count('到底還要修多久？'),1)
        self.assertTrue(any('所以……' in prompt and '到底還要修多久？' in prompt
                            for _,prompt in clips))
        for _,prompt in clips:
            self.assertIn('detailed_description:',prompt)
            self.assertNotIn('PYTHON-OWNED SOURCE INTERVAL',prompt)
        guarded=film_manual.protect_chain5_opening(clips[1][1])
        self.assertEqual(guarded.count('CHAIN5_VISUAL_ONLY_LEAD_IN'),1)
        self.assertLess(guarded.index('CHAIN5_VISUAL_ONLY_LEAD_IN'),
                        guarded.index('<d>[Chinese]'))
        self.assertEqual(film_manual.protect_chain5_opening(guarded),guarded)

    def test_classic_python_slot_wardrobe_survives_real_film_h3_slots(self):
        # Proven MV Python Slot contract: identity comes from Picture refs,
        # but a coat removed in an earlier slot must not be reintroduced
        # just because the reference photo still shows its opening outfit.
        setup=(
            '角色設定\n'
            '(S1) = <Picture 1> = 演員。\n'
            '(S2) = <Picture 2> = 旁白。\n'
            '人物五官與開場服裝依照參考圖片。\n'
            '開場穿著：\n藍色外套\n灰色長褲\n黑色長靴\n\n'
            '固定場景：紅幕舞台。\n\n'
        )
        actions=[
            '演員穿著完整開場服裝，在紅幕舞台登場。',
            '演員解開藍色外套，接著脫下藍色外套。',
            '演員以無外套狀態繼續跳舞。',
            '演員脫下灰色長褲。',
            '演員只穿黑色長靴繼續表演。',
            '演員脫下黑色長靴。',
            '演員赤腳走向聚光燈。',
            '演員以目前外觀謝幕。'
        ]
        source=setup+'\n\n'.join(
            f'SHOT {i+1:02d}｜{i*5:.2f}–{(i+1)*5:.2f}秒\n'+action
            for i,action in enumerate(actions))
        clips=film_manual.distribute_manual_prompt([(10,source)],40,10)
        self.assertEqual(len(clips),5)
        self.assertTrue(all(7<=seconds<=10 for seconds,_ in clips))
        self.assertAlmostEqual(sum(seconds for seconds,_ in clips),40,delta=1.5)
        prompts=[prompt for _,prompt in clips]
        joined='\n'.join(prompts)
        for action in actions:
            self.assertEqual(joined.count(action),1,action)
        for prompt in prompts:
            self.assertIn('<Picture 1>',prompt)
            self.assertIn('<Picture 2>',prompt)
            self.assertIn('Python當前狀態',prompt)
            self.assertIn('CURRENT_ACTOR_STATE',prompt)
        removed_coat=next(i for i,prompt in enumerate(prompts)
                          if '演員解開藍色外套' in prompt)
        self.assertLess(removed_coat,len(prompts)-1)
        after_coat=prompts[removed_coat+1]
        self.assertIn('Torso: Bare;',after_coat)
        self.assertIn('藍色外套 already removed, stays off.',after_coat)
        self.assertIn('初始服裝僅作歷史參考',after_coat)
        self.assertIn('人物五官依照參考圖片',after_coat)
        self.assertNotIn('開場穿著：\n藍色外套',after_coat)
        self.assertIn('灰色長褲 worn.',after_coat)
        self.assertIn('黑色長靴 worn.',after_coat)
        last=prompts[-1]
        self.assertIn('Feet: Barefoot;',last)
        self.assertIn('Torso: Bare;',last)
        self.assertIn('Bottom: Bare;',last)
        self.assertEqual(last.count('演員脫下黑色長靴。'),0)

    def test_classic_actor_state_is_inert_when_no_wardrobe_changes_are_authored(self):
        clips=self.generated()
        self.assertTrue(all('CURRENT_ACTOR_STATE' not in prompt
                            and 'Python當前狀態' not in prompt
                            for _,prompt in clips))

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
