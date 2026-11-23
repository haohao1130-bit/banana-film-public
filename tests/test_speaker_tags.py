import unittest

from banana_mv.direction_contract import authored_dialogue, fix_speaker_tags, speaker_missing

SHARED = '<Picture 2>＝小貓＝S2\n<Picture 3>＝小狸＝S3\n<Picture 5>＝小浣＝S5\n<Picture 7>＝白髮老人靈魂＝S6'
BRIEF = ('[4-7秒] S2走來遞給她一串。\nS2對S5說（平靜）：「這串妳的。」\n'
         '[7-10秒] S5眼睛一亮。\nS5對S2說（驚喜）：「小貓！你最好了！」')
PROMPT = """subject_definitions:
<Subject 1> is 小貓 from <Picture 2>: an orange tabby cat chef.
<Subject 3> is 小浣 from <Picture 5>: a round raccoon.

summary:
A skewer is shared.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved.

detailed_description:
[Shot 1] <Subject 1> (S2) says in a relaxed voice, <d>[Chinese] 這串妳的。</d> <Subject 3>'s eyes pop open; she coos with genuine gladness, <d>[Chinese] 小貓！你最好了！</d>

overall_soundscape:
Room tone.

non_diegetic_music:
N/A"""


class SpeakerTagTests(unittest.TestCase):
    def test_locks_read_names_and_role_codes(self):
        # 實測 cf9f52c7f21f：「<Picture 2>＝小貓＝S2」被讀成名字「小貓＝S2」，菜單寫「S5對S2說」也對不上，一句都沒鎖。
        locks = authored_dialogue(BRIEF, SHARED)
        self.assertEqual([(l['speaker'], l['reference'], l['role']) for l in locks],
                         [('小貓', '<Picture 2>', 'S2'), ('小浣', '<Picture 5>', 'S5')])

    def test_untagged_line_gets_its_real_speaker(self):
        # 第 18 段：小浣的台詞前最近的標籤是小貓，H3 用小貓的聲音講「小貓！你最好了！」
        fixed, repaired = fix_speaker_tags(PROMPT, authored_dialogue(BRIEF, SHARED))
        self.assertEqual(repaired, ['小貓！你最好了！'])
        self.assertIn('gladness, <Subject 3> (S1) says, <d>[Chinese] 小貓！你最好了！', fixed)
        self.assertIn('<Subject 1> (S2) says in a relaxed voice, <d>[Chinese] 這串妳的。', fixed)   # 對的不動
        self.assertEqual(fix_speaker_tags(fixed, authored_dialogue(BRIEF, SHARED))[1], [])          # 再跑不重複補

    def test_listener_tag_and_duplicate_tags_are_handled(self):
        # 第 17 段：老人的台詞前最近的標籤是聽的人小巫，還有「(S6) (S6)」重複標。
        prompt = PROMPT.replace('<Subject 3> is 小浣', '<Picture 7> is the appearance reference for <Subject 4>, 白髮老人.\n<Subject 3> is 小浣')
        prompt = prompt.replace('[Shot 1]', '[Shot 1] <Subject 4> (S6) (S6) speaks slowly, looking at <Subject 1> (S2), '
                                '<d>[Chinese] 有人為自己做飯。</d>')
        brief = BRIEF + '\nS6對S2說：「有人為自己做飯。」'
        fixed, repaired = fix_speaker_tags(prompt, authored_dialogue(brief, SHARED))
        self.assertIn('有人為自己做飯。', repaired)
        self.assertIn('looking at <Subject 1> (S2), <Subject 4> (S6) says, <d>[Chinese] 有人為自己做飯。', fixed)
        self.assertNotIn('(S6) (S6)', fixed)

    def test_speaker_missing_from_definitions_is_reported(self):
        # 第 9 段：9B 沒定義小浣，Python 無從補標，退回重寫。
        prompt = PROMPT.replace('<Subject 3> is 小浣 from <Picture 5>: a round raccoon.\n', '')
        missing = speaker_missing(prompt, authored_dialogue(BRIEF, SHARED))
        self.assertEqual([lock['speaker'] for lock in missing], ['小浣'])
        self.assertEqual(speaker_missing(PROMPT, authored_dialogue(BRIEF, SHARED)), [])

    def test_bare_speaker_lines_are_locked(self):
        # 最簡寫法：冒號前只有代號或名字（可加語氣）也算台詞；招牌上的「」不算。
        for brief in ('S5：「小貓！你最好了！」', 'S5（驚喜）：「小貓！你最好了！」',
                      '小浣：「小貓！你最好了！」', '- S5：「小貓！你最好了！」'):
            with self.subTest(brief=brief):
                self.assertEqual([(l['speaker'], l['line']) for l in authored_dialogue(brief, SHARED)],
                                 [('小浣', '小貓！你最好了！')])
        self.assertEqual(authored_dialogue('場景：吧台。「歡迎光臨」的招牌。', SHARED), [])

    def test_names_inside_dialogue_are_not_on_screen(self):
        # 小浣說「小貓！你最好了！」不代表小貓入鏡：小貓的圖不送給 H3。
        from banana_mv.film import kitchen_absent_pictures
        absent = kitchen_absent_pictures('S5在吧台吃串燒。\nS5：「小貓！你最好了！」', SHARED)
        self.assertIn(2, absent)
        self.assertNotIn(5, absent)
        self.assertNotIn(2, kitchen_absent_pictures('S2遞給S5一串。\nS5：「小貓！你最好了！」', SHARED))


if __name__ == '__main__':
    unittest.main()
