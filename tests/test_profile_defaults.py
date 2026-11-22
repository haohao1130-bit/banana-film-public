import os
import unittest
from unittest.mock import Mock, patch

from banana_mv import film_server


class ProfileDefaultsTests(unittest.TestCase):
    def defaults(self, profile=None):
        env = {} if profile is None else {'BANANA_FILM_PROFILE': profile}
        with patch.dict(os.environ, env, clear=False):
            if profile is None:
                os.environ.pop('BANANA_FILM_PROFILE', None)
            handler = object.__new__(film_server.Handler)
            handler.send_json = Mock()
            handler.path = '/api/film/defaults'
            handler.do_GET()
            return handler.send_json.call_args.args[0]

    def test_colab_is_720p_10s_6_steps_director_thinking_without_vsr(self):
        for profile in ('colab', None):
            with self.subTest(profile=profile):
                d = self.defaults(profile)
                self.assertEqual((d['profile'], d['resolution'], d['segment_seconds'], d['sampling_steps']),
                                 ('colab', 720, 10, 6))
                self.assertTrue(d['auto_director'] and d['rewriter_thinking'])
                self.assertFalse(d['upscale_available'])

    def test_5070_keeps_page_defaults_and_vsr(self):
        d = self.defaults('5070')
        self.assertEqual(d, {'profile': '5070', 'upscale_available': True})

    def test_entrypoints_declare_their_profile(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        self.assertIn("BANANA_FILM_PROFILE='colab'", (root/'tools/film_runtime.py').read_text(encoding='utf-8'))
        self.assertIn('os.environ.setdefault("BANANA_FILM_PROFILE", "5070")',
                      (root/'film_v2/local_classic_server.py').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
