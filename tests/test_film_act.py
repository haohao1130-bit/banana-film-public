"""Regression checks for full ACT + shared-settings film briefs."""
import unittest

from banana_mv.film_act import split_act_source


COMMON = """BANANAMV｜《三英戰呂布》
【共同設定】（附加在每一段前面）
■ 畫風
真人三國史詩，無配樂。
■ 角色綁定
@圖片1 = 呂布
@圖片2 = 劉備
@圖片3 = 關羽
@圖片4 = 張飛
@圖片5 = 董卓
■ 表情總原則
全員嚴肅。
【分段通告單】（每段十秒）
"""
SPEECH = (
    ('劉備說：「奉先，今日我們三人，好好談談。」', '呂布說：「談？我只談戰。」'),
    ('關羽說：「奉先，你的呼吸，亂了。」', '呂布說：「是你的刀，離我太近了。」'),
    ('張飛咆哮地說：「俺不是來打架的！俺是來抱的！」', '呂布說：「三弟放手！」'),
    ('劉備說：「我找你找得多苦？」', '呂布說：「我有義父了！」'),
    ('劉備說：「戰場從來不只有一處。」', '呂布說：「這不是虎牢關嗎？」'),
    ('董卓暴怒吼：「誰動了我的奉先？！」', '赤兔馬的旁白 OS，低沉地說：「……我只是一匹馬。」'),
)


def _six_act_story():
    parts = [COMMON]
    for i, (first, second) in enumerate(SPEECH, 1):
        start, end = (i - 1) * 10, i * 10
        parts.append(f"""ACT {i:02d}｜{start//60:02d}:{start%60:02d}.000–{end//60:02d}:{end%60:02d}.000
入鏡：@圖片1 呂布、@圖片2 劉備
段落：第{i}幕
【場景】虎牢關城牆與營帳
【承接】延續上一幕。
【角色表情】全員莊重。
【H3 提示詞】
0–2.5秒：{first}
2.5–7.5秒：{second}
7.5–10秒：四位勇士凝視木牌「免戰三日」，畫面穩定。
【音效】風聲，馬蹄聲。
【交棒】保持目前站位。
""")
    return '\n'.join(parts)


class ActParserTests(unittest.TestCase):
    def test_six_ten_second_clips(self):
        clips = split_act_source(_six_act_story())
        self.assertEqual(len(clips), 6)
        self.assertEqual([seconds for seconds, _ in clips], [10.0] * 6)
        settings = [clip.split('subject_definitions:\n', 1)[1].split('\n\nsummary:', 1)[0]
                    for _, clip in clips]
        self.assertEqual(len(set(settings)), 1)
        self.assertTrue(all('No background music.' in clip for _, clip in clips))
        self.assertTrue(all(clip.count('[Shot ') == 3 for _, clip in clips))
        self.assertIn('[Shot 2] At 00:02.500,', clips[0][1])
        self.assertIn('[Shot 3] At 00:07.500,', clips[0][1])
        self.assertIn('(S3) <d>[Chinese] 奉先，你的呼吸，亂了。</d>', clips[1][1])
        self.assertIn('(S4) <d>[Chinese] 俺不是來打架的！俺是來抱的！</d>', clips[2][1])
        self.assertIn('(S5) <d>[Chinese] 誰動了我的奉先？！</d>', clips[5][1])
        self.assertIn('(S6) <d>[Chinese] ……我只是一匹馬。</d>', clips[5][1])
        self.assertIn('「免戰三日」', clips[5][1])

    def test_legacy_is_unchanged(self):
        self.assertIsNone(split_act_source('SHOT 01｜0–10秒\n開場。'))

    def test_invalid_act_header_is_not_silently_repartitioned(self):
        with self.assertRaisesRegex(ValueError, 'ACT'):
            split_act_source(COMMON + 'ACT 01｜0-10\n')

    def test_micro_timing_must_be_contiguous(self):
        with self.assertRaisesRegex(ValueError, '時間不連續'):
            split_act_source(COMMON + """ACT 01｜00:00.000–00:10.000
【H3 提示詞】
0–2秒：站立。
3–10秒：移動。
""")


if __name__ == '__main__':
    unittest.main()
