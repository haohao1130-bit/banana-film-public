"""Regression: VNext H3 sampling uses the legacy one-click film padded size.

The final export still uses the requested output dimensions.
"""
import unittest
from unittest.mock import patch

from banana_mv.film_vnext.local_adapter import _h3_render_size
from banana_mv.film_vnext.pipeline import ProductionError


class VNextH3DimensionsTests(unittest.TestCase):
    def test_portrait_720p_aligns_width_before_sampling(self):
        self.assertEqual(_h3_render_size((720, 1280)), (736, 1280))

    def test_portrait_480p_aligns_height_before_sampling(self):
        self.assertEqual(_h3_render_size((480, 854)), (480, 864))

    def test_all_original_output_presets_keep_existing_contract(self):
        from banana_mv.core import OUTPUT_SIZE_PRESETS, dimensions
        for preset in OUTPUT_SIZE_PRESETS.values():
            for aspect, output in preset.items():
                with self.subTest(aspect=aspect, output=output):
                    self.assertEqual(_h3_render_size(output), dimensions(aspect, output[0]))
                    self.assertTrue(all(dim % 32 == 0 for dim in _h3_render_size(output)))

    def test_unknown_size_is_not_silently_changed(self):
        with self.assertRaises(ProductionError):
            _h3_render_size((721, 1280))


    def test_native_trim_crops_after_five_frame_prefix_without_audio_loss(self):
        from banana_mv.film_media import trim_native
        from banana_mv import film_media
        with patch.object(film_media, "require_audio"), \
                patch.object(film_media, "command") as command, \
                patch.object(film_media, "probe", return_value={
                    "streams": [{"codec_type": "video", "nb_frames": "243"}]
                }):
            trim_native("raw.mp4", "part.mp4", 243,
                        prefix_frames=5, output_size=(720, 1280))
        argv = command.call_args.args[0]
        self.assertIn("crop=720:1280", argv[argv.index("-vf") + 1])
        self.assertIn("atrim=start=", argv[argv.index("-af") + 1])
        self.assertEqual(argv[argv.index("-map") + 1], "0:v:0")
        self.assertIn("0:a:0", argv)

    def test_legacy_native_trim_without_output_size_has_no_crop(self):
        from banana_mv.film_media import trim_native
        from banana_mv import film_media
        with patch.object(film_media, "require_audio"), \
                patch.object(film_media, "command") as command, \
                patch.object(film_media, "probe", return_value={
                    "streams": [{"codec_type": "video", "nb_frames": "124"}]
                }):
            trim_native("raw.mp4", "part.mp4", 124)
        argv = command.call_args.args[0]
        self.assertNotIn("crop=", argv[argv.index("-vf") + 1])


if __name__ == "__main__":
    unittest.main()
