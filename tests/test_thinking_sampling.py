import copy
import unittest
from unittest.mock import patch

from banana_mv import services


def sampling(thinking, **extra):
    cfg = copy.deepcopy({'rewriter': dict(services.DEFAULTS['rewriter'], thinking=thinking, **extra),
                         'comfy_url': 'http://x', 'comfy_input_dir': '/tmp'})
    with patch.object(services, 'upload_comfy_image', return_value='x.jpg'):
        graph, _ = services.build_rewrite_graph(cfg, 'SYSTEM', [('text', 'hi')], 'job')
    inputs = graph['generate']['inputs']
    return (inputs['sampling_mode.temperature'], inputs['sampling_mode.top_p'],
            inputs['sampling_mode.presence_penalty'], inputs['prompt'])


class ThinkingSamplingTests(unittest.TestCase):
    def test_thinking_uses_qwen_thinking_sampling_and_brake(self):
        temperature, top_p, presence, prompt = sampling(True)
        self.assertEqual((temperature, top_p, presence), (1.0, 0.95, 1.5))
        self.assertIn('never reopen a settled decision', prompt)
        system = prompt.split('<|im_end|>')[0]
        self.assertNotIn('think>', system)  # 9B 會照抄提示；標籤一出現 ComfyUI 就切錯

    def test_result_keeps_only_text_after_the_last_thinking_tag(self):
        # 實測 cf58d55cc03a：思考照抄「close </think>」，正式稿前面混進思考與兩份草稿。
        leaked = 'quoted: close </think>. drafts...\nsubject_definitions:\nDRAFT\n</think>\n\nsubject_definitions:\nFINAL'
        cfg = {'rewriter': dict(services.DEFAULTS['rewriter'], thinking=True), 'comfy_url': 'http://x', 'comfy_input_dir': '/tmp'}
        with patch.object(services, '_rewrite_once', return_value=(leaked, 'thinking', 'pid')):
            self.assertEqual(services.rewrite_local(cfg, 'S', [('text', 'x')], 'job'), 'subject_definitions:\nFINAL')

    def test_non_thinking_keeps_defaults(self):
        self.assertEqual(sampling(False)[:3], (0.7, 0.8, 0.0))

    def test_config_override_is_respected(self):
        self.assertEqual(sampling(True, presence_penalty=0.5)[2], 0.5)


if __name__ == '__main__':
    unittest.main()
